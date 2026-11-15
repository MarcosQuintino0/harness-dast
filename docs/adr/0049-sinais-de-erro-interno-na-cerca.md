# 0049. Sinais de erro interno vistos pela cerca

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** plano do ciclo V1.3 a V1.8, versão 1.5 (item "sinais de erro interno nas respostas"), parte que o [ADR 0045](0045-sinais-passivos-de-erro-interno.md) deixou fora. Usa o proxy de escopo do [ADR 0017](0017-proxy-de-escopo-com-scopeguard.md) e o relatório do [ADR 0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md). Não substitui o ADR 0045.

## Contexto

O ADR 0045 conta sinais de erro interno (erro de banco, rastreamento de exceção, resposta 5xx) só nas evidências que o `scan` guardou: no máximo 200 mensagens, as mais graves, ligadas a um alerta do ZAP. A maior parte das respostas do alvo nunca chega a elas. Uma pilha de chamadas devolvida a um pedido do `probe`, do `authz` ou a um ataque do ZAP que não virou alerta fica invisível, e o relatório de 0045 diz "zero" sem dizer que olhou pouco.

Quem vê **toda** resposta do alvo é a cerca (o proxy de escopo, `docker/scope-proxy/addon.py`). O hook `response` do addon já recebe a resposta inteira (`flow.response.raw_content`, até `body_size_limit=20m` do `entrypoint.sh`) para medir o tamanho que grava na auditoria, e o motor já importa o `ScopeGuard` do domínio, porque a imagem instala o pacote `harness_dast` (`Dockerfile`: `pip install --no-deps /src`). Reconhecer um sinal conhecido numa resposta que já está na memória do proxy custa pouco e não exige tráfego novo.

Restrições: a cerca só pode **acrescentar** recusas; olhar uma resposta nunca pode negar, atrasar de forma perceptível ou alterar o tráfego. A trilha de auditoria guarda só nomes, nunca corpo (ADR 0017, item 6). A lista de sinais tem de ser fixa, testada e do domínio (regra do `CLAUDE.md`: decisão só em `domain`). Nada aqui amplia escopo, limites, janela ou autorização.

## Decisão

Vamos fazer a cerca reconhecer uma lista **fixa** de sinais de erro interno em cada resposta liberada, gravar na auditoria só a categoria, e transformar as categorias em achados de origem própria no relatório.

### 1. O catálogo fica no domínio

Módulo novo `domain/error_signal_catalog.py` (puro: só `re`, `typing` e pydantic). Ele define:

- `SignalCategory`, um `Literal` fechado: `sql_error`, `stack_trace_java`, `stack_trace_python`, `stack_trace_dotnet`, `stack_trace_node`, `stack_trace_php`, `debug_page`.
- `SIGNAL_RULES`, uma tupla de regras `{category, label, pattern, severity, confidence, cwe}`. Padrões iniciais (os testes os fixam; o programador pode refiná-los, nunca ampliar a lista de categorias sem novo ADR):

  | Categoria | O que reconhece (versão inicial) | Severidade proposta | Confiança | CWE |
  | --- | --- | --- | --- | --- |
  | `sql_error` | `ORA-` e cinco dígitos; `SQLSTATE` e cinco caracteres; `syntax error at or near`; `You have an error in your SQL syntax`; `unclosed quotation mark after the character string`; `SQLite3::`; `PSQLException`; `java.sql.SQL...Exception` | média | média | 209 |
  | `stack_trace_java` | duas ou mais linhas `at pacote.Classe.metodo(Arquivo.java:N)` seguidas, ou `Caused by:` com nome de exceção; também com quebra de linha escapada em JSON (`\n\tat ...`) | baixa | média | 209 |
  | `stack_trace_python` | `Traceback (most recent call last)`; `File "x.py", line N` | baixa | média | 209 |
  | `stack_trace_dotnet` | `at Namespace.Classe.Metodo(...) in Arquivo.cs:line N` | baixa | média | 209 |
  | `stack_trace_node` | `at funcao (/caminho/arquivo.js:L:C)` junto de `node_modules` ou `node:internal` | baixa | média | 209 |
  | `stack_trace_php` | `Stack trace:` seguido de `#0`; `PHP Fatal error` com `on line N` | baixa | média | 209 |
  | `debug_page` | marcadores de página de depuração de framework (`Werkzeug Debugger`, `DEBUG = True` da página de erro do Django) | média | alta | 489 |

  Todo padrão usa quantificadores limitados (como os de `internal_error_signals.py`) e nunca aninha repetições: o tempo de uma busca é linear no tamanho do texto, e um teste com texto patológico de 64 KiB prova isso.
- `detect_signals(text: str) -> tuple[SignalCategory, ...]`: ordem fixa do catálogo, sem repetição, **nunca devolve trecho**.
- `is_scannable(status, method, content_type) -> bool`: só olha resposta com corpo (`status` fora de 1xx, 204 e 304; `method` diferente de `HEAD`) e tipo `application/json`, `*+json`, `application/xml`, `text/xml`, `*+xml`, `text/plain`, `text/html` ou ausente. JavaScript, CSS, imagem e binário ficam de fora: pacotes de interface trazem textos como `Exception:` sem ser vazamento.
- Constantes `SCAN_LIMIT_BYTES = 65_536` e `COMPRESSED_INPUT_LIMIT = 262_144`.

O ADR 0045 continua como está: `internal_error_signals.py` mantém os três padrões dele e o formato `counts` do relatório. Para a lista não divergir sem ninguém ver, um teste exige que todo texto que os padrões de 0045 (`stack_trace`, `sql_error`) reconhecem seja reconhecido por alguma categoria do catálogo novo.

### 2. Como a lista chega ao proxy

O catálogo é domínio puro e o proxy já instala o pacote inteiro; nada é copiado. Adaptador novo `adapters/scope_proxy/signals.py` (sem mitmproxy, testado no host) traduz uma resposta em bytes numa leitura:

```
inspect_response(method, status, headers, raw_body) -> SignalReading(categories, skipped)
```

- Sem `Content-Encoding` ou com `identity`: lê os primeiros `SCAN_LIMIT_BYTES` do corpo.
- `gzip` e `deflate`: descomprime só os primeiros `COMPRESSED_INPUT_LIMIT` bytes de entrada com `zlib.decompressobj(...).decompress(dados, SCAN_LIMIT_BYTES)`; a saída é limitada, então uma bomba de descompressão não gasta memória.
- Qualquer outra codificação (`br`, `zstd`...) ou erro de `zlib`: não olha e devolve `skipped` com o motivo (`encoding`).
- Decodifica em UTF-8 com substituição e entrega o texto a `detect_signals`. Não conserva nada do texto.
- Resposta fora de `is_scannable`: `skipped = "type"`; corpo vazio: `skipped = "empty"`.

O hook `response` do addon chama o adaptador **antes** de gravar a linha de auditoria. A leitura é total: não levanta; o único erro tratado é o de descompressão, dentro do adaptador. **Esta é a única parte da cerca que falha aberta, de propósito:** ela só observa, nunca decide o que passa, e um defeito aqui jamais pode virar recusa nem travar uma execução. Qualquer outra coisa do hook continua como era.

### 3. O que a auditoria guarda

`AuditRecord` (`adapters/scope_proxy/audit.py`) ganha dois campos opcionais, omitidos da linha quando vazios (como `detail`):

- `signals`: tupla com as **categorias** encontradas. Nada de corpo, trecho, código de erro ou nome de classe.
- `signal_skip`: `type`, `encoding` ou `empty`, quando a resposta liberada não foi lida. Resposta liberada sem `signal_skip` e com `status` foi lida. É isso que dá a contagem honesta de "respostas examinadas".

Linhas negadas e do `CONNECT` não levam os campos. O restante da linha (método, caminho decodificado, nomes de parâmetro de consulta, status, bytes) é o que já existe; a requisição que causou o sinal fica identificada por ele. O trecho redigido que a tarefa previa **não** é gravado: preferimos não ter nenhum a ter um que a redação (`domain/redaction.py`) não cobriu. Quem quiser ver o conteúdo repete a operação.

`FileProxyAudit._row` e `ProxyRow` (`domain/traffic.py`) passam a ler `path`, `status`, `query_params`, `signals` e `signal_skip`, todos com padrão vazio: linha antiga continua legível e `summarize_traffic` não muda.

### 4. Custo e limite

- Leitura no máximo de 64 KiB por resposta (até 256 KiB comprimidos de entrada). A resposta inteira já está na memória do proxy; não há leitura nem tráfego novo.
- Critério de aceite medido no laboratório (não presumido): a leitura acrescenta menos de 5 ms por resposta no pior caso (64 KiB de texto, todos os padrões), e a taxa de 50 req/s do teto absoluto cabe sem fila nova. Se estourar, o limite cai para 32 KiB; o programador registra a medida no relatório.
- O `Connection: close` e as demais respostas do addon não mudam.

### 5. Cada sinal vira um achado, com técnica própria

Como os achados do `authz` (ADR 0027), são achados **de origem própria**, não alertas do ZAP:

- Técnica `proxy_error_signal`. Modelo novo `SignalFinding` (`domain/signal_result.py`, congelado): `finding_id` (`S-` e 8 hexadecimais do fingerprint), `fingerprint`, `fingerprint_version`, `origin` = `proxy`, `technique`, `category`, `title`, `proposed_severity` e `proposed_confidence` (da tabela do catálogo; nunca do agente), `cwe`, `owasp_api_2023` (`API8:2023`, proposta), `operation_id` (ou `None`), `method`, `path_template`, `occurrences`, `statuses` (até 5 códigos distintos), `query_params` (até 10 nomes, da primeira ocorrência), `description`, `solution`, `status` = `needs_triage`. Nenhum valor de resposta entra no modelo.
- **Atribuição à operação:** a linha da auditoria traz o caminho concreto; `AlertResolver` (`domain/finding_build.py`, casamento de modelo de caminho com as operações do `probe`) o liga a uma operação. Sem casamento, `operation_id` é `None` e `path_template` é `generic_template(caminho)` (`domain/finding.py`): ids viram `{}`, nunca a URL concreta com carga de ataque.
- **Fingerprint:** SHA-256 de `hdast-signal-v1`, produto, método, modelo de caminho e categoria. Fora: host, status, ids, parâmetros, quantidade, execução. `SIGNAL_FINGERPRINT_VERSION = 1`. Linhas com o mesmo fingerprint viram **um** achado com `occurrences`.
- **Janela:** só linhas liberadas entre o início do `probe` e o fim do último estágio gravado (`probe.json`, `scan.json`, `authz.json`, e `negative.json` quando existir, ADR 0051). É a mesma ideia do `summarize_traffic` e do `metrics.json` (ADR 0031), que já filtram a trilha por intervalo.
- **Entrada do relatório:** `FindingsReport` ganha `proxy_signals: ProxySignals | None` (aditivo; `None` em relatório antigo) com `enabled`, `window`, `responses_examined`, `responses_skipped` por motivo, `responses_with_signal`, `counts` por categoria e `findings`. `FindingsSummary` ganha `signal_by_severity` (como `authz_by_severity`: **não** entra em `total` nem em `by_severity`, que seguem sendo do ZAP). `exceeds()` (`application/report.py`) passa a contar também os achados de sinal, pelo mesmo critério do `authz`: o gate de severidade não pode ser contornado por achado de origem própria, e a triagem nunca retira achado da conta.
- **Artefato:** `error-signals.json` na pasta da execução, gravado pelo `report` quando há auditoria do proxy e linhas na janela. Se a auditoria não estiver disponível (pilha refeita, sem pilha gerenciada), o `report` reutiliza o arquivo que já existe; se não existir nenhum, `proxy_signals.enabled = false` com a mensagem "a cerca não registrou respostas desta execução". Porta nova de leitura e escrita em `RunArtifacts` (`application/scan_ports.py`) e implementação no armazém de `adapters/reporting/`.

### 6. Como se junta aos sinais passivos do ADR 0045 sem duplicar

- Os dois são **fontes diferentes** e **não se somam**: 0045 conta mensagens de evidência do ZAP (um subconjunto); 0049 conta respostas liberadas pela cerca (o conjunto). A seção de 0045 do relatório continua igual em JSON e ganha, só no Markdown e no HTML, uma linha que diz "subconjunto das respostas; a contagem completa está em 'Sinais vistos pela cerca'" quando `proxy_signals.enabled` é verdadeiro.
- **Só 0049 gera achado.** 0045 continua só contagem e não passa a gerar achado. A resposta 5xx **não** vira achado na cerca (o ZAP provoca muito 5xx de propósito): fica só como contagem de 0045; o 5xx em valor inválido é tratado pelo ADR 0051.
- O ZAP pode reportar o mesmo vazamento como alerta próprio ("Application Error Disclosure"). Não deduplicamos entre origens: o achado nunca some. O texto do achado de sinal diz que o ZAP pode ter o mesmo achado e que os dois precisam de uma triagem só.

### 7. Contrato (aditivo)

- Auditoria do proxy: campos `signals` e `signal_skip` (opcionais, fora da linha quando vazios).
- `findings.json` e `report.md` e `report.html`: `proxy_signals`, `summary.signal_by_severity` e a seção "Sinais vistos pela cerca".
- Pasta da execução: `error-signals.json`.
- Sem mudança de `schema_version` do relatório, de códigos de saída, de envelope, do perfil nem da impressão digital da aprovação.
- A imagem do proxy muda: sem `stack up --build` o teste roda a cerca antiga (escada de testes, "A imagem do proxy").

## Alternativas consideradas

- **Gravar o trecho redigido na auditoria.** A redação (`domain/redaction.py`) é uma rede de segurança, não garantia (ADR 0022, item 9), e a auditoria é por desenho livre de corpo. Descartada: a categoria e a requisição bastam para quem vai repetir a operação.
- **Gravar o código do erro (`ORA-00933`, `SQLSTATE 42S02`).** Parece inofensivo e é útil, mas abre a porta para "só mais um campo" de texto do alvo na auditoria. Fica fora desta decisão; pode entrar por ADR novo, com gramática fechada, se a triagem pedir.
- **Contar sinais no relatório do ZAP, depois do `scan`.** É o ADR 0045: só vê 200 mensagens. Mantido como segunda fonte, não como a fonte.
- **Ler o corpo na CLI, repetindo o pedido.** Dobra a carga no alvo e ainda perde o que o ZAP gerou. Descartada.
- **Script do ZAP ou regra passiva do ZAP.** Roda no processo que queremos observar de fora e não vê o tráfego do `probe` pela rota `auth` nem o do `authz`. Descartada, pelo mesmo argumento do ADR 0017.
- **Usar só o alerta "Application Error Disclosure" do ZAP e parar.** Perde o que o ZAP não promove a alerta e depende da política do `scan`. Descartada como única fonte.
- **Deduplicar contra os alertas do ZAP.** Exigiria casar uma resposta com um alerta por mensagem; o achado nunca some por contrato, e a duplicata é inofensiva e declarada. Descartada.
- **Tornar o 5xx um achado.** O varredor ativo gera 5xx como parte do ataque; o relatório viraria ruído. Descartada.
- **Falhar fechado quando a leitura falha.** A leitura é observação, não trava. Recusar uma resposta por defeito de leitura criaria uma nova forma de negar serviço ao próprio teste. Descartada, com o motivo escrito na decisão.

## Consequências

- O relatório passa a dizer, sobre **todas** as respostas liberadas, quantas foram lidas, quantas ficaram sem leitura e por quê (`encoding`, `type`, `empty`) e quantas traziam cada sinal. Um "zero" passa a vir com a base.
- Cada vazamento de erro interno ganha achado próprio, com severidade proposta pelo código, fingerprint estável e contagem. A comparação entre execuções (`report --compare`) vale para esses achados pelo mesmo mecanismo do `authz` (verificar na implementação; se a comparação não cobrir os achados de origem própria, a limitação fica escrita no relatório).
- Custo: um adaptador, um modelo, uma porta de artefato e um estágio de leitura no `report`; o proxy lê até 64 KiB por resposta.
- A imagem do proxy muda: todo teste de laboratório desta decisão exige `stack up --build`.
- O ADR 0045 não é editado: continua aceito como está, agora como a "segunda fonte" descrita acima.

## Casos de teste obrigatórios

Unitários (degrau 2), um arquivo por módulo, no espelho de `tests/unit/`:

- `domain/test_error_signal_catalog.py`: um texto positivo e um negativo por categoria; positivo com quebra de linha escapada em JSON (`\n\tat ...`); negativo para texto de documentação e de JavaScript; texto patológico de 64 KiB termina rápido; texto vazio, `None`, só espaços; `Traceback` cortado ao meio; entrada Unicode, controle e bidi não quebram; a ordem do resultado é fixa; nenhuma saída contém trecho do texto; todo texto que os padrões de 0045 reconhecem é reconhecido por alguma categoria.
- `domain/test_error_signal_catalog.py` (`is_scannable`): `HEAD`, 204 e 304 não; JSON, XML, `text/plain`, `text/html` e ausente sim; `image/png`, `application/javascript`, `text/css` não; tipo malformado (`;;`, vazio, só parâmetro) não levanta.
- `adapters/scope_proxy/test_signals.py`: corpo comum; gzip e deflate válidos; gzip truncado, corrompido e bomba de descompressão (saída limitada, memória limitada); `br` e `zstd` viram `skipped = "encoding"`; corpo acima do limite lê só o prefixo; corpo `None` e vazio; byte inválido em UTF-8.
- `adapters/scope_proxy/test_audit.py` e `test_kill_switch_and_audit_reader.py`: linha com e sem `signals` e `signal_skip`; linha antiga (sem os campos) continua legível; campo desconhecido em `AuditRecord` continua recusado; a linha nunca contém texto do corpo.
- `adapters/scope_proxy/test_engine.py`: uma resposta liberada com sinal grava a linha com a categoria e continua liberada; falha da leitura não nega nem atrasa.
- `domain/test_signal_findings.py`: agrupamento por fingerprint; fingerprint igual para ids diferentes no caminho e diferente por categoria e por método; atribuição a operação e o caso sem casamento (`generic_template`); janela (linha antes, dentro, depois); `statuses` e `query_params` limitados; zero linhas; muitas linhas.
- `domain/test_report_build.py`, `test_report_markdown.py`, `test_report_html.py`: `proxy_signals` ausente (relatório antigo), `enabled = false`, `enabled = true`; a seção de 0045 ganha a linha explicativa só quando há `proxy_signals`; achado de sinal escapado no Markdown e no HTML (nenhum valor vem do alvo, mas o título e a categoria passam pelo mesmo escape).
- `application/test_report.py`: `exceeds()` conta o achado de sinal; relatório reutiliza `error-signals.json` sem auditoria; sem auditoria e sem arquivo vira `enabled = false`; auditoria ilegível não derruba o `report` (aviso e `enabled = false`).
- `tests/contract/test_cli_scan_report.py`: o envelope do `hdast report` continua igual e `findings.json` traz os campos novos opcionais.

## Como provar no laboratório (degrau 3)

Teste `tests/integration/test_lab_error_signals.py`, marcadores `integration` e `lab_fast`, no molde de `test_lab_authz.py`: pasta descartável (`throwaway_pilot_env`), cópia do perfil da Clínica Piloto instalada e **aprovada em código** (`LabCli.approve_installed_products` / `approval_for`, no papel da pessoa), pilha **com `stack up --build`** (obrigatório: sem ele a cerca é a antiga). Para cada modo (`vulnerable` e `secure`):

1. `probe` e `scan --only buscarPacientesPorNome --max-minutes 3`, depois `report`.
2. Lê `audit.jsonl` do proxy (`proxy_audit`) e confere: o modo vulnerável do laboratório devolve rastreamento de exceção no corpo de respostas 500 e o seguro não; portanto, no vulnerável, ao menos uma linha liberada traz `signals` com `stack_trace_java`, e no seguro nenhuma traz. Se o varredor não provocar o erro nessa rodada, o programador usa o mesmo apoio de `tests/integration/path_support.py` (`via_proxy`, pelo proxy publicado em `127.0.0.1:3128`) para mandar **um** pedido que quebre a busca no vulnerável, e registra no teste qual é; o teste não depende da sorte do ZAP.
3. Confere o contrato, sem tratar a ocorrência de achado como gabarito: `error-signals.json` existe; `findings.json` traz `proxy_signals` coerente com a auditoria (a soma de `counts` bate com as linhas da janela); nenhuma linha de auditoria e nenhum arquivo da pasta contém texto do corpo (procura de um trecho conhecido da pilha de chamadas em `runs/` e no `audit.jsonl`); `responses_examined` mais `responses_skipped` é igual às linhas liberadas com `status` na janela.
4. Controle negativo: nas linhas com status 200 de JSON comum, `signals` ausente.
5. Medição de custo: a duração média por requisição na auditoria (`duration_ms`) com e sem a leitura (comparação entre a imagem nova e uma execução anterior, gravada em `HDAST_IT_METRICS_DIR`); entra no relatório da versão como número, não como asserção que falha em máquina lenta.
6. `stack down` ao fim.

O que a prova **não** cobre: o conteúdo real de um produto, respostas em `br`/`zstd` e HTTPS de um ambiente corporativo (só HTTP no laboratório).

## Limites conhecidos

- Reconhecer texto é heurística: há falso positivo (documentação com exemplo de erro) e falso negativo (mensagem traduzida, cortada, comprimida em `br`/`zstd`, ou depois dos primeiros 64 KiB). O relatório declara a contagem de respostas não lidas.
- A cerca vê a resposta como o alvo a mandou, sem redação nenhuma. Por isso nada do corpo vai para disco: só a categoria.
- O atacante, ou o próprio alvo, pode fazer um texto parecido com um sinal aparecer. O achado é `needs_triage` e de severidade baixa a média; não confirma vulnerabilidade.
- Resposta 5xx, por si, não é achado aqui.
- Só HTTP/1.1 (o proxy já recusa o restante, ADR 0017).
- Provado só no laboratório local; nenhum produto real.

## Divisão em tarefas

Uma tarefa, um programador (degrau máximo 2; o degrau 3 é do coordenador).

**T49. Cerca, achados e relatório de sinais.** Arquivos dela (nenhum outro agente os toca nesta onda):

- Novos: `src/harness_dast/domain/error_signal_catalog.py`, `src/harness_dast/domain/signal_result.py`, `src/harness_dast/domain/signal_findings.py`, `src/harness_dast/adapters/scope_proxy/signals.py`, `tests/integration/test_lab_error_signals.py`, os testes unitários listados acima.
- Alterados: `docker/scope-proxy/addon.py` (chamar o adaptador em `response`), `src/harness_dast/adapters/scope_proxy/audit.py`, `engine.py`, `audit_reader.py`, `src/harness_dast/domain/traffic.py` (`ProxyRow`), `src/harness_dast/domain/report_model.py`, `report_build.py`, `report_markdown.py`, `report_html.py`, `src/harness_dast/application/report.py`, `src/harness_dast/application/scan_ports.py` (`RunArtifacts`), `src/harness_dast/adapters/reporting/` (armazém do artefato novo), `src/harness_dast/cli/scan_composition.py` (`build_report` recebe `open_proxy_audit()`), `docker/scope-proxy/README.md`, `docs/reference/relatorio.md`, `docs/reference/finding-schema.md`.
- Não toca: `CHANGELOG.md`, `CLAUDE.md`, `docs/roadmap.md`, `docs/adr/README.md` (do coordenador).

Dependências de ordem: nenhuma. Os ADRs 0051 (relatório e `exceeds()`) esperam T49 integrada porque editam os mesmos arquivos de relatório.

## Adendo de implementação (versão 1.5, T49)

O status não muda. O que a implementação fez de diferente do texto acima, ou além dele:

- **Quarto motivo de não leitura, `error`.** `signal_skip` aceita `type`, `encoding`, `empty` e `error`. A leitura da cerca fica atrás de `read_response_signals` (`adapters/scope_proxy/signals.py`), que não levanta: qualquer falha inesperada da leitura vira `signal_skip: error` e a resposta passa do mesmo jeito (a falha aberta da seção 2). Sem esse valor a contagem de "não lidas" mentiria. O `except` largo desse ponto, e só dele, leva `noqa: BLE001` com o motivo.
- **Resposta que o alvo não devolveu.** O hook `error` do addon (destino falhou, `reason: upstream_error`, status 502) grava `signal_skip: empty`: não há corpo a ler, e a conta "lidas mais não lidas igual às linhas liberadas com status" continua fechando.
- **Catálogo refinado.** O padrão de Java também reconhece um nome de exceção com pacote (dois ou mais segmentos) seguido de `:` (por exemplo `java.lang.NullPointerException:`), e a página de depuração do Django exige a frase inteira da página de erro, não só `DEBUG = True` (que aparece em documentação). `ORA-` só vale em maiúsculas, com cinco dígitos e no começo de palavra. O "at" de uma linha de pilha também vale logo depois de `\n` ou `\t` escapados em JSON.
- **Teste de equivalência com o ADR 0045.** Os padrões genéricos de 0045 (`at x(y:12)`, `Exception:` sem pacote) são mais largos que os do catálogo; o teste cobre amostras representativas de cada forma que as duas fontes devem ver, não a inclusão de todo texto possível.
- **Teto de achados.** `findings` leva no máximo 500 achados (os de maior severidade primeiro); o excedente vai para `findings_omitted` e as contagens seguem completas. Sem teto, caminhos desconhecidos e variados inflariam o relatório. Como a ordem é por severidade, o gate nunca perde um achado que o teto cortou e que o limiar pegaria.
- **Atribuição à operação.** `AlertResolver` ganhou o método público `resolve_path(método, caminho)` (a regra de casamento é a mesma de `url_match`; `_match_url` passou a chamá-lo).
- **Janela.** Do `started_at` do `probe` ao maior `finished_at` entre `probe`, `scan` e `authz` (o `negative.json` do ADR 0051 ainda não existe: quem o criar acrescenta o `finished_at` dele em `Report._proxy_signals`). Sem instante legível, não há janela e vale o arquivo que já existe.
- **Reaproveitamento do arquivo.** O `report` só grava `error-signals.json` quando a janela tem ao menos uma resposta liberada com status; senão reaproveita o arquivo existente, e sem ele devolve `enabled: false` com a mensagem fixa (nada é gravado). Auditoria ou arquivo ilegível vira aviso no log, nunca erro do `report`.
- **Comparação.** `report --compare` cobre só os achados do ZAP; os achados de sinal não entram nela (como os do `authz`). O `notice` fixo e a documentação dizem isso.
- **Cerca antiga.** O relatório não consegue distinguir uma cerca anterior a esta versão (linhas sem `signals` nem `signal_skip`) de uma resposta lida sem sinal: é preciso `stack up --build`. Está nos limites da documentação.
- **Medida de custo.** Não foi medida (sem Docker nesta tarefa). O critério de menos de 5 ms por resposta fica para o degrau 3; a medição da duração média por requisição sai de `HDAST_IT_METRICS_DIR` em `tests/integration/test_lab_error_signals.py`.
- **Testes.** Os casos listados foram escritos em arquivos novos ao lado dos citados (`test_audit_signals.py` e `test_engine_signals.py` no lugar de acrescentar a `test_audit.py`, `test_kill_switch_and_audit_reader.py` e `test_engine.py`; `test_report_signals.py` em `domain` e em `application`), e o contrato (`test_cli_scan_report.py`) confere `proxy_signals` desligado sem pilha gerenciada.
- **Prova com Docker.** `tests/integration/test_lab_error_signals.py` foi escrito mas não rodado: o pedido que quebra a busca (`/api/pacientes/busca?nome=%27`, com o token do admin sintético) é suposição a confirmar no laboratório.

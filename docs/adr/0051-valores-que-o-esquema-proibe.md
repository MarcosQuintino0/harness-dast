# 0051. Valores que o esquema proíbe: teste negativo de validação de entrada

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** plano do ciclo V1.3 a V1.8, versão 1.5 (item "valores que o esquema proíbe"); o relatório da V1.5 entregou só o diagnóstico offline. Usa a validação do [ADR 0047](0047-validacao-offline-de-exemplos-openapi.md), o molde do estágio e da escrita do [ADR 0027](0027-teste-de-autorizacao-entre-contas.md) e do [ADR 0038](0038-authz-padrao-no-run-e-escrita-pela-carta.md), a carta do [ADR 0036](0036-carta-estruturada.md) e a aprovação do [ADR 0037](0037-aprovacao-humana-do-escopo.md).

## Contexto

O OpenAPI diz o que cada campo aceita: mínimo e máximo, tamanho, `enum`, tipo, obrigatoriedade. Hoje a ferramenta só manda valores **válidos** (`probe`, ADR 0007) e valores de ataque do ZAP, que miram injeção e não a validação do contrato. Dois defeitos reais ficam sem teste:

- **Falta de validação.** O servidor aceita (2xx) um valor que o contrato proíbe: um preço negativo, um status fora do `enum`, um texto maior que `maxLength`. O dado inválido entra no sistema e quebra regras de negócio mais adiante.
- **Erro sem tratamento.** O servidor devolve 5xx a um valor que o contrato proíbe: uma exceção que ninguém previu. É o sintoma que o ADR 0049 vê no corpo da resposta, mas só quando alguém provoca o erro.

A resposta esperada é a rejeição (4xx). Aceitar é falha; 5xx é falha.

A validação offline do ADR 0047 (`domain/schema_check.py`: `check_schema`, que devolve códigos `type`, `enum`, `length`, `range` e `required` sem repetir o valor) já sabe dizer se um valor viola o esquema. A decisão do que enviar e do que concluir pertence ao `domain`; o envio passa pelo mesmo caminho do `authz` (`OperationDispatcher` sobre `GuardedSender`: escopo, `deny_paths`, métodos, taxa, janela, prazo, trava e auditoria) e pelo proxy.

Restrições: nenhuma trava afrouxa; escrever no alvo só com a carta; `DELETE` nunca; segredo nunca em arquivo; flags só reduzem; o dado inválido aceito numa escrita precisa de limpeza ou restauração.

## Decisão

Vamos criar um **estágio novo, `negative`**, que repete, com **um valor proibido de cada vez**, os pedidos que o `probe` provou, e classifica a reação do servidor.

### 1. Onde entra: estágio próprio, não parte do `authz`

O `negative` roda **depois do `authz` e antes do `report`** no `run` (`preflight`, `probe`, `scan`, `authz`, `negative`, `report`), e também como comando solto, `hdast negative <produto> --run <run_id>`.

- **Por que não dentro do `authz`:** o `authz` compara **contas**; este teste não compara nada, usa uma conta só (a que provou o pedido). Colocá-lo lá misturaria dois assuntos sob "autorização", `--no-authz` desligaria os dois, os achados teriam a técnica `authz_*` e a seção do relatório se chamaria "Autorização entre contas". Um estágio próprio tem artefato (`negative.json`), seção e flag próprios.
- **Por que depois do `scan`:** os pedidos entram no histórico do ZAP (a rota padrão é `zap`, como a do `authz`), e `resolve_targets` (`domain/scan_plan.py`) escolhe a requisição aprendida de cada operação por método e caminho. Rodar o `negative` antes do `scan` poderia fazer a varredura partir de um valor inválido. O comando solto avisa, e o programador confere com um teste que o `scan` ignora o que o `negative` mandou (`test_scan_nao_aprende_pedido_do_negative`).
- **Por padrão ligado no `run`**, como o `authz` desde a V1.4 (a lição da V1.4: o que fica opcional, o agente não liga). Só **lê**: valores inválidos em `GET`. Escrever exige a carta (item 3). `--no-negative` o pula (`skipped`).
- **Custo da escolha:** mais um estágio em `STAGES` (`domain/run_summary.py`), no painel e no `metrics.json`. É o preço de ter fronteira clara.

### 2. O que se envia: um campo, uma classe, um valor

**Fonte do pedido válido:** `exchanges.json` do `probe` (`domain/probe_exchange.py`: método, modelo de caminho, alvo concreto com a consulta, conta, status e, para `POST`/`PUT`/`PATCH` com JSON, o corpo). **Fonte do que é proibido:** o `Operation` do OpenAPI da mesma operação (`value_schema` dos parâmetros de consulta; esquema do corpo JSON de `request_body.preferred()`), achatado por `flatten_schema`.

Onde se mexe (só aqui):

- **Parâmetros de consulta** do alvo gravado.
- **Campos de primeiro nível do corpo JSON** de `POST`, `PUT` e `PATCH`.

Onde **não** se mexe: parâmetro de caminho (trocá-lo troca o recurso e quase sempre dá 404), cabeçalho e cookie (o `exchanges.json` não os guarda), corpo de formulário e multipart (o `exchanges.json` não guarda o corpo), campo aninhado, campo `read_only`, esquema `truncated`, campo cujo esquema ainda é `one_of`/`any_of` depois de achatado. Campo cujo **nome** `classify_field_name` (`domain/authz_sensitive.py`) classifica como segredo, ou que aparece em `omitted_fields`, nunca é mexido. Em `PUT` e `PATCH`, também não se mexe no campo igual a `auth.username_field` do perfil (mudá-lo pode impedir o login da conta de teste, de que a restauração depende).

**Lista fechada de classes**, `CaseClass` em `domain/negative_values.py`:

| Classe | Valor enviado | Quando se aplica |
| --- | --- | --- |
| `below_minimum` | `minimum - 1` (ou o próprio `minimum`, se o limite é exclusivo) | número com `minimum` |
| `above_maximum` | `maximum + 1` (ou o próprio `maximum`, se exclusivo) | número com `maximum` |
| `wrong_type` | `"not-a-number"` num número; `"not-a-boolean"` num booleano; o número `12345` num texto (só no corpo JSON; na consulta todo valor já é texto) | tipo escalar sem `enum` |
| `missing_required` | o campo é **removido** | campo obrigatório de `POST` e `PUT`, ou parâmetro de consulta obrigatório; nunca em `PATCH` |
| `not_in_enum` | `"not-in-enum"` num texto; `maior valor do enum + 1` num número | campo com `enum` |
| `too_long` | `"a"` repetido `maxLength + 1` vezes | texto com `maxLength` de no máximo 1 000 |
| `too_short` | `"a"` repetido `minLength - 1` vezes (vazio se `minLength` é 1) | texto com `minLength` de pelo menos 1 |

Regras que mantêm o teste **inofensivo e atribuível**:

- Os valores são sempre ASCII simples e curtos (`MAX_VALUE_CHARS = 1_000`, `MAX_BODY_CHARS` do `exchanges.json`). **Nenhum** é carga de ataque (sem aspas, sem `<`, sem `../`, sem `%`): isto não é teste de injeção; é o ZAP que faz isso.
- **Cada valor é conferido** com `check_schema` antes de existir como caso: o código devolvido precisa ser o da classe (`range`, `type`, `enum`, `length`, `required`). Se não for (esquema que o ADR 0047 não modela, tipo `null`, formato), o caso é descartado e contado em `not_tested` com o motivo `unconfirmable`. Nunca se manda um valor que o próprio domínio não consegue dizer que é proibido.
- Um pedido muda **um** campo e deixa os demais como o `probe` provou (um fator por vez), para a reação ser atribuível.
- Formato, `pattern` e composição não são exercitados nesta decisão (limite abaixo).

**Orçamento (domínio, `NegativeConfig`):** `max_cases_per_operation` (padrão 6, de 1 a 20) e `max_requests` (padrão 200, de 1 a 1 000; conta **todo** envio do estágio, casos e restaurações). A escolha é determinística: por operação, os campos na ordem do esquema, a classe de maior prioridade primeiro (`wrong_type`, `missing_required`, `below_minimum`, `above_maximum`, `not_in_enum`, `too_long`, `too_short`) e depois uma segunda passada; entre operações, rodízio (para um orçamento curto cobrir muitas operações), leituras antes de escritas. O que o orçamento cortou vai para `not_tested` com o motivo `budget`. `POST` aceito mais de duas vezes na mesma operação (`MAX_CREATED_PER_OPERATION = 2`) encerra os casos dessa operação (`created_limit`): não se enche o ambiente de lixo.

### 3. Métodos e escrita

- **Leitura (`GET`):** sempre (é a parte ligada por padrão). `HEAD` não entra (sem corpo a concluir).
- **Escrita (`POST`, `PUT`, `PATCH`):** só com `negative.allow_writes: true` no perfil, que vem da carta. **Campo próprio, não reaproveita `authz.allow_writes`.** Justificativa: a pergunta da carta do ADR 0038 é "o teste **entre contas** pode escrever?"; esta é "o teste pode gravar **dado inválido** no ambiente?", e o risco é outro (o dado inválido aceito persiste). Uma carta pode autorizar uma e não a outra; juntar as duas faria a resposta de uma pergunta valer para a outra. Sem a autorização, cada exchange de escrita vai para `not_tested` com o motivo `writes_not_authorized` (mensagem "escrita não autorizada pela carta: negative.allow_writes") e **nada é enviado**; `--check`/flags não ligam a escrita (flags só reduzem).
- **`DELETE` nunca**: o plano descarta qualquer exchange com método fora de `GET`, `POST`, `PUT` e `PATCH`, e o domínio **recusa** um caso `DELETE` (teste que falha se alguém acrescentar).
- Nada é enviado fora do `scope.allow`/`deny_paths`: o `ScopeGuard` decide cada pedido, e o proxy também. `ScopeViolation` vira `scope_denied` em `not_tested`, não erro.

### 4. Reação: veredito no domínio

`domain/negative_verdict.py` (puro) recebe o status da resposta (e se houve) e devolve `rejected`, `accepted`, `server_error` ou `inconclusive` com motivo:

- **`rejected`** (esperado, **não é achado**): 4xx diferente dos abaixo (400, 413, 415, 422...).
- **`accepted`** (**achado**): 2xx.
- **`server_error`** (**achado**): 5xx.
- **`inconclusive`** (nada se conclui, vai para `not_tested`): 401 e 403 (`unauthorized`: a conta perdeu a permissão); 404 e 410 (`not_found`: o recurso sumiu); 405; 409 (`conflict`; em `POST` normalmente é valor único repetido: `create_conflict`); 429 (`rate_limited`); 3xx (`redirect`); sem resposta; escopo recusado; conta sem sessão.

O corpo da resposta **nunca** é gravado. Só o status entra no resultado.

**Severidade proposta (do código, nunca do agente; todo achado é `needs_triage`):**

| Reação | Em `GET` | Em `POST`, `PUT`, `PATCH` |
| --- | --- | --- |
| Aceitou valor proibido | baixa | média (baixa se a classe é `wrong_type`: aceitar `"5"` num número costuma ser coerção, não falta de validação) |
| 5xx | baixa | média (o estado do recurso pode ter ficado inconsistente) |

CWE-20 (validação de entrada imprópria) para "aceitou"; CWE-755 (tratamento impróprio de condição excepcional) para 5xx; OWASP API Top 10 2023 `API8:2023` (propostas, como nas demais técnicas).

### 5. Achados, artefato e relatório

- Técnicas novas (`NegativeTechnique`): `input_accepted` e `input_server_error`. Modelo `NegativeFinding` (`domain/negative_result.py`, congelado, de origem própria, como `AuthzFinding`): `finding_id` (`N-` e 8 hexadecimais), `fingerprint` (SHA-256 de `hdast-negative-v1`, produto, técnica, método, modelo de caminho, local `query` ou `body`, nome do campo e classe; fora: status, valor, execução), `fingerprint_version`, `origin` = `negative`, `technique`, `title`, `proposed_severity`, `cwe`, `owasp_api_2023`, `operation_id`, `method`, `path_template`, `account`, `location`, `field`, `case_class`, `declared` (o limite que o OpenAPI declara, por exemplo `minimum 1`; vem do contrato, não do alvo), `observed_status`, `baseline_status`, `restored` (`True`, `False` ou `None` se não se aplica), `created` (se um `POST` pode ter criado recurso), `evidence` (uma frase sem valor do alvo e sem o valor enviado), `description`, `solution`, `status` = `needs_triage`. **O valor enviado nunca é gravado**, só a classe.
- `negative.json` (`NegativeResult`, `schema_version` 1): `status`, `stop_message`, `started_at`, `finished_at`, `requests_sent`, `accounts`, `created_resources`, `restored_resources`, resumo por classe (`planned`, `sent`, `rejected`, `accepted`, `server_error`, `inconclusive`), `operations_tested`, `findings`, `not_tested` (operação, método, caminho, motivo, mensagem), `limits` (o que o estágio não cobre) e `notice` (zero achados não prova que a validação é boa).
- `FindingsReport` ganha `negative: NegativeResult | None` e `summary.negative_by_severity` (aditivos, como `authz_by_severity`; **não** entram em `total` nem em `by_severity`, que seguem sendo do ZAP). `exceeds()` (`application/report.py`) passa a contar os achados do `negative`, pelo mesmo critério do `authz`. O relatório ganha a seção "Valores que o esquema proíbe" (JSON, Markdown e HTML): por operação, quantos casos foram enviados, quantos o servidor rejeitou (o esperado), quantos aceitou e quantos deram 5xx. As afirmações de "o que não foi testado" (`NOT_TESTED_WITH_AUTHZ`) ganham, quando o estágio rodou, o limite de onde se mexeu.
- `run.json`: estágio `negative` (`StageRecord`), `RunOptions.negative` e `negative_findings_by_severity`.

### 6. Restauração e limpeza

- **`PUT` e `PATCH`** (só com `allow_writes`): depois de cada caso que **o servidor aceitou (2xx) ou respondeu com 5xx** (o estado é incerto), o estágio reenvia, com a mesma conta, o **corpo válido original** do `exchanges.json` (para `PATCH` é o mesmo corpo parcial do `probe`) e espera 2xx. Confirmado, `restored = True`. Se a restauração falhar ou não puder ser feita (janela fechada, prazo, parada), o resultado traz o aviso `possible_unrestored_change` em `not_tested` com o nome da conta e da operação e a dica "confira o estado e restaure por fora (reset do ambiente ou `hdast cleanup`)". Uma parada depois do envio **tenta** a restauração pelo mesmo caminho guardado (com a janela fechada nada sai), como `authz_restore.py`. A parada nunca é engolida. Não há leitura de confirmação: é um limite (abaixo).
- **`POST`:** não há valor anterior e `DELETE` é proibido. Cada `POST` aceito ou com 5xx **pode** ter criado um recurso com valor inválido: conta em `created_resources`, o achado diz `created = True`, e o relatório aponta `hdast cleanup` (o dado é sintético; a limpeza é de uma pessoa, com confirmação, ADR 0020 e 0025).
- Um caso **nunca** é enviado quando o caso anterior da **mesma operação** deixou uma restauração pendente.

### 7. Perfil e carta

**Bloco novo `negative` no `target.yml`** (`domain/negative_config.py`, `NegativeConfig(ProfileModel)`, campo `negative` em `ProductProfile`):

```yaml
negative:
  allow_writes: false          # padrão; true só vem da carta
  max_cases_per_operation: 6   # 1 a 20
  max_requests: 200            # 1 a 1000
  disabled_classes: []         # classes que não se testam (só reduz)
```

Validação: campo desconhecido, tipo errado (texto no lugar de número, booleano que não é booleano, `StrictBool`/`StrictInt`), fora da faixa, classe fora da lista fechada, classe repetida e mais de sete itens são `ConfigError` do perfil, com o caminho do campo.

**Carta:** `attack.allow_invalid_input_writes` (uma `Answer` booleana, no molde exato de `attack.allow_authz_writes`, `domain/letter_writes.py`). Ausente, nulo, `desconhecido` ou `false` valem `false`, sem pendência. `true` só passa com `source: carta` **e** `quote` não vazia (`NEGATIVE_WRITES_NEEDS_LETTER`); valor não booleano é `INVALID_VALUE`. A justificativa é a do ADR 0038: escrever dado inválido no ambiente é alargamento que só vale se a carta assinada o disser, e a frase dá à pessoa que aprova algo a conferir com o dono do produto. `hdast init --from-letter` escreve `negative:\n  allow_writes: true` **só** quando a carta autoriza; o aviso `NEGATIVE_WRITES_AUTHORIZED` (não bloqueia) lembra que o teste grava dados com valor inválido. Os demais campos do bloco (`max_*`, `disabled_classes`) **não** vêm da carta; o agente os ajusta, e o perfil os trava na aprovação (abaixo).

**Impressão digital da aprovação (ADR 0037):** o bloco `negative` **entra** (orçamento é carga; `disabled_classes` esconde achado; `allow_writes` escreve), mas, como o ADR 0038 fez com chave nova do `authz` e o ADR 0050 com chave nova do `scan`, **fica de fora enquanto for igual ao padrão**: `protected_blocks` (`domain/scope_fingerprint.py`) só inclui o bloco `negative` quando ele difere de `NegativeConfig()`, e `block_digests` e `combine_digests` só enumeram os blocos presentes. Assim um perfil sem o bloco mantém **a mesma** impressão digital e as aprovações existentes continuam valendo; mudar qualquer campo exige aprovar de novo. `BLOCKS` ganha `("negative", "teste de valores que o esquema proíbe")` para a descrição; a versão do cálculo (`FINGERPRINT_VERSION = 2`) não muda. O resumo de `hdast profile approve` ganha as linhas "VALORES INVÁLIDOS: até N pedidos, M por operação" e, com `allow_writes`, "ESCRITA DE VALOR INVÁLIDO AUTORIZADA".

### 8. Comando, estágio e artefatos novos

- `hdast negative <produto> --run <run_id> [--only OPERACAO] [--max-requests N] [--dry-run]`. Todas só **reduzem**: `--only` escolhe operações; `--max-requests` baixa o teto do perfil (acima dele é erro); `--dry-run` só planeja (os casos e o que fica sem teste, sem enviar, sem gravar, **sem pilha**, e portanto sem trava de pilha: `hold_stack(needed=not dry_run)`, como o `scan`). O estágio confere perfil, aprovação (`SCOPE_NOT_APPROVED`), janela e autorização **agora**, e o prazo é o único da execução.
- Códigos de saída: 0 (rodou, com ou sem achado: achado é dado; o dono do código 1 é o `report`); 2 configuração; 3 janela, autorização, prazo, aprovação; 5 falha do proxy do ZAP; 6 alvo sem resposta em sequência (`UNRESPONSIVE_THRESHOLD`, `domain/probe_policy.py`). `negative_stop_error` em `application/stage_errors.py`, no molde de `authz_stop_error`. Nenhum código de saída novo.
- `hdast run`: `RunRequest.negative: bool = True`, flag `--negative/--no-negative`; com `--skip-scan` o estágio é pulado com a mesma mensagem do `authz` ("depois do scan"). Se o `negative` parar antes do fim, o `report` ainda roda e o código de saída continua sendo o do `negative`.
- O estágio **tolera** `exchanges.json` ausente ou vazio dentro do `run` (`tolerate_missing_exchanges`, como o `authz`): a resposta é `not_tested` com o motivo, não derrubar a execução; o comando solto recusa (`ConfigError`).

### 9. Contrato (aditivo)

`target.yml`: bloco `negative`. `carta.yml`: `attack.allow_invalid_input_writes`. Envelope do `init --from-letter`: aviso `NEGATIVE_WRITES_AUTHORIZED`, pendência `NEGATIVE_WRITES_NEEDS_LETTER`, bloco gerado `negative.allow_writes`. Comando `hdast negative`. Artefato `negative.json`. `run.json`: estágio `negative`. `findings.json`: `negative`, `summary.negative_by_severity`. Sem mudança de `schema_version` do perfil, do relatório nem do cálculo da aprovação; sem código de saída novo. `STAGES` muda (aditivo; consumidores que enumeram estágios, como o painel e o `metrics.json`, precisam conhecer o novo).

## Alternativas consideradas

- **Dentro do `authz`, como verificação nova (`CHECK_RUNNERS`).** Reaproveita o laço, o `authz.json` e a seção do relatório, e custaria menos arquivos. Descartada: o nome "autorização entre contas" passa a mentir, `--no-authz` e `authz.disabled_checks` desligariam dois assuntos, e o achado teria técnica `authz_*`. O código do laço (`ReplaySender`, `Reply`, `StopRun`, `INTERRUPTIONS`) é reutilizado por importação, sem alterar `authz_sender.py`.
- **Reaproveitar `authz.allow_writes`.** Menos um campo na carta. Descartada pelo motivo do item 3: perguntas diferentes, riscos diferentes. Reversível por ADR novo.
- **Opcional (`--negative` desligado por padrão).** É o que falhou na V1.4. Como só lê por padrão, ligado é seguro.
- **Mandar vários valores proibidos de uma vez.** Mais rápido, mas a reação deixa de ser atribuível a um campo.
- **Gerar valores por fuzzing (aleatórios, longos, Unicode estranho).** É o trabalho do ZAP, aumenta a carga e produz falso positivo. Esta decisão manda só o mínimo que o contrato proíbe, conferido pelo próprio domínio.
- **Mexer em parâmetro de caminho e cabeçalho.** O `exchanges.json` não guarda cabeçalho, e o caminho troca o recurso. Fora desta decisão.
- **Deixar o programador ler o esquema inteiro (formato, `pattern`, `oneOf`).** `check_schema` não os modela (ADR 0047); enviar um valor que não se sabe que é proibido seria chutar. Descartada.
- **Tornar a rejeição um achado "bom" (prova de que validou).** Relatório vira ruído; a contagem de rejeições aparece como resumo, não como achado.
- **Restaurar com `DELETE`.** Proibido para sempre.

## Consequências

- O relatório passa a dizer, por operação, se o servidor valida o que o contrato proíbe, e a cobertura do que **não** foi testado (caminho, cabeçalho, formulário, aninhado, orçamento) fica escrita.
- O `run` manda pedidos a mais por padrão (no máximo `max_requests`, 200), só leituras, dentro do ritmo, do prazo e da janela. Quem não quer usa `--no-negative`.
- Com a carta autorizando a escrita, o teste altera dados sintéticos do ambiente (restaurados em `PUT`/`PATCH`, deixados em `POST`) e o aviso do `init` diz isso.
- Mais um estágio: `STAGES`, painel, `metrics.json`, skills (`run-scan`, `test-product`, `triage-findings`) e guias ganham o texto.
- Os achados de 5xx complementam o ADR 0049 (a cerca vê o conteúdo do erro nas mesmas requisições). Não há dedupe: origens diferentes, `needs_triage` nas duas.

## Casos de teste obrigatórios

Unitários e de contrato (degrau 2):

- `domain/test_negative_config.py`: padrões; faixas; `max_requests` 0, 1 001, negativo; `max_cases_per_operation` 0 e 21; `allow_writes` como texto, número, nulo (todos recusados); classe fora da lista, repetida, mais de sete; campo desconhecido; bloco que não é mapa; bloco ausente vale o padrão.
- `domain/test_negative_values.py`: cada classe com o valor esperado e **confirmado por `check_schema`**; limite exclusivo; `minimum` ausente; tipo sem classe aplicável (`boolean` sem `enum`, objeto, lista); `maxLength` acima de 1 000 e zero; `minLength` 0 (sem caso) e 1 (valor vazio); `enum` de números e de textos; `enum` vazio; esquema `truncated`; esquema composto; valores sempre ASCII e curtos; **nenhum valor contém aspa, `<`, `%`, barra ou `..`**; o valor nunca aparece em `repr` nem em `str` do caso (`repr=False`).
- `domain/test_negative_plan.py`: um fator por pedido; campo secreto, `omitted_fields`, `read_only` e `auth.username_field` em `PUT`/`PATCH` nunca mexidos; `DELETE` descartado e **caso `DELETE` recusado pelo domínio**; escrita sem `allow_writes` vira `writes_not_authorized` e nada é planejado; consulta com parâmetro repetido; corpo que não é objeto; corpo ausente em exchange de escrita; operação que sumiu do OpenAPI; exchange sem `Operation`; orçamento por operação e total (ordem determinística, rodízio, leituras antes de escritas, motivo `budget`); `MAX_CREATED_PER_OPERATION`; o mesmo plano duas vezes dá o mesmo resultado.
- `domain/test_negative_verdict.py`: tabela de status completa (200, 201, 204, 301, 400, 401, 403, 404, 405, 409, 410, 413, 415, 422, 429, 500, 502, 503, `None`); severidade por método e classe; `wrong_type` aceito em escrita é baixa.
- `domain/test_negative_findings.py`: fingerprint estável e distinto por campo, classe, local e método; o valor enviado não aparece no achado nem no `negative.json`; frase de evidência sem valor do alvo; `declared` vem do esquema.
- `domain/test_scope_fingerprint.py`: perfil sem o bloco e com o bloco igual ao padrão têm **a mesma** impressão digital de antes; qualquer mudança no bloco muda só a parte dele; voltar ao padrão volta ao resumo original; a aprovação antiga continua `approved`; ordem de `disabled_classes` não conta.
- `domain/test_letter_negative.py`, `test_letter_review.py`, `test_letter_warnings.py`, `tests/contract/test_cli_init_letter.py`: `true` com e sem `source: carta`, com e sem `quote`; texto `"sim"`, número, lista; ausente, nulo e `desconhecido`; perfil gerado sem o campo byte a byte igual ao de antes; o bloco gerado aparece em `generated_blocks`; o aviso.
- `application/test_negative.py` com falsos em memória (`tests/fakes/`): servidor falso que rejeita, que aceita, que responde 500, que responde 404/409/401; `exchanges.json` ausente, ilegível e vazio (erro no comando solto, `not_tested` no estágio do `run`); janela fechada e prazo no meio (restauração tentada, `possible_unrestored_change` quando não dá); alvo sem resposta em sequência para com 6; escopo recusado vira `scope_denied`; `--max-requests` acima do perfil é erro; `--dry-run` não envia nem grava; `--only` desconhecido é erro; segredo registrado nunca vai para `negative.json`.
- `application/test_negative_restore.py`: `PUT` aceito é seguido do reenvio do corpo original e `restored = True`; restauração que falha gera o aviso; `POST` aceito conta em `created_resources` e **nenhum** `DELETE` é enviado; um caso não parte com restauração pendente.
- `tests/contract/test_cli_negative.py`: envelope e saídas 0, 2, 3, 5, 6; `--json`; `--dry-run`; `SCOPE_NOT_APPROVED` antes de qualquer envio.
- `application/test_run.py` e `tests/contract/test_cli_run.py`: `STAGES` com `negative`; `--no-negative`; `--skip-scan`; parada do `negative` ainda gera o `report`; `run.json`.
- `domain/test_report_*`: seção nova em JSON, Markdown e HTML com e sem o estágio; relatório antigo sem o campo; `exceeds()` conta o achado; o escape dos textos.
- Teste de propriedade: para qualquer esquema gerado de campos escalares, todo caso planejado viola o esquema por `check_schema` e nenhum caso viola um campo que o plano excluiu.

## Como provar no laboratório (degrau 3)

Teste `tests/integration/test_lab_negative.py`, marcadores `integration` e `lab_fast`, no molde de `test_lab_authz.py`: pasta descartável, cópia do perfil da Clínica Piloto **aprovada em código**, uma pilha por modo (`vulnerable`, `secure`), um `probe` e um `negative`. A Clínica Piloto declara `minimum`, `enum`, `minLength`, `maxLength` e `required` em `criarConsulta`, `atualizarStatusConsulta`, `criarConvenio` e outros (`lab/pilot/openapi.json`). **Não se afirma o gabarito**: o teste prova o contrato e **grava** as observações em `HDAST_IT_METRICS_DIR/lab-negative-<modo>.json`.

1. `hdast negative clinica-piloto --run <id> --dry-run`: o plano lista casos por classe com o limite declarado; **nenhuma** linha nova no `audit.jsonl` do proxy; zero casos `DELETE`; sem `allow_writes`, os exchanges de escrita aparecem como `writes_not_authorized`.
2. Só leitura: `negative` real. Toda requisição do estágio (`operation_id` com o prefixo `negative:`, como `authz:` no `authz`) é `GET`, passa pelo proxy (linha na auditoria dele, dentro da janela do estágio) e respeita `max_requests`; o resumo por classe soma `sent`; nenhum segredo (`secret_values`, `files_containing`) nos artefatos, na saída e na auditoria; o valor enviado não está em `negative.json`.
3. Com escrita: a cópia do perfil liga `negative.allow_writes: true` (no laboratório isso faz o papel da carta, como `_install_with_writes` faz com `authz.allow_writes`; o perfil versionado não muda). Há pedidos `POST`, `PUT` e `PATCH` com o prefixo; **nenhum** `DELETE`; todo `PUT`/`PATCH` aceito ou com 5xx é seguido de um reenvio do corpo original; `created_resources` bate com os `POST` com 2xx ou 5xx. Restauração: o teste lê o recurso pela porta publicada do piloto (`direct`, de `tests/integration/path_support.py`) antes e depois do estágio e exige corpo igual nos `PUT`/`PATCH` restaurados.
4. Diferencial: nos dois modos, o número de casos `rejected`, `accepted` e `server_error` por classe é gravado nas métricas; **não** vira asserção (quem interpreta é quem lê a evidência), exceto que o modo `secure` não pode ter um achado `accepted` que o modo `vulnerable` não tenha (a verificação não pode acusar o alvo corrigido; se ocorrer, é defeito do veredito).
5. Aprovação: depois de ligar `negative.allow_writes` na cópia, o `preflight` falha com `SCOPE_NOT_APPROVED` até a aprovação em código ser refeita; sem o bloco, a aprovação antiga vale.
6. `run --skip-scan` e `run --skip-scan --no-negative` (rápidos): o estágio `negative` fica `skipped` nos dois, cada um com a sua mensagem. O fechamento da versão roda um `run` completo uma vez e registra o tempo do estágio.
7. `stack down` ao fim.

## Limites conhecidos

- Só consulta e corpo JSON de primeiro nível, nas operações com `exchanges.json`. Caminho, cabeçalho, formulário, multipart, campo aninhado, lista, `pattern`, formato, `oneOf` e `anyOf` ficam fora.
- "Aceitou" pode ser coerção legítima (um servidor que lê `"5"` como 5) ou parâmetro ignorado (um `GET` que descarta o filtro inválido). Por isso a severidade é baixa em leitura, o achado é `needs_triage` e a classe `wrong_type` é a mais fraca.
- "Rejeitou" não diz que a validação é **a do esquema**: um 400 por outro motivo (CSRF, conta) também conta como rejeição. O 401, o 403 e o 404 são `inconclusive` justamente por isso, mas um 400 de outro tipo passa.
- O 5xx pode vir do estado do alvo, não do valor. Um 5xx repetido em outro campo da mesma operação é indício mais forte, e o relatório mostra os campos.
- A restauração é de melhor esforço e não relê o recurso; `POST` deixa recurso criado (limpeza humana, `hdast cleanup`).
- Orçamento: 200 pedidos no total cobre poucas operações grandes; `not_tested` mostra o que o corte deixou.
- Provado só no laboratório local; nenhum produto real.

## Divisão em tarefas

Três pacotes, sem arquivo repetido entre os que andam juntos. A ordem importa porque o relatório e a carta são compartilhados com os ADRs 0049 e 0050.

**T51a. Domínio, perfil, carta, aprovação, aplicação e comando solto.** Onda 2 (depois das T49 e T50a integradas, porque toca `letter*.py` e `scope_fingerprint.py` e usa os mesmos artefatos).

- Novos: `src/harness_dast/domain/negative_config.py`, `negative_values.py`, `negative_plan.py`, `negative_verdict.py`, `negative_result.py`, `negative_findings.py`, `letter_negative.py`; `src/harness_dast/application/negative.py`, `negative_runner.py`, `negative_sender.py` (usa `OperationDispatcher`, `SessionPool` e importa `Reply`, `StopRun` e `INTERRUPTIONS` de `authz_sender.py`, sem alterá-lo), `negative_restore.py`, `negative_ports.py` (porta `NegativeArtifacts`, no molde de `authz_ports.py`); `src/harness_dast/cli/commands/negative.py`, `src/harness_dast/cli/negative_composition.py`; `tests/fakes/` (servidor falso do estágio); todos os testes unitários e de contrato listados.
- Alterados: `src/harness_dast/domain/profile.py` (campo `negative`), `scope_fingerprint.py` (bloco só quando difere do padrão), `scope_approval_summary.py`, `letter.py` (campo em `AttackSection`), `letter_review.py`, `letter_collect.py` (código `NEGATIVE_WRITES_NEEDS_LETTER`), `letter_warnings.py`, `src/harness_dast/application/stage_errors.py` (`negative_stop_error`), `src/harness_dast/adapters/reporting/run_files.py` (ler `exchanges.json`, gravar `negative.json`), `src/harness_dast/cli/app.py` (registrar o comando).
- Não toca: `run.py`, `run_summary.py`, `report_*`, painel (T51b).

**T51b. Estágio no `run`, relatório e painel.** Onda 3, depois da T51a e da T50b (as duas mexem em `report_build.py` e `report_model.py`).

- Alterados: `src/harness_dast/application/run.py` (estágio e `--no-negative`), `src/harness_dast/domain/run_summary.py` (`STAGES`, `StageName`, `RunOptions`, `negative_findings_by_severity`), `src/harness_dast/cli/commands/run.py`, `src/harness_dast/application/panel_live.py`, `src/harness_dast/domain/panel_*.py` que enumeram estágios (`panel_stages.py`, `panel_build_stages.py`, `panel_live.py`, `panel_summary.py`, `panel_model.py`, `panel_findings.py`, `panel_coverage.py`), `run_metrics.py`, `command_translation.py`, `report_model.py` (`negative`, `negative_by_severity`, `NOT_TESTED_WITH_AUTHZ`), `report_build.py`, `report_markdown.py`, `report_html.py`, `src/harness_dast/application/report.py` (`exceeds()` e leitura do artefato), `scan_ports.py` (`RunArtifacts`: `read_negative`), `docs/reference/relatorio.md`, `finding-schema.md`, `cli.md`, `exit-codes.md`, e os testes do item "estágio" e "relatório".
- Teste de integração: `tests/integration/test_lab_negative.py` (o programador o escreve junto da T51a; quem o roda é o coordenador).

**T51c. Documentação e skills.** Coordenador ou programador de documentação: `docs/reference/target-yml.md` (bloco `negative`), `docs/reference/` (novo `negative.md`, no molde de `authz.md`), `docs/guides/modelo-de-autorizacao.md` e `cadastrar-um-produto.md` (pergunta da carta), `.claude/skills/run-scan/SKILL.md`, `test-product/SKILL.md`, `triage-findings/SKILL.md`, `.claude/settings.json` (permitir `hdast negative`). `CHANGELOG.md`, `CLAUDE.md` (lista de comandos), `docs/roadmap.md` e `docs/adr/README.md` são do coordenador.

Dependência cruzada: o veredito do 5xx **não** usa o catálogo do ADR 0049; as duas entregas são independentes, e a T51a pode começar na onda 1 **só nos arquivos novos do domínio** (`negative_*.py`) se o coordenador quiser adiantar, desde que a parte de `scope_fingerprint.py`, `profile.py` e `letter*.py` espere a T50a.

## Adendo da T51a (implementação do núcleo)

Este adendo registra o que a T51a (domínio, perfil, carta, aprovação, aplicação e comando solto) fez além ou de modo diferente do texto acima, sem mudar a decisão nem o status.

- **Entregue:** `domain/negative_*` (config, valores, plano, pedido, veredito, resultado, achados, contagem), `letter_negative.py`, o bloco `negative` em `ProductProfile`, o campo `attack.allow_invalid_input_writes`, a impressão digital (bloco só quando difere do padrão) e o resumo da aprovação, `application/negative*`, `hdast negative` e `negative.json`. Não entram nesta tarefa, e ficam para a T51b: o estágio no `run`, `findings.json`, o relatório e o painel.
- **Campos aditivos do `negative.json`:** `operations` (uma linha por operação com casos enviados, para a seção do relatório) e `plan` (só na simulação, sem o valor). `restore_pending` é o motivo de os casos restantes de uma operação não saírem quando a restauração não se confirmou (separado de `possible_unrestored_change`, que é o aviso).
- **`not_tested` agregado:** `budget` e `unconfirmable` saem uma vez por operação, com a contagem na mensagem, e não uma linha por caso (a lista fica limitada).
- **Orçamento total:** o plano já traz no máximo `max_requests` casos; o laço ainda confere o orçamento a cada envio e reserva dois envios para um `PUT` ou `PATCH` (o caso e a restauração). Retentativas do despachante contam, e a restauração pode ultrapassar o teto por elas.
- **502, 503 e 504** seguem a tabela do ADR (5xx é `server_error`), embora o emissor também os conte como falha de transporte para o limite de alvo sem resposta. Quem triar deve desconfiar de um 5xx desses quando o alvo está instável.
- **Multipart:** o `negative` trata `exchange.multipart` preenchido (ADR 0052) como não testável (`unsupported_body`). Enquanto o campo não existir no `ExchangeRecord`, a leitura é feita pelo `__dict__` do registro; com o campo na base, vira `exchange.multipart is not None`.
- **`--only`** é conferido contra o OpenAPI (operação desconhecida é erro de configuração), não contra o `exchanges.json`.
- **Sem releitura:** a restauração só reenvia o corpo original e confere o `2xx`; não lê o recurso de volta (limite já declarado acima).

## Adendo da T51b (estágio no `run`, relatório e painel)

Este adendo registra o que a T51b fez, sem mudar a decisão nem o status.

- **Entregue:** estágio `negative` no `run` (`STAGES` agora tem seis, `RunRequest.negative`, `--negative/--no-negative`, `RunOptions.negative`, `negative_findings_by_severity`), `read_negative` em `RunArtifacts`, `FindingsReport.negative` e `summary.negative_by_severity`, a seção do relatório (`report.md` e `report.html`), `exceeds()` contando os achados, a janela dos sinais da cerca (ADR 0049) incluindo o `finished_at` do `negative.json`, `stages_seconds.negative` no `metrics.json` e o estágio no painel (aba Etapas, contagem do resumo, "O que ficou de fora", página ao vivo).
- **Mesmo molde do `authz`:** o estágio compartilha `token_cache`, `login_budget` e a trava de emergência e usa `tolerate_missing_exchanges=True`; falta de dado vira `not_tested`, não derruba o `run`. Se o `authz` ou o `negative` parar antes do fim, o `report` ainda roda e a saída é a do estágio que parou; se o `authz` parar, o `negative` não roda (fica `not_run`).
- **`NOT_TESTED_NEGATIVE`:** quando o estágio rodou, `not_tested_statements` ganha uma afirmação a mais (onde o estágio mexeu e onde não), depois das do ZAP e do `authz`. Relatório sem o estágio mantém as afirmações de antes, byte a byte.
- **`findings.json`:** o campo `negative` e `summary.negative_by_severity` são aditivos; relatório anterior sem eles continua válido (`null` e `{}`). Os achados do `negative` não entram em `findings`, `groups`, `total` nem `by_severity`.
- **Rótulos:** a seção usa `CLASS_LABEL` e `TECHNIQUE_LABEL` de `negative_findings.py` (antes privados; sem mudança de texto).
- **Painel:** o achado do `negative` não tem passo a passo de reprodução à mão (o valor enviado nunca é gravado) e não tem explicação de catálogo. A taxonomia atual não produz severidade alta, então ele só aparece na contagem; o caminho em "Falhas" existe, com confiança "a confirmar", para o caso de a taxonomia mudar.
- **Permissões:** `Bash(uv run hdast:*)` em `.claude/settings.json` já cobre `hdast negative`; nada a mudar.

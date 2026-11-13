# Referência da CLI `hdast`

Decisão: [ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md). Códigos de saída: [exit-codes.md](exit-codes.md). A tabela de status por componente fica em [../roadmap.md](../roadmap.md#tabela-de-status).

## Comandos

`version`, `init`, `profile validate`, `spec inspect`, `preflight` e `probe` existem hoje. Todos os outros são desenho aprovado e **não funcionam**.

| Comando | O que faz | Toca o alvo? | Status |
| --- | --- | --- | --- |
| `hdast version` | Mostra a versão instalada do harness | Não | Implementado (M1) |
| `hdast init <produto>` | Cria a pasta do produto a partir do modelo | Não | Implementado (M2) |
| `hdast profile validate <produto>` | Valida `target.yml` e diz se o perfil já pode ser executado agora | Não | Implementado (M2). Valida só o `target.yml`; `data-rules.yml` e `flows.yml` são conferidos por `spec inspect` |
| `hdast spec inspect <produto>` | Resume o OpenAPI para o agente e confere regras, encadeamentos, escopo e servidores | Não | Implementado (M3) |
| `hdast preflight <produto>` | Confere autorização, janela, segredos, ZAP, saúde do alvo, login e token CSRF de cada conta | Sim, mínimo | Implementado (M3) |
| `hdast probe <produto>` | Envia uma requisição válida por operação pelo ZAP e mede a alcançabilidade | Sim | Implementado (M3); verificado contra um ZAP falso, não contra o ZAP real ([roadmap](../roadmap.md)) |
| `hdast scan` | Executa a varredura do ZAP com limites fixados | Sim | Planejado (M4) |
| `hdast report` | Normaliza os alertas em achados e gera JSON e Markdown | Não | Planejado (M4) |
| `hdast cleanup` | Roda o hook de limpeza do produto para uma execução, com confirmação humana | Sim | Planejado (M5) |
| `hdast run` | Encadeia preflight, probe, scan e report sem interação | Sim | Planejado (M5) |
| Comando de parada de emergência | Interrompe a varredura e derruba os contêineres | Sim | Planejado (M5). O nome do comando ainda não foi definido |

Os marcos acima seguem o roadmap: `init` e `profile validate` no M2; `spec inspect`, `preflight` e `probe` no M3; `scan` e `report` no M4; `cleanup`, `run` e a parada de emergência no M5.

## Uso

```bash
uv run hdast --help
uv run hdast version
uv run hdast --json version
```

A saída (JSON e texto) é sempre UTF-8, qualquer que seja a página de código do terminal. `--json` pode vir **antes ou depois** do nome do comando: `hdast --json version` e `hdast version --json` fazem a mesma coisa. Mesmo um erro de uso (comando inexistente, opção desconhecida) sai como envelope JSON quando a flag está na linha. `hdast` sem argumentos mostra a ajuda e sai com `0`; com `--json` e sem comando, o resultado é um erro de uso em JSON (`CONFIG_ERROR`, saída 2), para não sujar o `stdout` com texto de ajuda. Ctrl+C encerra com o código `130` e `error.code` `INTERRUPTED`. (Antes da rodada de correção de 2026-11-13, `--json` depois do subcomando falhava em texto; achado A-03.)

## `hdast init`

```bash
uv run hdast init meu-produto                    # usa HDAST_PRODUCTS_DIR (padrão: products)
uv run hdast --json init meu-produto --products-dir ./meus-produtos
```

Cria `<products_dir>/<produto>/` copiando `products/_template/` e ajusta `product:` do `target.yml` para o nome da pasta. Regras: o nome é um slug (minúsculas, dígitos e `-`, 1 a 40 caracteres; nomes reservados do Windows como `con` são recusados); a pasta de produtos precisa existir (o comando não a cria); **nunca sobrescreve** um produto existente; nada é criado fora de `products_dir`; falha no meio da cópia remove a pasta parcial. O modelo é procurado em `products/_template` na raiz do repositório, relativo ao pacote instalado: funciona com `uv run` e instalação editável (`uv sync`); uma instalação por wheel não leva a pasta `products/` e o erro orienta a rodar a partir do repositório.

`--products-dir` sobrepõe `HDAST_PRODUCTS_DIR`. Flags só escolhem a pasta; não ampliam escopo, limites nem janela.

`data` em sucesso:

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `product` | texto | Nome do produto |
| `directory` | texto | Caminho absoluto da pasta criada (barras normais) |
| `files` | lista de texto | Arquivos criados, relativos à pasta, em ordem alfabética |

Erros (`CONFIG_ERROR`, saída 2): nome inválido, pasta de produtos inexistente, produto já existente, modelo indisponível, falha de escrita.

## `hdast profile validate`

```bash
uv run hdast profile validate meu-produto
uv run hdast --json profile validate meu-produto --products-dir ./meus-produtos
```

Lê `<products_dir>/<produto>/target.yml` e responde a duas perguntas separadas:

1. **A estrutura é válida?** Se não, o comando falha com `CONFIG_ERROR` (saída 2) e uma lista de problemas por caminho do campo. Isso inclui YAML inválido ou perigoso (âncora `&`, alias `*`, chave `<<`, chave repetida ou não textual, tag `!!`/`!` fora do esquema básico, mais de um documento, raiz que não é mapa, arquivo vazio, acima de 256 KiB ou fora de UTF-8; BOM e CRLF são aceitos), `product` diferente do nome da pasta, e `openapi` ou `cleanup.script` que, por link simbólico ou junção, saiam da pasta do produto. Nenhuma mensagem repete o conteúdo do arquivo.
2. **Pode executar agora?** Isto NÃO é erro: o comando sai com `0` e `data.runnable` diz. Cada pendência vira um item em `data.issues`.

`data` em sucesso:

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `product` | texto | Nome do produto |
| `environment_name` | texto | `environment.name` |
| `base_url_host` | texto | Só o host de `environment.base_url` |
| `allow_rules` | inteiro | Quantidade de regras em `scope.allow` |
| `deny_paths` | lista de texto | `scope.deny_paths` |
| `auth_type` | texto | `login_password` ou `api_key` |
| `accounts` | lista de `{alias, role}` | Contas por apelido e papel. **Nunca** referência, nome de variável nem valor de segredo |
| `windows` | lista de `{days, start, end, timezone, open_now}` | `days` em `seg`..`dom` (dias de início); `end` pode ser `24:00` |
| `authorization_reference` | texto | `scope.authorization.reference` |
| `authorization_valid_until` | texto | AAAA-MM-DD |
| `authorization_valid_now` | booleano | Autorização vale no instante da verificação (contagem em UTC) |
| `window_open_now` | booleano | Alguma janela aberta no instante da verificação |
| `limits` | `{requests_per_second, max_duration_minutes, zap_threads_per_host}` | Limites do perfil |
| `cleanup_configured` | booleano | Se há hook de limpeza |
| `checked_at` | texto | Instante da verificação (ISO 8601, UTC) |
| `runnable` | booleano | `true` só se `issues` estiver vazio |
| `issues` | lista de `{code, field, message}` | Pendências, abaixo |

Códigos de `issues[].code`: `PLACEHOLDER_HOST` (host ainda do modelo, como `exemplo.com.br`), `PLACEHOLDER_AUTHORIZATION` (referência `SEC-0000`), `PLACEHOLDER_SECRET_REF` (nome de variável `MEU_PRODUTO_*`), `FILE_MISSING` (`openapi` ou `cleanup.script` ainda não existe), `AUTHORIZATION_EXPIRED` e `WINDOW_CLOSED`. A existência das variáveis de ambiente dos segredos **não** é conferida aqui (o provedor de segredos é do M3). Para o modelo recém-criado por `hdast init`, o resultado é "estrutura válida, não executável", com a lista exata do que preencher.

Exemplo (resumido) para o modelo intocado:

```json
{"schema_version":1,"ok":true,"data":{"product":"demo","runnable":false,"issues":[{"code":"PLACEHOLDER_HOST","field":"environment.base_url","message":"..."},{"code":"FILE_MISSING","field":"openapi","message":"..."}]}}
```

## `hdast spec inspect`

```bash
uv run hdast --json spec inspect meu-produto
uv run hdast spec inspect meu-produto --budget 20000 --products-dir ./meus-produtos
```

Não toca o alvo. Lê o `target.yml` e o OpenAPI do produto (erro de perfil ou de OpenAPI é `CONFIG_ERROR`, saída 2) e devolve o resumo compacto da API mais verificações cruzadas. Problemas em `data-rules.yml` e `flows.yml` NÃO são erro: viram `issues`, para o agente ver tudo de uma vez. `--budget` (padrão 40000, de 2000 a 200000) limita o tamanho do JSON do resumo; fora do intervalo é erro de uso (saída 2).

`data` em sucesso:

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `product` | texto | Produto |
| `summary` | objeto | Resumo da API (`title`, `version`, `operation_count`, `omitted_operations`, `operations[]` com entradas obrigatórias, ids produzidos e consumidos). Textos vêm do OpenAPI (não confiáveis) e são cortados |
| `servers_out_of_scope` | lista de texto | Servidores do OpenAPI fora de `scope.allow`. O `probe` usa só `environment.base_url`; servidor do documento nunca define o escopo |
| `not_sent` | lista de `{operation_id, method, path, reason, message}` | Operações que o `probe` nunca enviará com as opções padrão: `skipped_scope` (fora de `scope.allow`), `skipped_denied` (em `deny_paths`), `skipped_destructive` (`DELETE`) |
| `suspicious_operations` | lista de texto | Operações cujo nome sugere reiniciar ou apagar dados (`createdb`, `reset`...): candidatas a `scope.deny_paths` (estreitar o escopo é permitido) |
| `data_rules`, `flows` | `{present, valid, count}` | Situação de cada arquivo |
| `unused_rules` | lista de `{number, field, operation}` | Regras que não casam com campo algum do OpenAPI (costuma ser erro de digitação) |
| `needs_rule` | lista de `{operation_id, message, hint}` | Operações cuja requisição não pôde ser montada: campo obrigatório que o harness não sabe gerar (por exemplo `pattern` complexo). A dica diz que regra escrever |
| `needs_rule_unchecked` | lista de texto | Consumidores de `flows.yml`; a montagem deles depende de valores de outra operação e não é simulada aqui |
| `issues` | lista de `{code, message, hint}` | `DATA_RULES_INVALID`, `DATA_RULES_MISMATCH` (regra cita operação inexistente), `FLOWS_INVALID`, `FLOWS_MISMATCH` (operação, parâmetro ou campo inexistente) |

## `hdast preflight`

```bash
uv run hdast --json preflight meu-produto
```

Confere, sem varrer, se o `probe` pode começar. Cada verificação é um item de `data.checks`; falha de verificação NÃO é exceção. Requer `HDAST_ZAP_BASE_URL` e `HDAST_ZAP_API_KEY` (quando o ZAP a exige) e as variáveis de ambiente dos segredos do perfil. Cada requisição enviada passa pelo `ScopeGuard` e fica em `runs/<run_id>/audit.jsonl` (o preflight tem pasta de execução própria).

Verificações, na ordem: `authorization` e `window` (tipo `scope`); `secrets:<apelido>`; `zap` (versão, via API com a chave); `target_health` (um GET em `probe.health_path`, ou na raiz da `base_url`, pela rota do `probe`; sucesso é qualquer resposta abaixo de 500); por conta, `csrf:<apelido>` (quando o perfil declara `auth.csrf`) e `login:<apelido>` (só em `login_password`; o token é obtido e nunca mostrado). Se autorização ou janela falham, nenhuma requisição é enviada e as de rede aparecem como não executadas.

`data`:

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `product` | texto | Produto |
| `ready` | booleano | `true` só se todas passaram |
| `checks` | lista de `{id, ok, detail, kind}` | `kind` é `scope` ou `environment`. `detail` nunca traz segredo |
| `run_id` | texto ou ausente | Pasta de execução com a auditoria, quando algo foi enviado |
| `zap_version` | texto ou ausente | Versão do ZAP, quando ele respondeu |

**Nomes de variáveis de ambiente.** O JSON mostra o segredo como `apelido.campo` (`user_a.password`) e **não** mostra o nome da variável: o agente não precisa dele (ele o escreveu no `target.yml`). O texto para a pessoa que opera inclui o nome da variável a definir.

Saída: `0` se pronto; `3` (`SCOPE_VIOLATION`) se autorização ou janela falharam; `4` (`PREFLIGHT_FAILED`) para qualquer outra falha. Quando não está pronto, o envelope vem com `ok: false`, `error` e também `data`.

## `hdast probe`

```bash
uv run hdast --json probe meu-produto --dry-run
uv run hdast --json probe meu-produto --seed 7 --only criarPaciente --only buscarPaciente
uv run hdast probe meu-produto --include-delete --account user_a
```

Envia UMA requisição válida por operação, pelo proxy do ZAP (que a aprende), e classifica o resultado. Montagem, ordem (produtores de `flows.yml` antes dos consumidores; `DELETE` por último) e regras de dados: [data-rules-yml.md](data-rules-yml.md) e [flows-yml.md](flows-yml.md).

| Flag | Efeito |
| --- | --- |
| `--seed N` | Semente dos geradores (sem ela, sorteia; fica no manifesto). Mesma semente e mesmo relógio dão as mesmas requisições |
| `--only ID` | Executa só esta operação (repetível). Os produtores de que ela depende entram junto |
| `--dry-run` | Monta as requisições e confere o escopo, mas não envia nada, não toca o ZAP, não resolve segredos e não grava arquivos. Mostra o que SERIA enviado: nomes de campos e o gerador de cada um, nunca valores |
| `--include-delete` | Permite `DELETE`, só sobre recurso criado nesta execução (a operação precisa ser consumidora em `flows.yml` e o produtor ter tido sucesso). Sem a flag, ou sem vínculo, é `skipped_destructive` |
| `--account APELIDO` | Conta que envia (padrão: a primeira de `auth.accounts`) |

Garantias, todas em código testado: toda requisição passa pelo `ScopeGuard` ANTES de sair (fora do escopo ou em `deny_paths` nunca é enviada); autorização, janela e prazo (`limits.max_duration_minutes`) são conferidos antes de CADA requisição; a taxa respeita `limits.requests_per_second`; redirecionamentos não são seguidos; a resposta é lida até 256 KiB; o login e a busca do token CSRF saem direto, nunca pelo ZAP; 401 refaz o login uma vez; 429 espera o `Retry-After` (até 3 vezes, no máximo 30 s cada); um 403 que parece rejeição de CSRF busca o token de novo uma vez; cinco falhas de transporte seguidas (timeout, conexão recusada, 502, 503, 504) encerram o `probe`. Nenhum segredo ou token é impresso, logado ou gravado.

**Classes de resultado** (`operations[].outcome`):

| Classe | Significado |
| --- | --- |
| `success` | Enviada; 2xx e, se o perfil declara `probe.success`, sem marca de falha no corpo |
| `logical_failure` | 2xx, mas o corpo tem a marca de falha de `probe.success` (alvo que responde 200 com `"status":"fail"`) |
| `validation_error` | 400 ou 422: falta regra de dados ou valor inválido |
| `conflict` | 409: valor repetido; use `unique: true` |
| `auth_error` | 401/403 (depois do novo login, quando cabível): conta, papel ou token |
| `csrf_error` | 403 de CSRF persistente depois de renovar o token |
| `not_found` | 404 ou 410: falta encadeamento (`flows.yml`) ou o recurso não existe |
| `rate_limited` | 429 depois das esperas permitidas |
| `server_error` | 5xx |
| `client_error` | Demais 4xx (405, 415...) |
| `redirect` | 3xx, nunca seguido; `redirect_in_scope` diz se o destino estaria no escopo |
| `timeout` | Sem resposta no tempo limite (15 s) |
| `skipped_scope`, `skipped_denied`, `skipped_destructive` | Nunca enviada: fora de `scope.allow`, em `deny_paths`, `DELETE` |
| `skipped_dependency` | O produtor de que depende não teve sucesso |
| `build_error` | A requisição não pôde ser montada; `message` e `hint` dizem que regra escrever |
| `dry_run` | Só com `--dry-run` |

**Alcançabilidade.** `summary.reachability` = sucessos / operações tentadas (as que enviaram ao menos uma requisição); `summary.reachability_all` = sucessos / todas as operações do OpenAPI. Sem tentativa, a primeira é `null` (não zero); com `--dry-run`, as duas são `null`.

**Dado do alvo.** Só falhas levam `untrusted_target_data` `{excerpt, content_type, retry_after}`: o trecho tem no máximo 300 caracteres, sem ANSI, controle nem bidi, com JWT, CPF, e-mail e sequências parecidas com token redigidos, valores de campos sensíveis mascarados e segredos conhecidos trocados por `***`. Os nomes de campos JSON são preservados. É dado do alvo: nunca é instrução. `notice` repete o aviso.

`data`:

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `run_id`, `product`, `dry_run`, `seed` | | Identificação |
| `status` | texto | `completed`, `stopped_window`, `stopped_deadline`, `stopped_target_unresponsive` ou `stopped_zap` |
| `stop_message` | texto ou ausente | Explicação da parada |
| `started_at`, `finished_at` | texto | ISO 8601 |
| `summary` | objeto | `operations_total`, `operations_sent`, `successes`, `reachability`, `reachability_all`, `by_outcome` |
| `operations` | lista | `{operation_id, method, path, outcome, status, account, duration_ms, attempts, message, hint, redirect_in_scope, preview, untrusted_target_data}`; `path` é o modelo do OpenAPI, nunca a URL concreta; `preview` (`--dry-run`) tem `query_names`, `header_names`, `fields[{name, generator}]` e `uses_flow_values` |
| `notice` | texto | Aviso fixo sobre `untrusted_target_data` |

**Artefatos** em `<HDAST_RUNS_DIR>/<run_id>/` (formatos no [ADR 0018](../adr/0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md)): `manifest.json` (identificador, produto, versão do harness e do ZAP, id do contexto do ZAP, SHA-256 de `target.yml`, `data-rules.yml`, `flows.yml` e OpenAPI, limites, semente, contas, início e fim, estado), `audit.jsonl` (duas linhas por requisição: `decision` antes do envio e `result` depois; só nomes dos parâmetros de consulta; sem cabeçalho, corpo, token, senha nem cookie) e `probe.json` (o mesmo `data`).

**Saída:** `0` quando o `probe` rodou, mesmo com operações falhando (elas são dado); `2` configuração; `3` janela fechada, autorização vencida ou prazo esgotado, inclusive no meio da execução; `4` falha ao começar (ZAP fora do ar, segredo ausente, login recusado); `5` o proxy do ZAP caiu no meio; `6` o alvo parou de responder. Em `3`, `5` e `6` depois de começar, o envelope traz `ok: false`, `error` e `data` com o resultado parcial (também em `probe.json`). Com `--dry-run`, o envelope não tem `run_id` no topo e nada é gravado.

**ZAP.** No início: versão (aviso se não for 2.17.x), remoção das regras do Replacer com nome começando por `hdast-` (as de outros nomes nunca), sessão nova por execução e contexto restrito aos hosts e caminhos do perfil. Configuração: [env-vars.md](env-vars.md).

## Envelope JSON

Com `--json`, o resultado vai para `stdout` como uma linha JSON. Campos sem valor são omitidos.

| Campo | Tipo | Quando aparece | Descrição |
| --- | --- | --- | --- |
| `schema_version` | inteiro | Sempre | Versão do formato do envelope. Hoje `1` |
| `ok` | booleano | Sempre | `true` em sucesso, `false` em falha |
| `run_id` | texto | Quando houver execução | Identificador da execução |
| `data` | objeto | Em sucesso | Resultado do comando |
| `error` | objeto | Em falha | Veja abaixo |

Objeto `error`:

| Campo | Descrição |
| --- | --- |
| `code` | Identificador estável do erro, em MAIUSCULAS |
| `message` | O que aconteceu |
| `hint` | O que fazer a respeito (omitido quando não há) |

Exemplo de sucesso:

```json
{"schema_version":1,"ok":true,"data":{"version":"0.1.0"}}
```

O valor de `version` acima é ilustrativo; ele vem do pacote instalado.

Exemplo de falha (ilustrativo; o cenário de escopo ainda não existe em código):

```json
{
  "schema_version": 1,
  "ok": false,
  "run_id": "2026-11-12T21-04-11Z-agenda-7f3a",
  "error": {
    "code": "SCOPE_VIOLATION",
    "message": "POST https://api.parceiro.com/v1/sms não está na lista permitida do produto agenda.",
    "hint": "Verifique scope.allow em products/agenda/target.yml. Flags não ampliam o escopo."
  }
}
```

Sem `--json`, o sucesso sai em texto no `stdout` e a falha, em texto no `stderr`.

## Valores de `error.code`

Os valores abaixo existem na hierarquia de erros do código. Novos valores entram por marco; remover ou renomear um é mudança de contrato.

| `code` | Erro | Código de saída |
| --- | --- | --- |
| `CONFIG_ERROR` | `ConfigError`: configuração, perfil ou argumento inválido (inclui erro de uso da linha de comando) | 2 |
| `SCOPE_VIOLATION` | `ScopeViolation`: ação fora do escopo, dos limites ou da janela | 3 |
| `PREFLIGHT_FAILED` | `PreflightError`: verificação anterior à execução falhou | 4 |
| `EXTERNAL_TOOL_ERROR` | `ExternalToolError`: ferramenta externa (ZAP, Docker) indisponível ou com resposta inválida | 5 |
| `TARGET_ERROR` | `TargetError`: o alvo respondeu de forma que impede o prosseguimento | 6 |
| `CLEANUP_FAILED` | `CleanupError`: a limpeza falhou | 7 |
| `INTERNAL` | Erro interno inesperado | 10 |
| `INTERRUPTED` | Interrompido pelo usuário (Ctrl+C) | 130 |

Os códigos 6 e 7 e o 130 vieram da rodada de correção de 2026-11-13 (achados A-06 e A-19), registrada no [ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md). Até então `TargetError` e `CleanupError` usavam o 5, que o desenho reserva à falha de ferramenta externa.

`CONFIG_ERROR` e `INTERNAL` vêm de qualquer comando. Com `spec inspect`, `preflight` e `probe` passam a ser produzidos também `SCOPE_VIOLATION` (3), `PREFLIGHT_FAILED` (4), `EXTERNAL_TOOL_ERROR` (5) e `TARGET_ERROR` (6); em `preflight` e `probe` o envelope de falha pode trazer `data` com o resultado parcial. `CLEANUP_FAILED` ainda não é alcançado por nenhum comando.

## Regras do contrato

- `stdout` carrega só o resultado. Logs vão para `stderr`.
- Mudança incompatível no envelope exige ADR, atualização do teste de contrato e sobe a versão maior do projeto.
- Flags só reduzem escopo e limites, nunca ampliam.

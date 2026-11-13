# Referência da CLI `hdast`

Decisão: [ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md). Códigos de saída: [exit-codes.md](exit-codes.md). A tabela de status por componente fica em [../roadmap.md](../roadmap.md#tabela-de-status).

## Comandos

`version`, `init` e `profile validate` existem hoje. Todos os outros são desenho aprovado e **não funcionam**.

| Comando | O que faz | Toca o alvo? | Status |
| --- | --- | --- | --- |
| `hdast version` | Mostra a versão instalada do harness | Não | Implementado (M1) |
| `hdast init <produto>` | Cria a pasta do produto a partir do modelo | Não | Implementado (M2) |
| `hdast profile validate <produto>` | Valida `target.yml` e diz se o perfil já pode ser executado agora | Não | Implementado (M2). Hoje valida só o `target.yml`; `data-rules.yml` e `flows.yml` entram com o M3 |
| `hdast spec inspect` | Valida o OpenAPI e devolve um resumo compacto para o agente | Não | Planejado (M3) |
| `hdast preflight` | Confere autorização, janela, ZAP no ar e login de cada conta | Sim, mínimo | Planejado (M3) |
| `hdast probe` | Envia requisições válidas pelo ZAP e mede a alcançabilidade | Sim | Planejado (M3); mecanismo depende do spike do M0 |
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

Hoje só `CONFIG_ERROR` e `INTERNAL` podem ser produzidos por um comando que existe (`hdast init`, `hdast profile validate` e erro de uso). Os demais são levantados pelo domínio, mas nenhum comando os alcança ainda.

## Regras do contrato

- `stdout` carrega só o resultado. Logs vão para `stderr`.
- Mudança incompatível no envelope exige ADR, atualização do teste de contrato e sobe a versão maior do projeto.
- Flags só reduzem escopo e limites, nunca ampliam.

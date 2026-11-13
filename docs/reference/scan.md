# `hdast scan`

> **Status: Implementado (M4)**, verificado contra um ZAP falso com as formas do spike do M0, **não** contra o ZAP real. Decisão: [ADR 0022](../adr/0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md). Formatos dos arquivos: [finding-schema.md](finding-schema.md). Lista do que conferir no ZAP real: [relatorio.md](relatorio.md#o-que-ainda-precisa-ser-verificado-contra-o-zap-real).

```bash
uv run hdast --json scan meu-produto --run 2026-11-13T05-15-32Z-meu-produto-ab12 --dry-run
uv run hdast --json scan meu-produto --run <run_id> --only buscarPaciente --max-minutes 20 --threads 1
```

Roda a varredura ativa do ZAP sobre as requisições que um `probe` **da mesma execução** ensinou ao ZAP e guarda os alertas brutos (já redigidos). Não gera achados: isso é do [`report`](relatorio.md).

## Flags

| Flag | Efeito |
| --- | --- |
| `--run RUN_ID` | **Obrigatória.** O `run_id` do `probe` (real, não `--dry-run`). O `scan` grava na mesma pasta |
| `--only ID` | Varre só esta operação (repetível) |
| `--include-outcome CLASSE` | Varre também operações que o `probe` classificou assim (repetível). Lista fechada: `logical_failure`, `validation_error`, `conflict`, `not_found`, `client_error`. `success` é sempre incluído; `server_error`, `auth_error` e afins nunca |
| `--dry-run` | Mostra o plano (`data.planned`, `data.skipped`). **Não** toca o ZAP nem o alvo, não resolve segredos, não grava arquivos |
| `--max-minutes N` | Reduz o prazo total (nunca acima de `limits.max_duration_minutes`) |
| `--threads N` | Reduz as threads por host (nunca acima de `limits.zap_threads_per_host`) |
| `--account APELIDO` | Impõe uma conta a TODAS as varreduras. Sem a flag, cada requisição é varrida com a conta que a enviou no `probe` (`auth.account_map`) |
| `--products-dir` | Pasta de produtos |

Flags só reduzem. Escopo, limites e autorização vêm do perfil.

## O que o `scan` varre (e o que nunca varre)

Decisão da CLI (`domain/scan_plan.py`), com o `ScopeGuard` sobre a **URL concreta** que o ZAP aprendeu:

| Regra | Efeito |
| --- | --- |
| Só `success` do `probe` (mais a lista de `--include-outcome`) | Sem requisição válida não há o que varrer |
| `DELETE` | **Nunca** varrido |
| Login (`POST` em `auth.token_path`) | **Nunca**: milhares de senhas inválidas bloqueariam a conta |
| `deny_paths` e fora de `scope.allow` | **Nunca** (conferido de novo na URL concreta) |
| `PUT` e `PATCH` | Só sobre recurso **criado nesta execução** (a operação consome um valor de `flows.yml` cujo produtor teve sucesso) ou com `scan.mutating_methods` no perfil |
| `POST`, `GET`, `HEAD`, `OPTIONS` | Varridos (o `POST` cria dados sintéticos; o `cleanup` os apaga) |
| Sem mensagem aprendida no ZAP | Pulada (`not_learned`) |

Ordem: por conta; dentro da conta, leituras, depois `POST`, depois `PUT`/`PATCH`. Uma varredura do ZAP **por requisição aprendida** (método, URL e corpo exatos, sempre com `contextId`, sem recursão e sem spider). O ZAP não restringe método nem caminho do que o varredor GERA: isso é do proxy de escopo ([ADR 0017](../adr/0017-proxy-de-escopo-com-scopeguard.md)); o `scan` só decide o que pede.

## Política e limites (sempre explícitos)

Antes da primeira varredura o ZAP recebe: `threadPerHost` (`limits.zap_threads_per_host`), `delayInMs` = `ceil(1000 / requests_per_second)`, teto de duração de cada varredura (menor entre `scan.max_scan_minutes` e o que resta do prazo) e de cada regra, `TargetParamsInjectable` = 51 (injeção em caminho ligada) e a política `hdast-scan`, recriada a cada execução. Bloco `scan` do perfil ([target-yml.md](target-yml.md#scan-opcional)).

**Regras desligadas por padrão** (o perfil só acrescenta, nunca reativa):

| Id | Regra | Por quê |
| --- | --- | --- |
| 40044 | Exponential Entity Expansion (Billion Laughs) | Negação de serviço por desenho |
| 30001 | Buffer Overflow | Cargas enormes para travar o processo; sem valor em API REST |
| 30002 | Format String Error | Cargas de formatação que podem derrubar o processo |
| 10104 | User Agent Fuzzer | Repete cada requisição com dezenas de User-Agent: carga sem achado útil |
| 40043 | Log4Shell | Depende de retorno externo (OAST) que o proxy nega; só gera carga |
| 90034 | Cloud Metadata Potentially Exposed | Pede endereços de metadados de nuvem: fora do escopo |
| 40035, 40032, 40034, 10095 | Hidden File Finder, `.htaccess`, `.env`, Backup File | Adivinham centenas de caminhos novos no host |

Os ids vêm da documentação do ZAP e **precisam ser conferidos** no ZAP real. O adaptador lê a política de volta (`ascan/view/scanners`) e recusa a execução (saída 4) se uma regra que devia estar desligada continua ligada.

## Token (Replacer)

A CLI faz o login (mesma sessão e mesmo orçamento de login do `probe`), instala regras do Replacer com nome `hdast-auth-<conta>-<geração>-<n>`, `matchType=REQ_HEADER` no cabeçalho de autenticação do perfil e `url` restrita à origem do alvo, e **renova** por `addRule` da geração nova antes de `removeRule` da antiga quando passa `scan.token_refresh_seconds` (mínimo `60 / auth.login_limit.max_per_minute`) ou o JWT está a menos de 30 s de expirar. **Remove tudo ao fim**, em sucesso, erro e Ctrl+C: primeiro pelo nome, depois uma varredura por prefixo `hdast-`.

**CSRF por cookie duplicado:** duas regras extras por geração: `REQ_HEADER` para o cabeçalho (`X-XSRF-TOKEN`) e `REQ_HEADER_STR` com regex que troca só `XSRF-TOKEN=valor` dentro do `Cookie`. O Replacer não consegue *acrescentar* um cookie ausente: se a requisição aprendida não tinha o cookie, essa regra não faz nada. **Marcado: a verificar no ZAP real.**

## Parada, prazo e saúde do alvo

- Antes de cada varredura e a cada consulta (2 s): janela, autorização, prazo (`RunGate`), saúde do alvo e renovação do token.
- **Janela fechada ou prazo esgotado**: a varredura em curso é parada (`ascan/action/stop`), o parcial é gravado e a saída é `3`.
- **Corte pelo ZAP** (`maxScanDuration`): o estado do ZAP é `FINISHED` com `progress` menor que 100; a CLI marca `truncated`.
- **Alvo saturado**: um `GET` barato no escopo (`probe.health_path` ou a raiz) entre as varreduras e a cada 30 s durante uma varredura. Três falhas seguidas (transporte, 502, 503, 504), com 10 s entre elas, param tudo: saída `6`. Sem GET de saúde no escopo a guarda fica desligada e `data.health.enabled` diz `false`.
- **Ctrl+C**: para a varredura, remove as regras e política, escreve `scan-progress.json` com `status: interrupted` e sai com `130`. Não grava `scan.json`.

## `data` e saída

`data` é o `scan.json` (campos em [finding-schema.md](finding-schema.md#scanjson)). Sem `--dry-run`, o envelope traz `run_id`. Progresso observável fora do envelope: `scan-progress.json` e o log estruturado no `stderr`.

| Saída | Quando |
| --- | --- |
| `0` | O `scan` rodou, mesmo com varreduras truncadas (isso é dado, em `entries[].truncated`) |
| `2` | Configuração: perfil, execução, `--run`, flags fora do intervalo |
| `3` | Autorização vencida ou janela fechada (na partida ou no meio) ou prazo esgotado. `data` traz o resultado parcial |
| `4` | Não começou: ZAP inacessível ou sem o contexto do `probe`, política recusada, segredo ausente, login recusado (também no meio: `stopped_auth`) |
| `5` | O ZAP falhou no meio, ou as regras do Replacer não puderam ser removidas ao fim (remova à mão as que começam com `hdast-`) |
| `6` | O alvo parou de responder |

O `scan` **nunca** sai com `1`: o veredito de severidade é do [`report`](relatorio.md#codigo-de-saida-1).

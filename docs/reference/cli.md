# Referência da CLI `hdast`

Decisão: [ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md). Códigos de saída: [exit-codes.md](exit-codes.md). A tabela de status por componente fica em [../roadmap.md](../roadmap.md#tabela-de-status).

## Comandos

`version`, `doctor`, `init`, `profile validate`, `profile approve`, `profile approval`, `spec inspect`, `preflight`, `probe`, `scan`, `authz`, `report`, `panel`, `run`, `cleanup`, `secret`, `stack` e `stop` existem hoje: o fluxo completo (preflight, probe, scan, report) dos marcos M1 a M5 foi verificado contra o ZAP 2.17 real ([relatório do lab](../reviews/2026-11-13-e2e-lab.md)); `doctor`, `authz`, a cerca da V1.1 e a medição foram medidos em laboratório em 2026-11-13 e 2026-11-14 ([cerca](../reviews/2026-11-13-lab-v1-1-cerca.md), [authz](../reviews/2026-11-13-lab-v1-1-authz.md)); `panel`, o diário de comandos, os índices e a página ao vivo (V1.2) existem como código e testes, **sem prova com Docker** (veja as seções V1.1 e V1.2 do [roadmap](../roadmap.md)). Nada foi provado contra produto real.

| Comando | O que faz | Toca o alvo? | Status |
| --- | --- | --- | --- |
| `hdast version` | Mostra a versão instalada do harness | Não | Implementado (M1) |
| `hdast doctor [produto]` | Responde "está tudo pronto para começar?": Python, `uv`, pasta de produtos, Docker, imagens, portas fixas, validade da pilha atual e, com produto, perfil, autorização, janela e presença das variáveis de segredo | Não (só lê a máquina) | Implementado ([ADR 0028](../adr/0028-facilitar-o-uso-doctor-setup-path-allow-local-init-e-prazo-da-pilha.md)). Seção abaixo |
| `hdast init <produto>` | Cria a pasta do produto a partir do modelo | Não | Implementado (M2) |
| `hdast profile validate <produto>` | Valida `target.yml` e diz se o perfil já pode ser executado agora | Não | Implementado (M2). Valida só o `target.yml`; `data-rules.yml` e `flows.yml` são conferidos por `spec inspect` |
| `hdast profile approve <produto>` | A PESSOA aprova os blocos de proteção do perfil (endereço, o que pode, o que é proibido, modo de caminho, janela, validade, limites, contas e papéis, força): mostra o resumo e exige que ela digite o nome do produto. Só em terminal interativo, sem `--json`. Sem ela, os comandos que tocam o alvo recusam | Não | Implementado (V1.3, [ADR 0037](../adr/0037-aprovacao-humana-do-escopo.md), proposto). Seção abaixo |
| `hdast profile approval <produto>` | Diz se o escopo está aprovado, alterado desde a aprovação (e quais blocos) ou nunca aprovado; só lê, liberado ao agente | Não | Implementado (V1.3, ADR 0037) |
| `hdast spec inspect <produto>` | Resume o OpenAPI para o agente e confere regras, encadeamentos, escopo e servidores | Não | Implementado (M3) |
| `hdast preflight <produto>` | Confere autorização, janela, segredos, ZAP, saúde do alvo, login e token CSRF de cada conta | Sim, mínimo | Implementado (M3) |
| `hdast probe <produto>` | Envia uma requisição válida por operação pelo ZAP e mede a alcançabilidade | Sim | Implementado (M3); verificado contra o ZAP real (VAmPI e Clínica Piloto) |
| `hdast scan <produto> --run ID` | Varre com o ZAP, uma requisição aprendida por vez, as operações que o `probe` alcançou, com limites e política fixados antes | Sim | Implementado (M4); verificado contra o ZAP 2.17 real. Referência: [scan.md](scan.md) |
| `hdast authz <produto> --run ID` | Teste de autorização entre contas, determinístico e sem ZAP: repete com outras contas os pedidos que o `probe` provou (BOLA, BFLA), confere campos fora do esquema e testa atribuição em massa; grava `authz.json` | Sim | Implementado ([ADR 0027](../adr/0027-teste-de-autorizacao-entre-contas.md)); verificado na Clínica Piloto local (H5, H6, H7); BFLA vertical sem prova. Referência: [authz.md](authz.md) |
| `hdast report <produto> --run ID` | Normaliza os alertas em achados e gera `findings.json`, `report.md` e `report.html`; dono do código de saída `1` | Não | Implementado (M4). Referência: [relatorio.md](relatorio.md); formatos: [finding-schema.md](finding-schema.md) |
| `hdast panel <produto> [--run ID]` ou `hdast panel --index` | Gera as páginas HTML do painel da execução (`summary`, `stages`, `findings`, `coverage`, `terminal`, `time-and-tokens`) em `runs/<run_id>/panel/` e refaz os índices `runs/index.html` e `runs/history-<produto>.html`; `report` e `run` também os geram no fim, e o `run` grava `panel/live.html` durante o teste. Sem `--run`, usa a execução mais recente do produto. `--index` sozinho só refaz os índices | Não | Implementado ([ADR 0032](../adr/0032-painel-da-execucao.md), proposto); as seis abas estão desenhadas. Seção abaixo |
| `hdast cleanup <produto> --run ID` | Roda o hook de limpeza do produto para uma execução, com confirmação humana | Não (só o banco de testes) | Implementado (M5), verificado contra um Oracle Free real; `--dry-run`; só uma pessoa em terminal interativo apaga ([ADR 0025](../adr/0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md)) |
| `hdast secret set\|list\|delete` | A pessoa grava, lista e remove segredos do cofre de credenciais do sistema (`secret_ref: keyring:NOME`); nunca mostra valor. Gravar e remover só em terminal interativo | Não | Implementado ([ADR 0030](../adr/0030-cofre-de-credenciais-do-sistema-keyring.md)); ainda não verificado no cofre real de uma máquina. Seção abaixo |
| `hdast run <produto>` | Encadeia preflight, probe, scan, authz (ligado por padrão, `--no-authz` o pula) e report num só processo, sem interação, e grava `run.json`; nunca roda a limpeza | Sim | Implementado (M5). Seção abaixo |
| `hdast stack up <produto>` | Gera a política do proxy de escopo a partir do perfil e sobe ZAP, proxy, ponte do proxy e o alvo de laboratório | Não (sobe contêineres locais) | Implementado ([ADR 0019](../adr/0019-pilha-gerenciada-politica-por-execucao-e-login-pelo-proxy.md)) |
| `hdast stack status` / `hdast stack down` | Mostra a pilha (serviços, política, auditoria, trava) / derruba o que o `up` subiu | Não | Implementado |
| `hdast stop` | Trava de emergência: cria o `KILL` do proxy e para as varreduras do ZAP; funciona com o ZAP fora do ar | Não | Implementado |

Os marcos acima seguem o roadmap: `init` e `profile validate` no M2; `spec inspect`, `preflight` e `probe` no M3; `scan` e `report` no M4; `cleanup`, `run` e a parada de emergência no M5.

**Aprovação do escopo (ADR 0037).** `preflight`, `probe`, `scan`, `authz`, `run`, `cleanup` e `stack up` só carregam o perfil se uma pessoa aprovou os blocos de proteção (`hdast profile approve`) e eles não mudaram desde então; senão recusam com `SCOPE_NOT_APPROVED` (saída `3`) antes de abrir qualquer conexão. `stack down`, `stack status` e `stop` nunca são bloqueados.

## `hdast panel`

`hdast panel <produto> [--run ID] [--products-dir DIR] [--json]` lê os arquivos da execução (`run.json`, `manifest.json`, `probe.json`, `scan.json`, `findings.json`, `authz.json`, `metrics.json`: todos opcionais), o perfil e o OpenAPI do produto e grava seis páginas HTML em `runs/<run_id>/panel/`. Sem rede, sem ZAP, sem JavaScript e sem recurso externo; todo texto do alvo é escapado. A página de entrada é `summary.html`; abra no navegador. A aba Terminal lê o diário de comandos da pasta de estado (`HDAST_STATE_DIR`); sem diário para o teste, ela diz que o diário começou na versão 1.2. Dado que falta aparece como "não medido", nunca como zero. Tema escuro, e o claro segue o aparelho.

`data` do envelope: `run_id`, `product`, `directory` (`panel`), `entry` (`panel/summary.html`), `files`, `verdict` (`finished`, `partial` ou `error`: como o teste terminou, nunca "seguro"), `severe_findings` (ou `null` sem `findings.json`), `sources` (arquivos lidos) e `missing` (arquivos não encontrados). Saídas: `0` com as páginas gravadas; `2` para execução inexistente, de outro produto, sem nenhum arquivo conhecido, `run_id` inválido ou falha de escrita. Falha ao gerar o painel dentro de `report` ou `run` nunca muda o resultado deles: vai para o log.

**Índices** ([ADR 0034](../adr/0034-indices-do-painel-e-pagina-ao-vivo.md)): toda geração de painel refaz `runs/index.html` (um cartão por produto: último teste, falhas graves, validade da carta quando o perfil pode ser lido; mais os últimos dez testes) e `runs/history-<produto>.html` (data, hora, o que rodou, funções atacadas, falhas graves, o que mudou desde o teste anterior do mesmo tipo, duração, tokens e como terminou; gráfico das falhas graves por varredura). `hdast panel --index` (sozinho: sem produto e sem `--run`) refaz só os índices e devolve `data.indexes`; com o produto ou `--run` é erro (`2`). Execução ilegível ou de versão antiga vira linha "sem dados" (ou "dados incompletos"); nunca some nem derruba o índice. O caminho do alto de toda página (`hdast / Produto / data`) é link relativo para esses arquivos. `data.indexes` também sai no comando com produto.

**Página ao vivo:** durante `hdast run`, a CLI regrava `runs/<run_id>/panel/live.html` a cada mudança de etapa e a cada função da varredura (a partir do fim do `preflight`, quando a pasta passa a existir). A página se recarrega sozinha (`<meta http-equiv="refresh" content="15">`, sem JavaScript), mostra o horário da última gravação e o aviso de como parar (`hdast stop`). Ao fim do `run` é regravada uma última vez, sem recarga, ligando para `summary.html` e `stages.html`. Falha ao gravá-la vai para o log (`panel_live_not_written`) e não muda o resultado do `run`.

## `hdast run`

```bash
uv run hdast --json run meu-produto
uv run hdast run meu-produto --skip-scan --seed 7              # só preflight + probe (laço das regras de dados)
uv run hdast run meu-produto --fail-on high --compare <run_id>  # gate de severidade e comparação
uv run hdast run meu-produto --max-minutes 20
```

Caso de uso `RunPipeline` ([ADR 0024](../adr/0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md)). Roda `preflight`, `probe`, `scan`, `authz` (ligado por padrão desde a V1.4, [ADR 0038](../adr/0038-authz-padrao-no-run-e-escrita-pela-carta.md)) e `report` **no mesmo processo**: um cache de tokens e um orçamento de login compartilhados (cada conta loga uma vez), sem perguntas. Para no primeiro estágio que falha e sai com o código **dele**; o `report` é o único dono do código `1`.

| Flag | Efeito |
| --- | --- |
| `--seed N` | Semente dos geradores do `probe` |
| `--skip-scan` | Para depois do `probe`; `scan`, `authz` e `report` ficam `skipped` |
| `--authz` / `--no-authz` | O estágio `authz` (teste de autorização entre contas), depois do `scan` e antes do `report` ([authz.md](authz.md)), **vem ligado**: por padrão só lê (`horizontal`, `excessive_data` e `vertical` em `GET`/`HEAD`); a atribuição em massa e os métodos de escrita só rodam com `authz.allow_writes` no perfil, que vem da carta. `--no-authz` o pula (consta como `skipped`; é redução). `--authz` continua aceito por compatibilidade e é redundante. Com `--skip-scan` ele também fica `skipped`. Sem contas ou pedidos suficientes o estágio não derruba o `run`: as verificações vão para `not_tested` com o motivo. Se ele parar antes do fim, o `report` ainda roda e a saída é a do `authz` |
| `--fail-on {none,low,medium,high}` | Limiar do `report`; achado no limiar ou acima sai com `1`. **Só endurece** `scan.fail_on` do perfil: `--fail-on none` com um perfil `high` continua `high` (flags só reduzem). Severidade que a CLI não soube classificar (`unknown`) conta como acima de qualquer limiar diferente de `none` |
| `--compare RUN_ID` | Comparação do `report` com outra execução do mesmo produto |
| `--max-minutes N` | Reduz o prazo da execução inteira (conta o tempo já gasto; nunca acima do perfil, mínimo 1 min para o `scan`) |
| `--products-dir` | Pasta de produtos |

**Prazo único por execução.** `limits.max_duration_minutes` (reduzido por `--max-minutes`) vale para a execução **inteira** e conta do início DELA (`run`, `probe` ou `scan`), não da subida da pilha: o `run` calcula um só prazo absoluto no início do `preflight` e o repassa ao `probe` e ao `scan`; nenhum estágio recomeça a contagem. O tempo gasto ajustando o `probe` antes do `run` não come o prazo da varredura. A pilha tem validade própria (veja `stack up`).

**Parada do `scan` não perde o relatório.** Se o `scan` parar antes do fim (prazo, janela, login, ZAP ou alvo) e tiver gravado `scan.json`, o `report` roda mesmo assim sobre o que foi coletado (`coverage.partial: true` e aviso no topo de `report.md`) e a saída final continua sendo a do estágio que parou (por exemplo `3` no prazo). Com Ctrl+C ou `hdast stop` (`130`) o `report` não roda. Com a trava acionada, só vira `130` o erro que a própria trava causou; um erro de outra origem mantém o código dele e `stop_requested: true` registra a trava.

Nunca roda `hdast cleanup`: a saída final mostra o comando exato (`hdast cleanup <produto> --run <run_id> --dry-run`), quando o perfil tem `cleanup`, para uma pessoa rodar e confirmar.

`Ctrl+C` e `hdast stop` (em outro terminal) encerram sem exceção: a varredura em curso é parada em até 2 s, as regras do Replacer são removidas, os artefatos parciais e o `run.json` são gravados e a saída é `130` (`status: interrupted`; com `hdast stop`, também `stop_requested: true`).

### `run.json` (e `data` do envelope)

Gravado na pasta do `probe` (do preflight, se o `probe` não começou). O `data` do envelope é o mesmo conteúdo, com `ok: true` (saídas `0` e `1`) ou `ok: false` e `error` (demais).

| Campo | Descrição |
| --- | --- |
| `schema_version`, `product`, `run_id` | Versão (1), produto e pasta da execução |
| `status` | `completed`, `findings` (saída 1), `failed` ou `interrupted` |
| `exit_code`, `started_at`, `finished_at`, `duration_seconds` | Resultado e tempos |
| `options` | `seed`, `skip_scan`, `authz`, `fail_on`, `compare`, `max_minutes` efetivos |
| `stages` | Sempre os cinco (`preflight`, `probe`, `scan`, `authz`, `report`), em ordem: `name`, `status` (`ok`, `failed`, `interrupted`, `skipped`, `not_run`), `exit_code`, `run_id`, `started_at`, `duration_seconds`, `error_code`, `message` |
| `artifacts` | Arquivos que existem na pasta (`probe.json`, `scan.json`, `findings.json`, `report.md`, `report.html`, `authz.json`, `rule-stats.json`, `metrics.json`...). A pasta `panel/` não aparece aqui: é uma pasta, e o `run` a gera depois de gravar este arquivo |
| `findings_by_severity` | Achados do ZAP por severidade proposta (só se o `report` rodou) |
| `authz_findings_by_severity` | Achados do estágio `authz` (técnica própria, não misturados aos do ZAP) por severidade, ou `null` se ele não rodou |
| `stop_requested` | A trava de emergência estava acionada |
| `cleanup_command` | Comando de limpeza a rodar por uma pessoa, ou `null` |

## Uso

```bash
uv run hdast --help
uv run hdast version
uv run hdast --json version
```

A saída (JSON e texto) é sempre UTF-8, qualquer que seja a página de código do terminal. `--json` pode vir **antes ou depois** do nome do comando: `hdast --json version` e `hdast version --json` fazem a mesma coisa. Mesmo um erro de uso (comando inexistente, opção desconhecida) sai como envelope JSON quando a flag está na linha. `hdast` sem argumentos mostra a ajuda e sai com `0`; com `--json` e sem comando, o resultado é um erro de uso em JSON (`CONFIG_ERROR`, saída 2), para não sujar o `stdout` com texto de ajuda. Ctrl+C encerra com o código `130` e `error.code` `INTERRUPTED`. (Antes da rodada de correção de 2026-11-13, `--json` depois do subcomando falhava em texto; achado A-03.)

## `hdast stack` e `hdast stop`

```bash
uv run hdast --json stack up vampi --products-dir ./meus-produtos      # sobe a pilha para o perfil
uv run hdast --json stack up clinica-piloto --secure --token-ttl 20     # alvo piloto em modo seguro, token de 20 s
uv run hdast --json stack up vampi --vulnerable --build                # modo vulnerável do laboratório e imagens reconstruídas
uv run hdast --json stack status
uv run hdast --json stop                                                # trava de emergência
uv run hdast --json stack down
```

Opções de `stack up`: `--vulnerable` ou `--secure` escolhem o modo do alvo de laboratório (sem nenhuma, vale o padrão dele); `--token-ttl` fixa a vida do token do alvo em segundos; `--build` reconstrói as imagens locais antes de subir (necessário depois de mudar `docker/` ou o alvo); `--oracle` e `--timeout` estão abaixo; `--products-dir` sobrepõe `HDAST_PRODUCTS_DIR`.

`stack up clinica-piloto --oracle` sobe também o Oracle Free do piloto (perfil `oracle`, banco só em `127.0.0.1:21521`, cerca de 80 s a mais) e gera as senhas; o usuário de banco da limpeza é criado por uma pessoa (`lab/pilot/cleanup/create-cleanup-user.sql`). `stack up <produto>` exige autorização válida e janela aberta (saída `3` se não). Gera `policy.json` (escopo e limites **iguais** aos do perfil; `not_after` = a VALIDADE DA PILHA: menor entre a duração máxima mais 60 minutos de folga para o ajuste do `probe`, o fim da autorização e o fechamento da janela; ela não é o prazo de uma varredura, que conta do início de cada execução e nunca passa de `max_duration_minutes`; passou de `not_after`, o proxy nega tudo e é preciso um novo `stack up`), grava o estado, e sobe com `docker compose up -d --wait --force-recreate` (prazo `--timeout`, padrão 300 s). Reconhece o alvo pelo host de `environment.base_url`: `vampi` (compose raiz, perfil `lab`) e `clinica-piloto` (projeto `hdast-pilotrun`, anexado à `hdast_lab_net`, API em `127.0.0.1:28080` e gestão em `127.0.0.1:29091`). Sem pilha gerenciada anterior nada é derrubado; com uma, ela é derrubada antes (aviso em `warnings`). Falha do Docker sai com `5` (`EXTERNAL_TOOL_ERROR`).

`data` de `stack up` e `stack status` (nunca contém a chave do ZAP nem senhas):

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `managed` | booleano | Há pilha gerenciada |
| `running` | booleano | Todos os serviços em execução |
| `product`, `run_id`, `lab_target` | texto | Produto, identificador da pilha (vai em toda linha de auditoria do proxy) e alvo anexado ou ausente |
| `not_after` | texto ISO 8601 | Prazo da política |
| `zap_url`, `auth_proxy_url` | texto | API e proxy do ZAP; proxy de escopo para login e CSRF |
| `policy_file`, `audit_file`, `state_file` | texto | Caminhos locais |
| `kill_switch` | booleano | Trava acionada |
| `services` | lista | `{project, service, state, health}` |
| `target_urls` | mapa | `api` e `management` do alvo piloto |
| `warnings` | lista de textos | Avisos |
| `lock` | objeto ou nulo | Quem ocupa a pilha agora (trava por pilha, [ADR 0035](../adr/0035-trava-por-pilha.md)): `state` (`held`, `orphan` ou `unreadable`), `command`, `product`, `lock_id`, `pid`, `started_at` e `message`; nulo com a pilha livre |

`stop` lê os `scan-progress.json` com `status: running` atualizados há até 120 s (`data.scans_running`: execução, operação, posição e percentual do que estava rodando), cria o arquivo `KILL` na pasta da política (a da pilha gerenciada, ou `HDAST_SCOPE_POLICY_DIR`) **antes** de falar com o ZAP e depois pede ao ZAP `ascan/stopAllScans`; ZAP inacessível não é erro (`zap_reachable: false`). `data`: `kill_file`, `kill_created`, `stack_managed`, `zap_reachable`, `zap_scans_stopped`, `zap_message`. O proxy nega todo pedido novo e a trava só se desfaz recriando a pilha (`stack up`). Sem pilha e sem `HDAST_SCOPE_POLICY_DIR`, sai com `2`. `stop` não derruba contêineres: use `stack down`.

Como os comandos seguintes obtêm a chave, a URL do ZAP, o proxy de login e as senhas do alvo: do ambiente `HDAST_*` quando definido; senão do `stack.json` em `HDAST_STATE_DIR` (veja [env-vars.md](env-vars.md)).

## `hdast doctor`

```bash
uv run hdast doctor                   # só a máquina
uv run hdast --json doctor meu-produto --products-dir ./meus-produtos
```

Responde "está tudo pronto para começar?" ANTES de qualquer contato com o alvo. O nome segue o costume de outras ferramentas (`brew doctor`, `flutter doctor`): diagnostica o ambiente e diz como consertar. Não envia requisição ao alvo, não sobe contêiner e nunca mostra o valor de um segredo: só diz se a variável existe. O `preflight` continua sendo a conferência COM rede (ZAP, saúde do alvo, logins); o `doctor` vem antes e não precisa da pilha no ar.

Conferências, na ordem (cada uma é um item de `data.checks`, com `status` `ok`, `warn` ou `fail`):

| `id` | O que confere | Reprova (`fail`) / avisa (`warn`) |
| --- | --- | --- |
| `python` | Python 3.12 ou mais novo | `fail`, com o comando para instalar |
| `uv` | `uv` no PATH | `warn` (os comandos `uv run hdast ...` não funcionariam) |
| `products_dir` | A pasta de produtos existe (`HDAST_PRODUCTS_DIR` ou `--products-dir`) | `fail` (tipo `config`) |
| `docker` | O Docker responde (`docker version`, prazo de 20 s) | `fail` |
| `images` | As imagens do `compose.yaml` (ZAP, pontes, proxy de escopo e, para o VAmPI, o alvo) já estão no Docker | `warn`: serão baixadas ou construídas no primeiro `stack up` |
| `port:<n>` | As portas fixas 8080 (ZAP) e 3128 (proxy) em 127.0.0.1 (ou as de `HDAST_ZAP_HOST_PORT` e `HDAST_PROXY_HOST_PORT`) estão livres; para a Clínica Piloto, também 28080 e 29091. Com pilha gerenciada no ar, porta em uso é esperada | `fail`; porta configurada que não é número de 1 a 65535 é `fail` tipo `config` |
| `stack` | Só com pilha gerenciada: se ainda vale (`not_after`) | `warn` se venceu |
| `profile` | Com produto: o perfil é válido e não tem pendências do modelo (`PLACEHOLDER_*`, `FILE_MISSING`) | `fail` (tipo `config`) |
| `authorization`, `window` | Com produto: mesma regra do `preflight` | `fail` (tipo `scope`) |
| `secrets:<apelido>` | Com produto: os segredos de `secret_ref` de cada conta existem, como variável de ambiente (`env:`) ou no cofre do sistema (`keyring:`). O nome só aparece no texto, nunca no JSON; para `keyring:` o texto traz o comando `hdast secret set NOME`. Cofre inutilizável também reprova, com a dica | `fail` |
| `path_mode` | Com produto: só aparece se o perfil tem `scope.path_mode: wide` | `warn`: o modo amplo só é seguro com `deny_paths` completo e só vale se a carta o autoriza |
| `authz_peers` | Com produto: nenhum papel tem duas contas em `auth.accounts` | `warn`: o teste de autorização horizontal (`run`, `authz`) não poderá comparar contas; com `--no-authz` nada muda |

Cada reprovação traz em `detail`, numa linha, o que houve e o que fazer. `ready` é `true` quando nada reprovou (avisos não contam).

`data`: `{product, ready, checks: [{id, status, detail, kind}], summary: {ok, warn, fail}}`. Código de saída: `0` pronto; se algo reprovou, o da primeira reprovação nesta prioridade: `scope` = `3` (`SCOPE_VIOLATION`), `config` = `2` (`CONFIG_ERROR`), demais = `4` (`PREFLIGHT_FAILED`). O envelope de falha traz `error` e `data` juntos, como no `preflight`.

## `hdast init`

```bash
uv run hdast init meu-produto                    # usa HDAST_PRODUCTS_DIR (padrão: products)
uv run hdast --json init meu-produto --products-dir ./meus-produtos
uv run hdast init meu-produto --with-cleanup    # cria também a pasta cleanup/ (limpeza de dados)
```

Cria `<products_dir>/<produto>/` copiando `products/_template/` e ajusta `product:` do `target.yml` para o nome da pasta. Regras: o nome é um slug (minúsculas, dígitos e `-`, 1 a 40 caracteres; nomes reservados do Windows como `con` são recusados); a pasta de produtos precisa existir (o comando não a cria); **nunca sobrescreve** um produto existente; nada é criado fora de `products_dir`; falha no meio da cópia remove a pasta parcial. O modelo é procurado em `products/_template` na raiz do repositório, relativo ao pacote instalado: funciona com `uv run` e instalação editável (`uv sync`); uma instalação por wheel não leva a pasta `products/` e o erro orienta a rodar a partir do repositório.

`--products-dir` sobrepõe `HDAST_PRODUCTS_DIR`. `--with-cleanup` copia também `cleanup/` (README e exemplo do script); por padrão a pasta NÃO é criada, porque a limpeza de dados é opcional e o script é de autoria humana (o bloco `cleanup` do `target.yml` do modelo continua lá: remova-o se não houver limpeza). Flags só escolhem a pasta; não ampliam escopo, limites nem janela.

`data` em sucesso:

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `product` | texto | Nome do produto |
| `directory` | texto | Caminho absoluto da pasta criada (barras normais) |
| `files` | lista de texto | Arquivos criados, relativos à pasta, em ordem alfabética |

Erros (`CONFIG_ERROR`, saída 2): nome inválido, pasta de produtos inexistente, produto já existente, modelo indisponível, falha de escrita.

### `hdast init --from-letter` (carta estruturada, ADR 0036)

```bash
uv run hdast init meu-produto --from-letter carta.yml --check    # só confere; não cria nada
uv run hdast --json init meu-produto --from-letter carta.yml     # confere e cria o produto
```

Gera o `target.yml` a partir do `carta.yml` (formulário de formato fechado, com a origem de cada resposta: `carta`, `pessoa` ou `desconhecido`; veja [modelo de autorização](../guides/modelo-de-autorizacao.md)), de modo que o agente não escreve `environment`, `openapi`, `scope`, `limits`, `auth` (tipo, login e contas) nem `scan.strength`. A criação da pasta segue as regras do `init` (nunca sobrescreve; `--with-cleanup` e `--products-dir` valem). Falha fechada: com qualquer pendência nada é criado.

- `--from-letter <carta.yml>`: caminho da carta. A geração é determinística (mesma carta, mesmo texto; sem relógio nem dependência da ordem das chaves).
- `--check`: só vale com `--from-letter`; confere a carta sem criar nada e não exige que o produto esteja livre. Sem `--from-letter` é erro de uso.

Pendências recusam a carta: portão (ambiente de teste, dados sintéticos, autorização vigente) respondido "não" ou desconhecido recusa tudo; campo obrigatório ausente ou desconhecido; valor de modelo (`exemplo.com.br`, `SEC-0000`, `MEU_PRODUTO_*`, `CHANGE_ME`); valor recusado pelos modelos do perfil; valor de segredo no lugar do NOME (`env:NOME`/`keyring:NOME`); `path_mode: wide` sem `source: carta` e `quote`; carta de outro produto; perfil gerado recusado por `ProductProfile`. Autorização com `valid_until` anterior a hoje (UTC; o último dia vale inteiro) também recusa a carta, com o código `AUTHORIZATION_EXPIRED`. A janela aberta não é conferida aqui: é do `preflight`.

**Avisos.** Com a carta pronta, `data.warnings` lista o que merece uma segunda olhada do dono do produto; **não bloqueia nem muda o perfil gerado**. O agente os mostra à pessoa na entrevista. Códigos: `ALLOW_ROOT_WILDCARD` (permissão com `/**`), `DELETE_AUTHORIZED` (método `DELETE` autorizado), `DENY_PATHS_EMPTY` (nenhum caminho proibido) e `VALIDITY_OVER_ONE_YEAR` (validade a mais de um ano).

`data` (sucesso e falha):

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `product` | texto | Nome do produto |
| `ready` | booleano | Se a carta está completa e válida |
| `check` | booleano | Se foi `--check` |
| `generated_blocks` | lista de texto | Blocos do `target.yml` gerados da carta (`environment`, `openapi`, `scope`, `limits`, `auth`, `scan.strength`); vazia com pendência |
| `issues` | lista de objetos | Pendências, uma por campo: `{field, code, message}`; `code` é `MISSING`, `UNKNOWN`, `INVALID_VALUE`, `PLACEHOLDER`, `GATE_DENIED`, `WIDE_NEEDS_LETTER`, `PRODUCT_MISMATCH`, `PROFILE_REJECTED` ou `AUTHORIZATION_EXPIRED` |
| `warnings` | lista de objetos | Avisos que não bloqueiam: `{field, code, message}` (veja abaixo); vazia com a carta recusada |
| `example_data` | lista de objetos | Dados de exemplo da carta, só informação para o agente (não viram regra) |
| `directory`, `files` | texto, lista | Só quando o produto foi criado (como no `init` simples) |

Com pendências: erro `LETTER_REJECTED` (herda de `CONFIG_ERROR`), saída 2, e o envelope traz `error` e `data` juntos. Carta ilegível ou com forma errada (YAML inválido, campo desconhecido, resposta fora de `{value, source}`): `CONFIG_ERROR`, saída 2, sem `data`.

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
| `approval` | objeto | Estado da aprovação humana do escopo (ADR 0037): `{state, approved_at, changed_blocks, message}`; veja `hdast profile approval`. **Informativo**: não entra em `runnable` nem em `issues` e nunca faz o comando falhar |

Códigos de `issues[].code`: `PLACEHOLDER_HOST` (host ainda do modelo, como `exemplo.com.br`), `PLACEHOLDER_AUTHORIZATION` (referência `SEC-0000`), `PLACEHOLDER_SECRET_REF` (nome de variável `MEU_PRODUTO_*`), `FILE_MISSING` (`openapi` ou `cleanup.script` ainda não existe), `AUTHORIZATION_EXPIRED` e `WINDOW_CLOSED`. A existência das variáveis de ambiente dos segredos **não** é conferida aqui (o provedor de segredos é do M3). Para o modelo recém-criado por `hdast init`, o resultado é "estrutura válida, não executável", com a lista exata do que preencher.

Exemplo (resumido) para o modelo intocado:

```json
{"schema_version":1,"ok":true,"data":{"product":"demo","runnable":false,"issues":[{"code":"PLACEHOLDER_HOST","field":"environment.base_url","message":"..."},{"code":"FILE_MISSING","field":"openapi","message":"..."}]}}
```

## `hdast profile approve` e `hdast profile approval`

```bash
uv run hdast profile approve meu-produto                       # a PESSOA, num terminal
uv run hdast --json profile approval meu-produto               # só leitura (liberado ao agente)
```

Decisão: [ADR 0037](../adr/0037-aprovacao-humana-do-escopo.md) (proposto). Uma pessoa aprova os **blocos de proteção** do perfil; a CLI recusa tocar o alvo se eles mudaram desde a aprovação.

**O que a aprovação trava** (impressão digital SHA-256 do perfil já validado e normalizado, um resumo por bloco; comentário, espaço e ordem de chave do YAML não contam): `environment` (nome, `base_url`, `verify_tls`), `scope.allow`, `scope.deny_paths`, `scope.path_mode`, `scope.authorization`, `scope.windows`, `limits`, `auth` (tipo, caminho do login ou cabeçalho da chave, contas por apelido, papel e **nome** de `secret_ref`, `login_limit`), `scan` inteiro, `authz` inteiro e `cleanup` inteiro (a configuração: caminho do script, **nomes** de `secret_ref`, tabelas, teto de linhas; o conteúdo do script não entra: a limpeza o confere na hora de apagar, com o hash do `--dry-run`). Entra tudo que amplia o que é tocado, com que conta, com que carga ou por quanto tempo, e tudo que reduz o que é relatado. **Não** entram, porque só ajustam alcançabilidade: `openapi`, `auth.csrf`, `auth.token_expired`, `auth.default_account`, `auth.account_map`, as opções de codificação do login e `probe`. A versão do cálculo é **2**: aprovação gravada com a versão 1 (V1.3 antes da correção do QA) vale como não aprovada. A tabela completa e o motivo de cada campo estão no ADR.

**`profile approve <produto>`**: só funciona em terminal interativo (entrada e stderr), **sem `--json`**; sem terminal ou com `--json` recusa com `CONFIG_ERROR` (saída `2`) e não grava nada. Mostra o resumo (endereço, o que pode, o que é proibido, modo de caminho, autorização, janelas, limites, contas e papéis, política da varredura, teste de autorização, limpeza) e, se havia aprovação anterior, o que mudou; a pessoa precisa **digitar o nome do produto** (outra coisa cancela: saída `0` com `approved: false`, nada gravado). Não existe flag, arquivo nem variável de ambiente que confirme no lugar dela. Perfil já aprovado e inalterado: diz isso e não pergunta. A aprovação é gravada na pasta de estado (`HDAST_STATE_DIR`), em `approvals/<produto>.json` (fora da pasta do produto e de `runs/`; sem segredo; contém produto, resumos, instante e o resumo legível).

`data` de `profile approve`: `product`, `approved` (booleano), `already_approved`, `approved_at` (ou `null`), `changed_blocks` (lista de identificadores) e `summary` (as linhas mostradas à pessoa).

**`profile approval <produto>`**: só lê. `data`: `product`, `state`, `approved_at`, `changed_blocks`, `message`. `state` é `approved`, `not_approved`, `changed` (o perfil mudou desde a aprovação; `changed_blocks` lista quais) ou `invalid` (arquivo ilegível, de versão desconhecida, de outro produto ou com resumos que não conferem: vale como não aprovado). O mesmo objeto vem em `data.approval` do `profile validate`, que não falha por causa dele.

Identificadores de bloco (`changed_blocks`): `environment`, `scope.allow`, `scope.deny_paths`, `scope.path_mode`, `scope.authorization`, `scope.windows`, `limits`, `auth`, `scan`, `authz`, `cleanup`.

**Quem confere:** `preflight`, `probe`, `scan`, `authz`, `run`, `cleanup` e `stack up`. Sem aprovação ou com o perfil alterado, o erro é `SCOPE_NOT_APPROVED` (saída `3`, a mesma da cerca; nenhum código de saída novo), com a mensagem `O perfil de <produto> mudou desde a aprovação de <instante>. Blocos alterados: scope.allow (o que pode ser alcançado)` (ou "ainda não foi aprovado por uma pessoa") e a dica de que **uma pessoa** precisa rodar `hdast profile approve <produto>`. A conferência acontece ao carregar o perfil, antes de abrir qualquer conexão. `stack down`, `stack status` e `stop` não são bloqueados.

## `hdast spec inspect`

```bash
uv run hdast --json spec inspect meu-produto
uv run hdast spec inspect meu-produto --budget 20000 --products-dir ./meus-produtos
```

Não toca o alvo. Lê o `target.yml` e o OpenAPI do produto (erro de perfil ou de OpenAPI é `CONFIG_ERROR`, saída 2) e devolve o resumo compacto da API mais verificações cruzadas. Problemas em `data-rules.yml` e `flows.yml` NÃO são erro: viram `issues`, para o agente ver tudo de uma vez. `--budget` (padrão 40000, de 2000 a 200000) limita o tamanho do JSON do resumo; fora do intervalo é erro de uso (saída 2).

Cada operação do resumo traz `multipart_offline` quando a inspeção detecta `multipart/form-data`: `true` ou `false` indica o resultado de uma prova de construção e leitura de corpo sintético em memória. São verificadas até 100 chaves de mídia de requisição com até 100 caracteres cada. Se houver mais chaves ou alguma for longa demais ou não for texto, aparece também `multipart_inspection_incomplete: true`; nesse caso, a ausência de `multipart_offline` é inconclusiva. Um resultado positivo continua válido mesmo com inspeção incompleta. A prova não valida o esquema nem envia requisições; a mídia preferida continua escolhida entre as primeiras 20 mídias representadas e o probe continua recusando multipart. Veja o [ADR 0048](../adr/0048-multipart-funcional-offline.md).

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
| `issues` | lista de `{code, message, hint}` | `DATA_RULES_INVALID`, `DATA_RULES_MISMATCH` (regra cita operação inexistente), `FLOWS_INVALID`, `FLOWS_MISMATCH` (operação, parâmetro ou campo inexistente), `ACCOUNT_MAP_MISMATCH` (`auth.account_map` cita operação inexistente) |
| `operation_accounts` | lista de `{operation_id, account}` | A conta (apelido) que enviará cada operação que o `probe` envia, segundo `auth.default_account` e `auth.account_map` |

## `hdast preflight`

```bash
uv run hdast --json preflight meu-produto
```

Confere, sem varrer, se o `probe` pode começar. Cada verificação é um item de `data.checks`; falha de verificação NÃO é exceção. Requer `HDAST_ZAP_BASE_URL` e `HDAST_ZAP_API_KEY` (quando o ZAP a exige) e as variáveis de ambiente dos segredos do perfil. Cada requisição enviada passa pelo `ScopeGuard` e fica em `runs/<run_id>/audit.jsonl` (o preflight tem pasta de execução própria).

Antes dele, `hdast doctor <produto>` confere a máquina e o perfil sem rede. Verificações, na ordem: `authorization` e `window` (tipo `scope`); `secrets:<apelido>`; `zap` (versão, via API com a chave); `target_health` (um GET em `probe.health_path`, ou na raiz da `base_url`, pela rota do `probe`; sucesso é qualquer resposta abaixo de 500); `target_setup` (só se o perfil declara `probe.setup_path`: um GET idempotente que prepara os dados, chamado uma vez, antes dos logins; reprova em 4xx e 5xx); por conta, `csrf:<apelido>` (quando o perfil declara `auth.csrf`) e `login:<apelido>` (só em `login_password`; o token é obtido e nunca mostrado). Se autorização ou janela falham, nenhuma requisição é enviada e as de rede aparecem como não executadas.

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
| `--account APELIDO` | Impõe esta conta a TODAS as operações (reduz o roteamento do perfil a uma conta). Sem a flag, cada operação usa a conta de `auth.default_account` e `auth.account_map` (padrão: a primeira de `auth.accounts`). Apelido que não existe no perfil é erro de configuração |

Garantias, todas em código testado: toda requisição passa pelo `ScopeGuard` ANTES de sair (fora do escopo ou em `deny_paths` nunca é enviada); autorização, janela e prazo (`limits.max_duration_minutes`) são conferidos antes de CADA requisição; a taxa respeita `limits.requests_per_second`; redirecionamentos não são seguidos; a resposta é lida até 256 KiB; o login e a busca do token CSRF nunca passam pelo ZAP (saem direto ou por `HDAST_AUTH_PROXY_URL`, que a pilha gerenciada aponta para o proxy de escopo); cada conta usada faz um login por execução e todo login respeita `auth.login_limit` (espera, não falha); um 401 de token vencido (`auth.token_expired`, ou qualquer 401 sem esse bloco) refaz o login uma vez por requisição; 429 espera o `Retry-After` (até 3 vezes, no máximo 30 s cada); um 403 que parece rejeição de CSRF busca o token de novo uma vez; cinco falhas de transporte seguidas (timeout, conexão recusada, 502, 503, 504) encerram o `probe`. Nenhum segredo ou token é impresso, logado ou gravado.

**Classes de resultado** (`operations[].outcome`):

| Classe | Significado |
| --- | --- |
| `success` | Enviada; 2xx e, se o perfil declara `probe.success`, sem marca de falha no corpo |
| `logical_failure` | 2xx, mas o corpo tem a marca de falha de `probe.success` (alvo que responde 200 com `"status":"fail"`) |
| `validation_error` | 400 ou 422 (ou código declarado em `probe.error_codes`): falta regra de dados ou valor inválido. O trecho traz `errors[].field` e `rule` |
| `conflict` | 409 (ou código declarado): valor repetido; use `unique: true` |
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

## `hdast cleanup`

```bash
uv run hdast cleanup meu-produto --run 2026-11-12T21-04-11Z-meu-produto-7f3a --dry-run
uv run hdast cleanup meu-produto --run 2026-11-12T21-04-11Z-meu-produto-7f3a
```

Apaga, em uma transação confirmada por uma pessoa, o lixo que uma execução deixou no banco Oracle de testes, com o SQL escrito por uma pessoa do time do produto. **O agente de IA não roda este comando.** Guia do operador, passo a passo e o que o portão de SQL garante: [operations/cleanup.md](../operations/cleanup.md); decisão: [ADR 0020](../adr/0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md).

| Flag | Efeito |
| --- | --- |
| `--run ID` | (obrigatória) A execução a limpar. Precisa existir em `HDAST_RUNS_DIR`, ser do produto e já ter terminado |
| `--dry-run` | Roda os comandos, mostra as contagens e DESFAZ tudo (`ROLLBACK`, sempre). Não apaga nada, não exige terminal e **não emite token** |
| `--products-dir DIR` | Pasta de produtos (sobrepõe `HDAST_PRODUCTS_DIR`) |

Sem `--dry-run`, só roda com terminal interativo (entrada e saída de erro): a pessoa vê o plano e **digita** o nome do produto. Não há flag, arquivo nem variável de ambiente que confirme no lugar dela; sem terminal, o comando se recusa (saída `2`). Autorização vencida é `3`; a janela de execução não é exigida.

`data`: `run_id`, `product`, `status` (`dry_run`, `committed` ou `declined`), `script_sha256`, `statement_count`, `tables`, `statements` (`{index, table, rows}`), `total_rows`, `max_rows`, `confirmation_method` (`none`, `interactive`; `token` só para quem usa o caso de uso em processo), `committed`, `rolled_back`, `started_at`, `finished_at`, `duration_ms`, `token_expires_at` (campo reservado, sem uso pela CLI). **Nunca** traz token, valores de variáveis de ligação nem credenciais. Falha de banco, teto de linhas (`cleanup.max_rows`) excedido ou erro ao conectar: `error.code = CLEANUP_FAILED`, saída `7`, mensagem com o índice do comando e a tabela, tudo desfeito.

**Artefatos** em `<HDAST_RUNS_DIR>/<run_id>/`: `cleanup.json` (o mesmo `data`), `cleanup-audit.jsonl` (linhas `started` e `finished`, também numa exceção inesperada) e `cleanup-confirmation.json` (resíduo: só o hash de um token que a CLI não expõe).

## `hdast secret`

```bash
uv run hdast secret set AGENDA_USER_A_SENHA
uv run hdast secret list meu-produto
uv run hdast secret delete AGENDA_USER_A_SENHA
```

Guarda as senhas das contas de teste no cofre de credenciais do sistema operacional, para `secret_ref: "keyring:NOME"` ([ADR 0030](../adr/0030-cofre-de-credenciais-do-sistema-keyring.md)). **O agente de IA não grava nem remove segredo**: `set` e `delete` só funcionam em terminal interativo (entrada e saída de erro) e `.claude/settings.json` os nega ao agente. Nenhum subcomando mostra o valor nem o tamanho.

| Subcomando | O que faz |
| --- | --- |
| `set NOME` | Pede o valor num prompt **oculto**, duas vezes. Nunca por argumento, variável nem entrada redirecionada; não existe `--value`. Sem terminal: recusa (`CONFIG_ERROR`, saída `2`). Valor vazio é recusado. Substitui o que já houver |
| `list PRODUTO` | Para cada `keyring:` que o perfil do produto cita: o `NOME`, os campos que o usam (`used_by`) e `present` (existe e não está vazio). Só leitura, funciona sem terminal e fica liberado ao agente. `env:` não aparece (veja o `doctor`) |
| `delete NOME` | Pede que você **digite o NOME** para confirmar. Sem terminal: recusa. Nome inexistente não pede nada e diz que não existe |

`NOME` segue o formato de `secret_ref` (maiúsculas, dígitos e `_`; sem prefixo `HDAST_`). Todos aceitam `--products-dir` (usado só pelo `list`, para achar o perfil).

`data` de `set`: `{name, replaced}`. De `delete`: `{name, removed, existed}`. De `list`: `{product, entries: [{name, used_by, present}]}`.

Só o cofre do próprio sistema é aceito (Windows Credential Manager, macOS Keychain, Secret Service ou KWallet no Linux). Sem ele (contêiner, CI), o erro é `SECRET_BACKEND_ERROR` (saída `4`) com a dica de usar `env:NOME`; nada cai em silêncio para variável de ambiente ou arquivo.

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
{"schema_version":1,"ok":true,"data":{"version":"1.3.0"}}
```

O valor de `version` acima é ilustrativo; ele vem do pacote instalado.

Exemplo de falha (ilustrativo; `preflight`, `probe`, `scan` e o proxy de escopo aplicam o `ScopeGuard` e produzem este envelope):

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
| `SCOPE_NOT_APPROVED` | `ScopeNotApproved`: nenhuma pessoa aprovou os blocos de proteção do perfil, ou eles mudaram desde a aprovação ([ADR 0037](../adr/0037-aprovacao-humana-do-escopo.md)); a mensagem diz quais blocos mudaram | 3 |
| `PREFLIGHT_FAILED` | `PreflightError`: verificação anterior à execução falhou | 4 |
| `SECRET_BACKEND_ERROR` | `SecretBackendError`: o cofre de credenciais do sistema (`keyring:`) não está utilizável | 4 |
| `EXTERNAL_TOOL_ERROR` | `ExternalToolError`: ferramenta externa (ZAP, Docker) indisponível ou com resposta inválida | 5 |
| `TARGET_ERROR` | `TargetError`: o alvo respondeu de forma que impede o prosseguimento | 6 |
| `CLEANUP_FAILED` | `CleanupError`: a limpeza falhou | 7 |
| `STACK_BUSY` | `StackBusy`: a pilha já está ocupada por outra execução (trava por pilha, [ADR 0035](../adr/0035-trava-por-pilha.md)) | 8 |
| `INTERNAL` | Erro interno inesperado | 10 |
| `INTERRUPTED` | Interrompido pelo usuário (Ctrl+C) | 130 |

Os códigos 6 e 7 e o 130 vieram da rodada de correção de 2026-11-13 (achados A-06 e A-19), registrada no [ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md). Até então `TargetError` e `CleanupError` usavam o 5, que o desenho reserva à falha de ferramenta externa.

`CONFIG_ERROR` e `INTERNAL` vêm de qualquer comando. Com `spec inspect`, `preflight` e `probe` passam a ser produzidos também `SCOPE_VIOLATION` (3), `PREFLIGHT_FAILED` (4), `EXTERNAL_TOOL_ERROR` (5) e `TARGET_ERROR` (6); em `preflight` e `probe` o envelope de falha pode trazer `data` com o resultado parcial. `hdast cleanup` produz `CLEANUP_FAILED` (saída `7`) e `hdast run` produz o código do estágio que falhou.

## Regras do contrato

- `stdout` carrega só o resultado. Logs vão para `stderr`.
- Mudança incompatível no envelope exige ADR, atualização do teste de contrato e sobe a versão maior do projeto.
- Flags só reduzem escopo e limites, nunca ampliam.

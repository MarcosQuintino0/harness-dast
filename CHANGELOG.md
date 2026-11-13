# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). O versionamento seguirá [Versionamento Semântico](https://semver.org/lang/pt-BR/); mudança incompatível no envelope JSON ou no schema do perfil sobe a versão maior. Ainda não há versão publicada.

## [Unreleased]

### Adicionado (marco M5, `hdast run`, trava de emergência e verificação no ZAP real)

- Comando `hdast run <produto>` (`--seed`, `--skip-scan`, `--fail-on`, `--compare`, `--max-minutes`): `preflight`, `probe`, `scan` e `report` em UM processo (cache de tokens e orçamento de login compartilhados), para no primeiro estágio que falha com o código dele, nunca roda a limpeza (mostra o comando) e sempre grava `run.json` (`domain/run_summary.py`). Ctrl+C e `hdast stop` encerram com saída 130. Caso de uso `RunPipeline` em `application/run.py`; tradução do estado das etapas em `application/stage_errors.py` ([ADR 0024](docs/adr/0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md)).
- Porta `KillSwitch` (`FileKillSwitch`): o `RunGate` consulta o arquivo `KILL` antes de cada envio e a cada consulta do `scan`; `hdast stop` passa a informar o que estava rodando (`scans_running`, lido de `scan-progress.json`).
- `scan.json` e `findings.json` ganham `traffic`, lido da auditoria do proxy de escopo (liberados, negados por motivo, taxa média e de pico, limite do perfil); o `report.md` diz quantas tentativas fora do escopo o proxy barrou (porta `ProxyAudit`, [ADR 0023](docs/adr/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md)).
- `hdast stack up clinica-piloto --oracle`: Oracle Free do piloto pela pilha gerenciada, com a porta do banco só em `127.0.0.1:21521` e senhas geradas; `lab/pilot/cleanup/create-cleanup-user.sql` (usuário de limpeza com SELECT e DELETE nas cinco tabelas). O perfil do piloto e o modelo de produto ganham o bloco `cleanup` completo (`connection`, `user`, `password`, `allowed_tables`, `max_rows`, `db_schema`).
- Testes de integração de ponta a ponta (`tests/integration/test_lab_run.py`, `test_run_cleanup_oracle.py`, `run_support.py`) e relatório factual do lab: [docs/reviews/2026-11-13-e2e-lab.md](docs/reviews/2026-11-13-e2e-lab.md).

### Corrigido (verificação do `scan` e do `report` contra o ZAP 2.17 real)

- O `scan` e o `report` não usavam o estado da pilha gerenciada (chave e endereço do ZAP, senhas do alvo): `scan` falhava com "chave de API errada". Agora usam a mesma configuração efetiva do `probe`.
- `ascan/action/disableScanners` recusava o pedido inteiro: o id 10095 (Backup File Disclosure) é regra passiva e não existe no varredor ativo. Removido da lista padrão; a política agora confere os ids que a imagem tem antes de desligar e cita os que faltam.
- CSRF por cookie duplicado durante a varredura: a regra `REQ_HEADER_STR` não acrescentava o cookie `XSRF-TOKEN` ausente e cerca de 6% das escritas do varredor (as das regras PHP, CVE-2012-1823) saíam sem ele e eram recusadas com `XSRF_INVALIDO`. A regra do cookie agora é um `REQ_HEADER` sobre `Cookie` (acrescenta quando falta): 547 de 547 escritas medidas com o par igual e zero recusas.
- `max_rule_minutes` podia passar do teto da execução; `--only` com `operation_id` desconhecido agora é erro de configuração em vez de plano vazio.
- Ids de regras e formas de resposta do `ascan/*`, `context/*`, `core/view/message(s)`, `alert/view/alerts` e do Replacer conferidos contra o ZAP real (lista em [docs/reference/relatorio.md](docs/reference/relatorio.md#o-que-foi-verificado-contra-o-zap-real)).
- Mapeamento CWE para OWASP API Security Top 10 2023 conferido contra as páginas oficiais (nenhuma entrada errada; fontes no docstring de `domain/finding_taxonomy.py`).

### Alterado

- ADRs 0017 a 0022 passam a "Aceito" (o aceite veio depois da implementação e da verificação no lab). Novos: [0023](docs/adr/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md) e [0024](docs/adr/0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md).
- Auxiliares da composição (`products_dir_or_default`, `harness_version`, `build_spec_loader`) deixaram de ser privados; nenhum módulo importa mais `_helper` de outro.
- Perfis de laboratório: `max_duration_minutes` do VAmPI 30 (a varredura completa passa de 15 min).
- README, SECURITY, docs de operação, testes, módulos e roadmap atualizados para o fluxo completo.

### Adicionado (marco M4, `hdast scan` e `hdast report`)

- Comando `hdast scan <produto> --run <run_id>` (`--only`, `--include-outcome`, `--dry-run`, `--max-minutes`, `--threads`, `--account`): varre com o ZAP, uma varredura por requisição aprendida (método, URL e corpo exatos, sempre com `contextId`, sem recursão e sem spider), só as operações que o `probe` alcançou. Nunca `DELETE`, o login ou caminho negado; `PUT`/`PATCH` só sobre recurso criado na execução ou com `scan.mutating_methods`. Limites (`threadPerHost`, `delayInMs`, tetos de duração) e política (`hdast-scan`, força LOW, limiar MEDIUM, injeção em caminho ligada, 10 regras destrutivas ou pesadas desligadas) fixados ANTES da primeira varredura; prazo total, janela e autorização conferidos a cada consulta; guarda de saúde do alvo (saída 6); corte do ZAP reconhecido por `progress < 100` e marcado `truncated`; token entregue pelo Replacer (renovação por adicionar-e-remover, uma conta por vez, CSRF por cookie duplicado, regras SEMPRE removidas, inclusive em erro e Ctrl+C). Artefatos `scan.json`, `scan-progress.json`, `alerts.raw.json` e `evidence.json`, todos redigidos. Referência: `docs/reference/scan.md` ([ADR 0022](docs/adr/0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md)).
- Comando `hdast report <produto> --run <run_id>` (`--compare`, `--fail-on`): sem rede, transforma os alertas em achados (`Finding` congelado, fingerprint SHA-256 versão 1 sobre produto, método, modelo de caminho da requisição aprendida resolvida por `sourceMessageId`, vetor, parâmetro, regra e CWE; deduplicação; severidade e confiança como propostas pelo ZAP; status `needs_triage`) e grava `findings.json` e `report.md` (português, escapado, com a seção fixa "O que este relatório não testou"). Triagem do agente em `triage.json` separado (não apaga nem reclassifica), comparação entre execuções (`new`, `persistent`, "não observado nesta execução", nunca "corrigido") e `curl` reproduzível com marcadores no lugar dos segredos. O `report` é o dono do código de saída `1`. Referência: `docs/reference/relatorio.md` e `docs/reference/finding-schema.md`.
- Perfil, aditivo e opcional na schema v1: bloco `scan` (`strength`, `threshold`, `url_path_injection`, `mutating_methods`, `disable_rules`, `max_scan_minutes`, `max_rule_minutes`, `token_refresh_seconds`, `fail_on`).
- Portas `ScanControl`, `RunArtifacts` e `ReportSink` (em `application/scan_ports.py`); adaptadores `adapters/zap/scan_client.py` e `adapters/reporting/`; módulos puros `domain/scan_*.py`, `redaction.py`, `finding*.py`, `triage.py`, `report_*.py` e `markdown_safe.py`. Sem dependência nova.
- Testes: unitários com falsos para os dois casos de uso, ZAP falso em HTTP real com as formas do spike (`tests/fakes/zap_scan_server.py`), contratos dos dois comandos, arquivos de referência de `findings.json` e `report.md` a partir de fixtures reconstruídas do spike (`tests/fixtures/zap_alerts/`). **Não verificado contra o ZAP real**: a lista do que conferir está em `docs/reference/relatorio.md`.

### Adicionado (marco M5, `hdast cleanup`)

- Comando `hdast cleanup <produto> --run <run_id>` (`--dry-run`, `--confirm <token>`): executa o SQL de limpeza escrito por pessoa em UMA transação no Oracle de testes e só confirma depois do aceite humano (digitar o nome do produto, ou token de uso único emitido por um `--dry-run` anterior, no stderr, nunca no JSON). Código de saída `7` (`CLEANUP_FAILED`) passa a ser produzido ([ADR 0020](docs/adr/0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md)). Guia: `docs/operations/cleanup.md`.
- Portão de SQL em `domain/cleanup_*.py` (defesa em profundidade, não prova): só `DELETE FROM <tabela> WHERE ...` em tabelas de `allowed_tables`, com condição de amarração às variáveis `:run_start`, `:run_id`, `:run_tag` e `:account_N`; recusa DDL, `TRUNCATE`, `UPDATE`, PL/SQL, `COMMIT`, link de banco, `&variável`, funções fora de uma lista fechada e Unicode que imita ASCII.
- Perfil, aditivo e opcional na schema v1: `cleanup.user`, `cleanup.password`, `cleanup.allowed_tables`, `cleanup.max_rows` e `cleanup.db_schema`; a limpeza se recusa a rodar sem os quatro primeiros. `cleanup.connection` passa a ser o DSN.
- Dependência de runtime `oracledb` (python-oracledb) 26.1.0 (UPL-1.0 OU Apache-2.0), modo thin; proibida no `domain` pelo import-linter.
- Portas `CleanupExecutor`, `CleanupSession`, `CleanupScripts`, `CleanupRuns`, `TokenSource` e `OperatorPrompt`; adaptadores `adapters/cleanup/` e falsos em `tests/fakes/cleanup_*.py`.
- Trilha em `runs/<run_id>/`: `cleanup.json`, `cleanup-audit.jsonl` e `cleanup-confirmation.json` (só o hash do token).
- Testes: portão (casos de recusa, truques de comentário, texto e `q'...'`, Unicode, propriedade com oráculo independente), plano, token, caso de uso com falsos, contrato do comando e integração contra o Oracle Free do piloto (`pytest -m integration`).

### Adicionado (integração do `probe` com o piloto: vários níveis, conta por operação, orçamento de login)

- Encadeamento em vários níveis em `flows.yml` (grafo sem ciclos; ciclo e auto-referência continuam recusados; cadeia de no máximo `MAX_FLOW_DEPTH` = 6 operações). `--only` traz os produtores em qualquer nível ([ADR 0021](docs/adr/0021-esquema-aditivo-do-perfil-para-o-alvo-piloto.md)).
- Perfil, aditivo e opcional na schema v1: `auth.default_account` e `auth.account_map` (conta por `operationId` e/ou caminho e método), `auth.login_limit.max_per_minute`, `auth.token_expired` e `probe.error_codes`. `spec inspect` devolve `operation_accounts` e o `issue` `ACCOUNT_MAP_MISMATCH`; `probe --account` impõe uma conta a todas as operações.
- Orçamento de login (janela deslizante de 60 s consultada antes de todo POST de login), um login por conta por execução, cache de tokens por processo compartilhado por `preflight` e `probe`, novo login por token vencido no máximo uma vez por requisição e `Retry-After` no login.
- Classificação exata pelo código de erro do corpo; o trecho do alvo preserva `errors[].field` e `rule` dentro do teto de 300 caracteres.
- Gerador `br.crm` (`NNNNNNN-UF`, único por execução). Contrato das variáveis de ligação da limpeza em `docs/reference/cleanup.md`.
- Perfis de laboratório em `lab/vampi/product-profile/` e `lab/pilot/product-profile/` (atualizado), e testes de integração `tests/integration/test_lab_vampi.py` e `test_lab_pilot.py` contra o ZAP 2.17 e o proxy de escopo reais.

### Corrigido (verificação contra o ZAP real e o piloto)

- O cliente HTTP do alvo não reaproveita mais conexões: contra o Spring Boot atrás do ZAP e do proxy de escopo, a terceira requisição numa conexão persistente ficava pendurada até o tempo limite de 15 s.
- O ZAP 2.17 fecha a conexão (em vez de devolver `bad_api_key`) quando a chave está ausente ou errada; o erro agora diz isso e aponta `HDAST_ZAP_API_KEY`. O ZAP falso dos testes passou a imitar isso e as formas reais (`bad_view`, `no_implementor`, regras do Replacer com todas as chaves).

### Adicionado (pilha gerenciada e trava de emergência)

- Comandos `hdast stack up <produto>` (`--vulnerable/--secure`, `--token-ttl`, `--build`, `--timeout`), `hdast stack status`, `hdast stack down` e `hdast stop` ([ADR 0019](docs/adr/0019-pilha-gerenciada-politica-por-execucao-e-login-pelo-proxy.md)). A política do proxy de escopo é gerada do perfil (nunca mais larga) e relida pelo validador do contêiner; a chave do ZAP é sorteada e guardada num arquivo de estado fora do repositório (`HDAST_STATE_DIR`), de onde `preflight`, `probe` e `stop` a leem quando o ambiente não a define.
- Serviço `proxy-gateway` no `compose.yaml` (porta `127.0.0.1:3128`, variável `HDAST_PROXY_HOST_PORT`): o login e o token CSRF passam pelo proxy de escopo, não pelo ZAP, por padrão na pilha gerenciada (`HDAST_AUTH_PROXY_URL`).
- Anexação dos alvos de laboratório `vampi` e `clinica-piloto` (projeto `hdast-pilotrun`, credenciais descartáveis) e `ZapApiClient.stop_all_scans`.

### Adicionado (marco M3, `spec inspect`, `preflight` e `probe`)

- Comandos `hdast spec inspect <produto>` (resumo do OpenAPI e verificações cruzadas; `--budget`), `hdast preflight <produto>` (lista de verificações como dado) e `hdast probe <produto>` (`--seed`, `--only`, `--dry-run`, `--include-delete`, `--account`), com envelope JSON, códigos de saída 3 a 6 e resultado parcial em `data` quando terminam em falha ([ADR 0018](docs/adr/0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md)).
- Dependência de runtime `httpx` 0.28.1 (BSD-3-Clause), usada no cliente do alvo e no cliente da API do ZAP; proibida no `domain` pelo import-linter.
- Schema v1 do perfil, aditivo e opcional: `auth.csrf` (`fetch_path`, `cookie_name`, `header_name`, `methods`), `probe.success.json_field_absent_or_not_equal`, `probe.health_path` e `environment.verify_tls`.
- Invariante de envio: `ApprovedRequest` só é criado por `approve(guard, request)`; o cliente HTTP só aceita esse tipo. Redirecionamentos não são seguidos, o tempo e o tamanho da resposta são limitados e TLS é verificado por padrão.
- Classificação de resultado por operação (18 classes), alcançabilidade (tentadas e todas), ritmo por balde de fichas, prazo, janela conferida antes de cada requisição, novo login após 401, espera de 429, renovação de CSRF e parada com o alvo sem resposta.
- Trecho de resposta do alvo neutralizado (300 caracteres, sem ANSI nem bidi, valores sensíveis redigidos) sob `untrusted_target_data`.
- Trilha em `runs/<run_id>/`: `manifest.json`, `audit.jsonl` (decisão antes do envio, resultado depois) e `probe.json`.
- Higiene do ZAP: versão, sessão nova por execução, contexto restrito ao escopo e remoção de regras do Replacer com prefixo `hdast-`.
- Portas `Sleeper`, `EntropySource`, `ValueSourceFactory`, `SpecLoader`, `ProductDocuments`, `SecretProvider`, `SecretVault`, `TargetClient`, `ZapControl` e `RunStore`; adaptadores `adapters/http`, `adapters/zap`, `adapters/secrets`, `adapters/storage/run_store.py`, `product_documents.py`, `adapters/openapi/spec_loader.py` e `adapters/system_runtime.py`.
- Variáveis `HDAST_ZAP_PROXY_URL`, `HDAST_AUTH_PROXY_URL` e `HDAST_ZAP_CA_FILE`.
- Testes: unitários com falsos para os três casos de uso, adaptadores contra servidor HTTP local real, ZAP falso com as formas do spike, contratos dos três comandos e o teste de regressão da afirmação central (alcançabilidade com regras acima da sem regras, sobre o OpenAPI do VAmPI).

### Alterado (M3)

- `ScopeGuard.evaluate` devolve a decisão como dado (`allowed`, `denied_path`, `outside_scope`); `ensure_allowed` não mudou.
- O leitor de YAML endurecido aceita o nome do arquivo (`parse_yaml_document`) para as mensagens de `data-rules.yml` e `flows.yml`.
- `--budget` do resumo da API ganhou teto (`MAX_BUDGET_CHARS`).
- Entradas do `ignore_names` do vulture que passaram a ter chamador de produção foram removidas.

### Adicionado (marco M1, fundação)

- Documentação técnica: `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md` e este changelog; `docs/architecture.md`, `docs/roadmap.md` (tabela única de status), `docs/testing.md`; `docs/modules/`, `docs/reference/` e `docs/operations/`.
- `docs/adr/` com índice, template e os ADRs 0001 a 0011.
- Pacote `harness_dast` em layout `src/` com os pacotes `domain`, `application`, `adapters`, `cli`, `config` e `observability`; `application` e os subpacotes de `adapters` são só esqueleto.
- Hierarquia de erros, envelope JSON versionado, tratador único de erros e o comando `hdast version`.
- Settings da ferramenta (`HDAST_*`) e logger estruturado (structlog) com redação de segredos.
- Ferramentas de qualidade: ruff, mypy estrito, import-linter, vulture, pytest com marcadores.
- CI (`.github/workflows/ci.yml`): análise estática, segurança (gitleaks e pip-audit sobre o `uv.lock`), testes unitários e de contrato com pisos de cobertura por camada e diff-cover, integração (tolera zero testes).
- pre-commit com ruff, gitleaks, commitizen, mypy e import-linter.
- `compose.yaml` com ZAP, proxy de saída (Squid, nega por padrão) e ponte do ZAP em loopback; `lab/` com o VAmPI (perfil `lab`) e seu OpenAPI. Subida e isolamento verificados em tempo de execução em 2026-11-13 (Docker Desktop 29.7.2, Windows 11).
- `products/_template/` com o modelo de perfil de produto.

### Adicionado (marco M2, segunda metade: perfil, `init` e `profile validate`)

- `application/ports.py` (`Clock`, `ProfileRepository`, `ProductScaffolder`) e os casos de uso `ValidateProfile` e `InitProduct` ([ADR 0015](docs/adr/0015-portas-do-perfil-e-carregador-de-yaml.md)).
- `adapters/storage/`: leitor de YAML endurecido (recusa âncora, alias, chave `<<`, chave repetida ou não textual, tag fora do esquema básico, aninhamento excessivo e arquivo acima de 256 KiB; mensagens só com linha e coluna), repositório de perfis em arquivos (nome de produto como slug, caminho resolvido dentro de `products_dir`, arquivos referenciados dentro da pasta do produto), criador de pasta de produto a partir de `products/_template` e `adapters/system_clock.py`.
- Comandos `hdast init <produto>` e `hdast profile validate <produto>`, com `--products-dir` (sobrepõe `HDAST_PRODUCTS_DIR`) e envelope JSON; `cli/composition.py`.
- `tests/fakes/` com relógio, repositório de perfis e criador de produtos em memória.
- Saída da CLI forçada a UTF-8 em `main()`, para que mensagens com acento não derrubem o comando em página de código antiga.

### Adicionado (marco M2, primeira metade: domínio do perfil e do escopo)

- `domain/host.py` e `domain/urlnorm.py`: host e URL de saída em forma canônica, com falha fechada para qualquer ambiguidade.
- `domain/pathpattern.py`: padrões de caminho com `*` e `**`, casamento e cobertura.
- `domain/scope.py`: `ScopeRule`, `Scope` e `ScopeGuard` (camada 1 do escopo), com `allow_local` para o lab.
- `domain/window.py`: janelas de execução (`seg-sex 20:00-06:00 America/Sao_Paulo`) e validade da autorização.
- `domain/overrides.py`: sobrescritas que só estreitam escopo e limites.
- `domain/run.py`: `RunId` e `RunLimits` com tetos absolutos (50 requisições por segundo, 480 minutos, 8 threads).
- `domain/secret_ref.py`, `domain/auth.py`, `domain/profile.py` e `domain/profile_errors.py`: modelos do perfil de produto (schema v1) e tradução de erros sem eco de valores.
- Suíte de QA independente (`tests/**/*_qa.py`) e testes de contrato do CLI.
- ADRs 0012 (dependências `tzdata` e `pyyaml`), 0013 (schema v1 do perfil) e 0014 (avaliação cega como suíte de evals, planejada para o M6).
- `docs/reviews/` com o relatório de revisão de QA de 2026-11-13 e a resposta às constatações.
- Dependências de runtime `tzdata` (banco de fusos IANA no Windows) e `pyyaml` (leitura do perfil; hoje só um teste a usa).
- `docs/reference/target-yml.md` reescrito como referência do schema v1 implementado.

### Alterado

- Tipo de autenticação `oauth2_password` renomeado para `login_password`; campos conforme `domain/auth.py` (`token_path`, `request_encoding`, `username_field`, `password_field`, `token_response_field`, `token_header`, `token_scheme`); a variante de chave fixa usa `header_name`. O `products/_template/target.yml` foi reescrito para o schema real.
- Códigos de saída: `TargetError` passa a 6 e `CleanupError` a 7 (antes usavam 5, agora só de ferramenta externa); interrupção do usuário sai com 130 e `INTERRUPTED`. ADR 0010 emendado antes do primeiro commit.
- `--json` vale antes ou depois do subcomando; `hdast` sem argumentos mostra a ajuda e sai com 0.
- `Authorization.valid_until` aceita apenas data `AAAA-MM-DD`.

### Corrigido (revisão de QA independente, 2026-11-13)

Achados do [relatório](docs/reviews/2026-11-13-qa-m1-m2.md); decisão por achado na [resposta](docs/reviews/2026-11-13-qa-m1-m2-resposta.md).

- A-01 (bloqueante): `deny_paths` era contornável por `/admin;x=1`, `/admin%20`, `/admin.` e `/admin;/x`. O `ScopeGuard` agora recusa segmentos com `;`, que terminam em ponto ou espaço ou começam por espaço, em forma crua ou codificada.
- A-02: o template do perfil não carregava; foi alinhado ao schema real e passou a ser validado por teste.
- A-03 e A-12: `--json` após o subcomando e `hdast` sem argumentos.
- A-06 e A-19: códigos de saída 6, 7 e 130.
- A-07: janela com início igual ao fim era aceita na forma estruturada e ampliava a janela autorizada; agora é sempre recusada.
- A-05: o gate de pisos de cobertura não passa mais de forma vazia (prefixo inexistente ou camada com código e nada medido falham).
- A-09 e A-10: as mensagens do `ScopeGuard` e do perfil deixam de repetir o caminho da requisição e o host inválido.
- A-14: `ConfigError` das settings não encadeia mais o erro do pydantic (que continha o valor); `HDAST_ZAP_BASE_URL` só aceita `http` ou `https`.
- A-17 (parte): contrato do import-linter que impede `domain` de importar dependências externas além de pydantic; `vulture` com `ignore_names` agrupado e comentado.
- A-15: redação de logs estendida a exceções, objetos, conjuntos, `bytes`, pares de cabeçalho e às chaves `senha`, `private_key` e `credentials`.
- A-04, A-11 e A-13: documentação sincronizada com o código, ADRs 0012 e 0013 e reescrita da referência do perfil.

Itens da revisão **não corrigidos** nesta rodada (registrados como em aberto no [roadmap](docs/roadmap.md#itens-em-aberto)): A-08, A-16, A-18 e parte de A-17.

Observação: este registro reflete o código lido em 2026-11-13 durante a escrita da documentação. Confirme cada item contra o `git diff` e os gates antes do primeiro commit.

### Decisões registradas

- Idioma: identificadores em inglês; documentação, comentários e mensagens em português (P-06).
- Verificador de tipos: mypy em modo estrito (P-07).
- Windows com Docker Desktop suportado desde o início (P-11).
- Encadeamento de chamadas limitado a um nível na V1 (P-12).
- Comando `hdast` e pacote `harness_dast` (P-13).
- Requisito novo do dono do projeto: avaliação cega por agentes de teste como suíte de evals, no M6 ([ADR 0014](docs/adr/0014-avaliacao-cega-como-eval.md)).

### Pendente

- Licença do projeto indefinida (P-14); não há arquivo `LICENSE`.
- Segundo revisor humano ainda não nomeado (P-09).
- Spike do M0 ainda não executado (AD-07, P-08, P-10).
- Carregador de YAML, comandos `hdast` além de `version`, camada `application`, adaptadores, skills e integração com o ZAP: planejados (M2 a M6).

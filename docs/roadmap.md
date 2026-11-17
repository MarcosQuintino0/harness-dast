# Roadmap da V1

Fonte: documento de fundação técnica aprovado em 2026-11-13. O tamanho de cada marco é uma estimativa relativa, sem base em dados publicados. Cada marco termina com algo demonstrável e um critério objetivo.

## Estado atual

Versão publicada mais recente: **1.9.3**, em 2026-11-16. A organização V1.9.4 está implementada nesta branch, sem carimbo de release; aceite e integração dependem da revisão.
M0 a M6 têm entregas de código e provas locais, com os limites por componente abaixo; M7 não foi realizado.
Existem CLI, ZAP, limpeza Oracle, painel, carta, aprovação humana, `negative`, estratégia, conhecimento, diário de mutações
e leitura de dono no `authz` (ADR 0082). Não existem outros motores ou bancos de limpeza nem prova contra produto real.
O padrão permanece `legacy`: a investigação V1.9 preservou a lacuna histórica de equivalência; `proxy` não foi promovido.
Continuam lacunas na autorização vertical, no recibo de efeito aplicado em tarefa, no par 200 e na atribuição em massa V4 do VAmPI.
A cerca não modela coerção de tipo de parâmetro de caminho: mitigue com negação por curinga.
Authz não cobre identificador no corpo nem `DELETE`; escrita horizontal exige duas contas do mesmo papel.

Esta seção consolida o vigente. As seções de provas por versão e as notas transferidas das instruções registram o estado
na data da entrega: uma prova posterior pode completar uma lacuna anterior. [Histórico](../CHANGELOG.md),
[provas datadas](reviews/README.md) e [estado dos planos](plans/README.md) preservam essa distinção.

## V1.12: mais achados (provada só no laboratório)

Entregue na branch `feat/v1-12-mais-achados`, versão 1.12.0, sem PR, merge nem release. Os ADRs 0092 a 0103 estão propostos.

- **Carta:** o bloco `attack` liga `pacing`, `inject_headers`, `oast`, `allow_rate_tests`, `experimental_rules` e `inventory`; só a carta liga, pela CLI (ADR 0096).
- **Capacidades:** JWT no `authz` (ADR 0098); injeção em cabeçalhos e cookies (0097); OAST na varredura e SSRF guiado pelo contrato (0099, 0100); limite de consumo (0101); inventário de versões e documentação (0102); imagem derivada `hdast/zap` com regras alpha e beta selecionadas (0103). Tabela do que o ZAP faz em [uso do ZAP](reference/uso-do-zap.md).
- **Laboratório (trilha L):** crAPI na pilha (0094), ponte de retorno isolada (0095), falha H11 na Clínica Piloto (0092), vigia (0093), regressão dirigida e caso `crapi-foco`.

**Provado só no laboratório (Clínica Piloto, VAmPI e crAPI, 2026-11-17):** H11 achada só com a chave; SSRF do crAPI (C11) achado com OAST; JWT (C15) aceito com `alg none` e claims alteradas; OTP da v2 (C3) sem limite. Detalhes, `run_id` e números no [relatório da V1.12](reviews/relatorio-v1.12.md).

**Não provado:** injeção em cookie sem alvo plantado; Log4Shell, XXE e SSTI cega sem alvo; chave HMAC fraca só em unidade; C12 (NoSQL) não achado em força baixa; 5 alarmes falsos de gravidade alta da regra 40033 na Clínica segura; `check_otp_v3` com provável falso positivo; página enorme só em unidade; `kid`, `jku` e confusão de algoritmo fora. Sem produto real, sem rodada cega e sem validação independente (pendentes). O caso `crapi-foco` ganhou a versão 2, com `detectable: true` em C3, C11 e C15; na Clínica Piloto a H11 continua `detectable: false`, porque a carta da Clínica não autoriza cabeçalhos.

## Organização V1.9.4

Fases 1, 2 e 3 implementadas: navegação e versão coerentes, regras canônicas em AGENTS, cinco skills de desenvolvimento,
cópia cega por permissão com manifesto (ADR 0083 proposto), pesquisa consolidada e retenção documental de evals.
Subpacotes `domain/panel/`, `domain/authz/`, `application/authz/`, `domain/report/` e portas por consumidor implementados,
com imports e testes espelhados. ADR 0084 proposto; apresentação preservada na camada atual.
CI configurado com timeout em todos os jobs, job Windows sem integração e preparação explícita das imagens no job manual;
coleta vazia não é mais aceita. O CI não foi executado de verdade nesta entrega.
Validação limitada a unitários e contratos; laboratório e rodadas cegas não executados nesta entrega.
Plano, aceites e limites: [organização V1.9.4](plans/2026-11-16-v1-9-4-organizacao.md).

## Marcos

| Marco | Entrega | Pronto quando | Tamanho |
| --- | --- | --- | --- |
| M0 Decisões e spike | Spike descartável: ZAP em Docker no Windows, requisições válidas pelo proxy, token no ZAP, conexão com o Oracle de testes, skill chamando um comando, medição de bloqueios | AD-07, P-08 e P-10 resolvidos e registrados. Nenhum código do spike é aproveitado. **Estado: executado em 2026-11-13 para a parte do ZAP** ([relato](spikes/2026-11-13-m0-zap.md)): AD-07 e P-10 respondidos (decisões nos ADRs 0017, 0018 e 0019). O spike não mediu a taxa de bloqueio (P-08) nem a skill chamando um comando; o Oracle foi verificado depois, no M5 | Pequeno |
| M1 Fundação | Esqueleto do repositório, ferramentas, pre-commit, CI com todos os gates, ADRs, `CLAUDE.md`, lab com VAmPI | Um pull request trivial passa por todos os gates. Uma importação proibida quebra o CI. **Estado: entregue.** Pull request #1 mesclado em 2026-11-13; o CI rodou no Linux a partir do #2 e passou nos pull requests seguintes (`gh run list`) | Pequeno |
| M2 Domínio, perfil e escopo | `init` e `profile validate`. Modelos de domínio, `ScopeGuard`, carregador de perfil, erros e envelope JSON | Casos obrigatórios do `ScopeGuard` verdes. Perfil inválido é recusado com mensagem acionável. **Estado: entregue:** domínio (modelos, `ScopeGuard`, janelas, sobrescritas), carregador de YAML endurecido, `hdast init` e `hdast profile validate`, com os primeiros casos de uso e portas | Médio |
| M3 OpenAPI, dados e alcançabilidade | `spec inspect`, `preflight`, `probe`. Catálogo de geradores, autenticação do piloto, encadeamento de um nível, trilha de auditoria | No VAmPI, a alcançabilidade com regras fica acima da do import cru, e o número é reportado | Grande |
| M4 Varredura e achados | `scan` e `report`. Adaptador do ZAP, limites fixos, modelo de achado, fingerprint, relatório em JSON e Markdown | O achado conhecido do VAmPI aparece com evidência redigida. O modo seguro não gera achado de severidade alta | Grande |
| M5 Limpeza e execução completa | `cleanup`, `run`, parada de emergência, manifesto da execução | Teste de ponta a ponta verde no lab, com zero requisição fora do escopo na auditoria | Médio |
| M6 Skills, documentação de uso e avaliação cega | As quatro skills, os dois subagentes, permissões, guias de operação, roteiro de avaliação das skills e **suíte de avaliação cega (evals)**, [ADR 0014](adr/0014-avaliacao-cega-como-eval.md) | Uma pessoa que nunca viu o projeto cadastra o lab e roda uma varredura seguindo só o README, e agentes cegos repetem isso com nota automática: zero requisição fora do escopo, alcançabilidade e achados medidos contra o gabarito (veja [M6](#m6-skills-documentação-de-uso-e-avaliação-cega)) | Médio |
| M7 Piloto em um produto real | Proxy de saída, autorização formal, perfil do produto piloto, comparação ZAP cru contra ZAP configurado | Execução sem incidente, alcançabilidade medida e apresentada à liderança. É o ponto de decidir se a V2 acontece | Médio |

Observação: a ordem M0 antes de M1 é a do desenho. O M1 foi iniciado antes do spike do M0, e a primeira metade do M2 (domínio) também, por não dependerem dele; o spike foi executado em 2026-11-13, antes do M3 ([relato](spikes/2026-11-13-m0-zap.md)). Estado consolidado: M0 a M6 têm entregas; M7 permanece pendente. Evoluções posteriores estão discriminadas abaixo.

As skills previstas para o M6 são `onboard-product`, `fix-reachability`, `run-scan` e `triage-findings`; os subagentes são `spec-analyst` e `findings-triager`.

## Tabela de status

**Esta é a única tabela de status do projeto.** Quando um componente muda de estado, atualize só esta tabela e o `CHANGELOG.md`. Os demais documentos apontam para cá.

Legenda: **Implementado** = existe em código ou configuração e tem teste ou verificação registrada; **Parcial** = existe uma parte, a outra não; **Planejado (Mx)** = nada existe, marco previsto; **Pendente** = depende de decisão ou de spike.

Estado consolidado inclui a V1.11 e a V1.12, provadas só no laboratório. Provas datadas em [reviews](reviews/README.md) distinguem implementação, validação local e lacunas; itens sem confirmação continuam marcados como tal.

### V1.11: verificação de achados (provada só no laboratório)

Código das fases A, B, C e E integrado: classificação aditiva, `hdast confirm`, declaração humana separada e apresentação no painel e nos relatórios. As receitas e restrições estão em [verificação](reference/verification.md); os ADRs 0085 a 0091 permanecem propostos. A régua privada `triage_accuracy` é suplementar e preserva a grade histórica. O recibo da semente efetivamente varrida é obrigatório para confirmação ativa; execuções antigas sem recibo recusam tráfego.

**Provado só no laboratório (Clínica Piloto e VAmPI, 2026-11-17):** fase 0 com três linhas de base completas, fase D com a matriz por tipo em [calibração](reference/verification-calibration.md) e fase F nos modos vulnerável e seguro. Resultado honesto: só recibos de autorização chegaram a `reproduced`; o único SQL elegível a receita ativa ficou `inconclusive`; os demais SQL, XSS, travessia, hash e cabeçalho saíram `not_verifiable`; `likely_false_positive` nunca ocorreu, então a capacidade de descartar não foi medida. O achado de autorização do modo seguro (`buscarPaciente` entre médicos) é a ausência de `authz.shared_roles` no perfil do laboratório, não defeito: com a declaração da carta, a execução segura tem zero achados de autorização e zero `reproduced`. Limites, gates e commits no [relatório da V1.11](reviews/relatorio-v1.11.md). Não há release publicada, PR ou merge desta versão, nem rodada cega, nem produto real. A V1.10 permanece fechada.

### Fundação (M1)

| Componente | Onde | Status |
| --- | --- | --- |
| Pacote `harness_dast` em layout `src/`, com pacotes `domain`, `application`, `adapters`, `cli`, `config`, `observability` | `src/harness_dast/` | Implementado (M1) |
| Subpacotes de `adapters` (`openapi`, `zap`, `http`, `datagen`, `secrets`, `reporting`, `cleanup`, `storage`) | `src/harness_dast/adapters/` | `openapi`, `datagen`, `storage`, `http`, `zap` e `secrets` implementados (M3); `cleanup` implementado (M5); `reporting` implementado (M4: armazém de artefatos e destinos JSON e Markdown) |
| `application` (casos de uso e portas) | `src/harness_dast/application/` | `ports.py`, `init_product.py` e `validate_profile.py` (M2); `inspect_spec.py`, `preflight.py` e `probe.py` (M3). `cleanup.py` (M5); `scan.py` e `report.py` (M4); `run.py` (`RunPipeline`, M5). V1.1 e V1.2: `authz/`, `doctor*.py`, `secret_*.py`, `metrics.py`, `panel*.py`, `command_journal.py` |
| Hierarquia de erros `HarnessError` e mapeamento para códigos de saída | `domain/errors.py` | Implementado (M1) |
| Envelope JSON com `schema_version` e saída humana | `cli/output.py` | Implementado (M1) |
| Tratador único de erros | `cli/app.py` | Implementado (M1) |
| Comando `hdast version` | `cli/commands/version.py` | Implementado (M1) |
| Settings da ferramenta (`HDAST_*`) | `config/settings.py` | Implementado (M1) |
| Logger estruturado com redação (structlog) | `observability/logging.py` | Implementado (M1) |
| Configuração de ruff, mypy estrito, pytest, import-linter e vulture | `pyproject.toml` | Implementado (M1) |
| pre-commit (ruff, gitleaks, commitizen, mypy, import-linter) | `.pre-commit-config.yaml` | Implementado (M1); se os hooks estão instalados nas máquinas de quem contribui: a confirmar |
| CI com gates (estática, segurança, testes, integração) | `.github/workflows/ci.yml` | Implementado (M1); rodou nos pull requests #1 a #5 e passou nos mais recentes (`gh run list`). A integração com Docker está configurada sob disparo manual; a configuração V1.9.4 ainda não foi executada |
| `compose.yaml` (ZAP, proxy de escopo, pontes do ZAP e do proxy, alvos do lab) e `lab/` (VAmPI) | raiz, `docker/`, `lab/` | Implementado (M1); subida e isolamento verificados em tempo de execução em 2026-11-13 (veja [lab/README.md](../lab/README.md)) |
| `products/_template/` (modelo de perfil) | `products/` | Implementado (M1); `target.yml` validado por teste contra o modelo de domínio |
| Documentação e ADRs 0001 a 0084 (estados no índice; 0083 e 0084 propostos, aceitar é decisão do dono) | `docs/`, raiz | Implementado |
| `LICENSE` | | Não existe de propósito: licença indefinida (P-14) |

### Domínio do perfil e do escopo (primeira metade do M2)

Tudo abaixo é código puro em `src/harness_dast/domain/`, com testes unitários (incluindo propriedades com hypothesis) e a suíte de QA `*_qa.py`. Todos os comandos `hdast` usam esses módulos. Contrato de cada módulo: [modules/domain.md](modules/domain.md).

| Componente | Módulo | Status |
| --- | --- | --- |
| Host canônico (IDNA, IP sem ambiguidade, metadados da nuvem) | `host.py` | Implementado |
| Normalização de URL de saída (falha fechada, incluindo `;`, ponto e espaço finais) | `urlnorm.py` | Implementado |
| Padrões de caminho (`*`, `**`), casamento e cobertura | `pathpattern.py` | Implementado |
| `ScopeRule`, `Scope`, `ScopeGuard` (camada 1 do escopo) | `scope.py` | Implementado |
| Janelas de execução (gramática compacta, fuso IANA) e validade da autorização | `window.py` | Implementado |
| Sobrescritas que só estreitam escopo e limites | `overrides.py` | Implementado |
| `RunId` e `RunLimits` com tetos absolutos | `run.py` | Implementado (`RunManifest` mora em `probe_result.py`) |
| Referência a segredo `env:NOME` e base dos modelos do perfil | `secret_ref.py` | Implementado |
| Autenticação: `login_password` e `api_key` | `auth.py` | Implementado |
| `ProductProfile`, `Environment`, `CleanupConfig` e tradução de erros para `ConfigError` | `profile.py`, `profile_errors.py` | Implementado |
| Carregador de YAML do perfil (recusa âncora, alias, `<<`, chave repetida, tag fora do esquema básico, arquivo grande, caminho que sai da pasta) | `adapters/storage/strict_yaml.py`, `profile_repository.py`, `product_paths.py` | Implementado (M2) |
| Criador de pasta de produto a partir de `products/_template` | `adapters/storage/product_scaffolder.py` | Implementado (M2) |
| Portas `Clock`, `ProfileRepository`, `ProductScaffolder` e casos de uso `ValidateProfile` e `InitProduct` | `application/` | Implementado (M2); [ADR 0015](adr/0015-portas-do-perfil-e-carregador-de-yaml.md) |

### Comandos da CLI

Existem `version`, `doctor`, `init`, `profile validate`, `profile approve`, `profile approval`, `spec inspect`, `preflight`, `probe`, `scan`, `authz`, `negative`, `report`, `panel`, `run`, `wait`, `cleanup`, `secret`, `stack`, `stop`, `strategy`, `plan` e `knowledge`. O fluxo completo foi verificado contra o ZAP 2.17 real e dois alvos de laboratório ([relatório](reviews/2026-11-13-e2e-lab.md)).

| Comando | Status |
| --- | --- |
| `hdast version` | Implementado (M1) |
| `hdast init`, `hdast profile validate` | Implementado (M2) |
| `hdast spec inspect`, `hdast preflight`, `hdast probe` | Implementado (M3); verificado contra o ZAP real (seção abaixo) |
| `hdast scan`, `hdast report` | Implementado (M4); verificado contra o ZAP 2.17 real ([ADR 0022](adr/0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md), [ADR 0023](adr/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md); resultado dos 12 itens em [reference/relatorio.md](reference/relatorio.md#o-que-foi-verificado-contra-o-zap-real)) |
| `hdast cleanup` | Implementado (M5): `--dry-run`, confirmação digitada só em terminal interativo ([ADR 0025](adr/0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md)), portão de SQL, teto de linhas, verificado contra um Oracle Free real ([ADR 0020](adr/0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md), [guia](operations/cleanup.md)) |
| `hdast doctor` | Implementado (V1.1, [ADR 0028](adr/0028-facilitar-o-uso-doctor-setup-path-allow-local-init-e-prazo-da-pilha.md)); avisa de `scope.path_mode: wide` e da falta de duas contas do mesmo papel; verificado com Docker real e com porta ocupada em 2026-11-13. Veja "V1.1" abaixo |
| `hdast authz`, `hdast run --authz` | Implementado (V1.1, [ADR 0027](adr/0027-teste-de-autorizacao-entre-contas.md)); verificado só na Clínica Piloto local (H5, H6, H7), não contra produto real. Veja "V1.1" abaixo |
| `hdast panel` | Implementado como código e testes (V1.2, [ADR 0032](adr/0032-painel-da-execucao.md), proposto): gera as páginas HTML do painel da execução; as abas de execução estão feitas, incluindo Autorização desde a V1.9.3. Veja "V1.2" abaixo |
| `hdast profile approve`, `hdast profile approval` | Implementado como código e testes (V1.3, [ADR 0037](adr/0037-aprovacao-humana-do-escopo.md), proposto); veja "V1.3" abaixo |
| `hdast init --from-letter [--check]` | Implementado como código e testes (V1.3, [ADR 0036](adr/0036-carta-estruturada.md), proposto); veja "V1.3" abaixo |
| `hdast run`, `hdast stop` (trava de emergência) | Implementado (M5): `run` encadeia preflight, probe, scan, authz, negative e report (authz só lê por padrão; escrita só pela carta) em um processo e grava `run.json`; `stop` aciona o `KILL`, para as varreduras e diz o que estava rodando; `stack up --oracle` ([ADR 0024](adr/0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md)) |

### V1.1: o que foi provado em laboratório e o que ainda NÃO foi verificado

Quatro entregas, cada uma com ADR, juntadas em `feat/v1-1` e costuradas entre si. Todas passam nos gates e nos testes unitários e de contrato. Em 2026-11-13 a cerca, o `authz`, o `doctor`, o `setup_path` e o prazo da pilha foram medidos com Docker, ZAP e alvos de laboratório reais ([cerca](reviews/2026-11-13-lab-v1-1-cerca.md), [authz](reviews/2026-11-13-lab-v1-1-authz.md)). Continua sem prova contra produto real.

| Entrega | Existe como código e testes | O que ainda NÃO foi verificado |
| --- | --- | --- |
| Cerca com motivo granular e `scope.path_mode: wide` ([ADR 0026](adr/0026-cerca-com-motivo-granular-e-modo-amplo-de-caminho.md)) | `ScopeReason`, `detail` na auditoria, `traffic.denied_by_detail`, `path_shape_denied`, `allowed_outside_allow`, `path_mode`, `WideScopeGuard` só no proxy; aviso de cobertura parcial e nomes legíveis no `report.md` e no `report.html` | **Provado em laboratório:** a isca em `deny_paths` não foi alcançada por nenhuma das 45 formas, contra o proxy e o ZAP reais, nos dois modos (`isca_calls` 0). **Não verificado:** a coerção de tipo do parâmetro de caminho (veja "Itens novos da V1.1"); uma repetição por célula, sem variância; HTTPS pelo proxy; o caminho `allowed_outside_allow` contra alvo real. O ADR 0026 mantém o status que tinha (decisão do dono) |
| Teste de autorização entre contas ([ADR 0027](adr/0027-teste-de-autorizacao-entre-contas.md)) | `hdast authz`, `run --authz`, `exchanges.json` do `probe`, quatro verificações, `authz.json`, seção `authz` em `findings.json`, `report.md` e `report.html`, `summary.authz_by_severity` | **Provado na Clínica Piloto local:** H5, H6 e H7 achados no vulnerável e zero no seguro (55 e 51 pedidos), `exchanges.json` gravado por `probe` real, restauração do campo conferida pelo próprio `authz.json`. **Não verificado:** produto real; BFLA vertical e a interrupção após o `PUT` em alvo real; `report` com a seção `authz` (o `scan` não rodou); escritas sobre recurso de outra conta |
| Facilitar o uso ([ADR 0028](adr/0028-facilitar-o-uso-doctor-setup-path-allow-local-init-e-prazo-da-pilha.md)) | `hdast doctor` (com avisos de `path_mode: wide` e de falta de duas contas do mesmo papel), `probe.setup_path`, mensagem do `allow_local`, `init --with-cleanup`, validade da pilha | **Provado:** `doctor` com tudo certo e com porta 3128 ocupada; `setup_path` no VAmPI (migrado de `health_path: /createdb`, alcançabilidade 1,0); prazo da pilha com `max_duration_minutes: 3` em cópia. **Não verificado:** `doctor` com Docker parado; 30 minutos reais entre `stack up` e `run` |
| Cofre de senhas local ([ADR 0030](adr/0030-cofre-de-credenciais-do-sistema-keyring.md)) | `secret_ref: keyring:NOME`, `hdast secret set\|list\|delete` (só em terminal), `RoutingSecretProvider`, adaptador `keyring` com lista fixa de backends, presença no `preflight` e no `doctor`, redação igual à de `env:`, negação no `.claude/settings.json` | O cofre real do Windows, do macOS e do Linux (os testes usam backend em memória e nunca tocam o cofre da máquina); o `secret set` num terminal real com prompt oculto; o roteiro de prova está no relatório da entrega |
| Medição da execução ([ADR 0031](adr/0031-medicao-da-execucao-metrics-json-e-tempo-por-regra-do-zap.md)) | `metrics.json` (tempo por etapa, operação e regra do ZAP, tráfego e lacunas, regras desligadas) e `rule-stats.json`, gravados por `report` e `run`; só números e ids | **Provado com Docker (2026-11-14):** um ataque direcionado na Clínica Piloto (`probe --only` e `scan --only` em `listarConvenios` e `buscarConvenio`, depois `report`) gravou `metrics.json` com 44 regras medidas por operação (tempo, pedidos, alertas e estado) e lacunas do proxy. **Não verificado:** `hdast run` completo; `preflight` no `metrics.json` fora do `run`; outra versão do ZAP além da 2.17.0; produto real |
| Relatório agrupado, `report.html` e skill `test-product` ([ADR 0029](adr/0029-relatorio-agrupado-pagina-html-e-skill-de-um-pedido-so.md)) | `groups`, notas de padrão esperado, `report.html` (sem JavaScript, CSP, escape), skill `test-product` com contrato testado | A página aberta em navegador de verdade (claro e escuro, celular, impressão); a rodada cega com a skill de um pedido só |

As costuras entre as quatro (página com `authz` e com a cerca, doctor, mensagens de erro, guias e skills) foram fechadas em código e testes, também sem Docker.

### V1.2: painel da execução (entregue em 1.2.0 como código e testes)

Desenho aprovado em `docs/design/execution-panel/`. Peças de dados, cada uma como código e testes unitários e de contrato, **sem Docker e sem prova contra alvo**:

| Peça | Situação |
| --- | --- |
| Diário de comandos por produto ([ADR 0033](adr/0033-diario-de-comandos.md), Proposto) | Código e testes: `domain/command_journal.py`, `application/command_journal.py`, `adapters/storage/command_journal.py`, registro em `run_app`; referência em [reference/command-journal.md](reference/command-journal.md) |
| Tradução de cada comando para português simples | Código e testes (`domain/command_translation.py`); teste falha se a CLI ganhar comando sem tradução |
| Catálogo de explicação de falha, degrau de confiança e dados de "reproduzir à mão" | Código e testes (`domain/finding_explain.py`, `finding_confidence.py`, `manual_repro.py`); usados pelas abas Falhas e Terminal |
| Lacuna histórica: "confirmada por pessoa" | Na V1.2 o terceiro degrau não era alcançável; a V1.11 acrescenta declaração separada no ADR 0086, proposto. |
| Painel (HTML), comando `panel`, índices de produtos e histórico | O comando `panel` e as abas existem (veja a tabela abaixo); os índices e a página ao vivo estão feitos como código e testes ([ADR 0034](adr/0034-indices-do-painel-e-pagina-ao-vivo.md), proposto) |

### V1.2: painel da execução, estado por parte (1.2.0)

O desenho final do painel foi aprovado pelo dono em 2026-11-14 ([docs/design/execution-panel/](design/execution-panel/README.md)); a CLI gera as páginas ([ADR 0032](adr/0032-painel-da-execucao.md), proposto). Estado por parte:

| Parte | Existe como código e testes | O que falta |
| --- | --- | --- |
| Fundação | `hdast panel`, `PanelView` (modelo de visão com tudo que as seis abas precisam), registro de páginas, casca (CSP, caminho, menu, componentes), tokens do desenho com teste de paridade, formatos e palavras de estado, porta `PanelFiles`, geração no fim de `report` e `run` (falha nunca derruba) | Gerado só a partir de uma execução real guardada, sem Docker e sem varredura nova; ainda não visto por uma pessoa de QA |
| Abas Resumo e Etapas | Fiéis ao desenho, com os estados "sem falha grave", "parou no meio" e "erro"; testadas com texto hostil em toda página | Conferir o que o desenho marca como exemplo (tipos de teste, tokens por etapa) quando existirem as fontes |
| Abas Falhas, Cobertura, Terminal, Tempo e tokens | Fiéis ao desenho, com os links por âncora entre abas verificados por teste; nenhuma página provisória sobra | Ver com uma pessoa de QA; Docker e varredura nova não foram usados |
| Diário de comandos e catálogo de explicação de falha | Ganchos `commands` e `explanations` ligados (`application/panel_hooks.py`, `domain/panel/catalog.py`, `domain/panel/journal.py`) | Nada pendente além da prova contra alvo real |
| Tokens do agente | `agent-metrics.json` lido pelo caso de uso e mostrado na aba Tempo e tokens; arquivo ausente vira "não medido" | Quem grave o arquivo fora da avaliação cega |
| Índices de produtos e de histórico | `runs/index.html` e `runs/history-<produto>.html`, refeitos a cada painel e por `hdast panel --index`; links relativos no caminho do alto; estados "nenhum produto", "um teste só", "erro", "carta vencida" e "sem dados" | Gerados só a partir de execuções reais guardadas; sem prova com `hdast run` de verdade |
| Página "ao vivo" | `panel/live.html` regravada a cada etapa e função, sem JavaScript, com recarga a cada 15 s; fecha sem recarga ao fim do `run` | Sem prova com `hdast run` de verdade (sem Docker); faltam "tipos de teste da função", "sinais de falha" e o terminal ao vivo, e o estado transitório "alvo fora do ar" |
| Máscara de dados pessoais na prova | Nada | Tudo (o dono ainda não respondeu sobre a máscara) |

### Diferenças entre o painel e o desenho

O painel da 1.2.0 segue o desenho de `docs/design/execution-panel/`. O que o desenho mostra e a CLI ainda não tem, ou que ficou conferido só em parte (todos itens abertos, sem correção prevista nesta versão):

- **Nomes das regras do ZAP em inglês no painel.** Falta uma tabela de tradução (regra do ZAP para nome em português); hoje a lista de grupos e as regras mais lentas mostram o nome que o ZAP dá.
- **Chaves em inglês na resposta dos comandos do Terminal.** A resposta resumida mostra `chave: valor` com a chave do envelope da CLI (`run_id`, `operations_sent`...); falta traduzir as chaves como as frases dos comandos.
- **Blocos do desenho do Ao vivo que não existem por falta de dado:** o terminal ao vivo, os tipos de teste de cada função, os sinais de falha até agora e os tokens até agora.
- **Estado "sistema testado fora do ar".** O desenho prevê o estado transitório da página ao vivo; o código não o produz.
- **Lacuna histórica do degrau "confirmada".** A V1.11 acrescenta registro humano separado; não modifica `triage.json`.
- **Celular e tema claro conferidos só em parte.** Foram vistos o Resumo e a página ao vivo; as demais abas não foram abertas em celular de verdade nem no tema claro.
- **Sem link "pular para o conteúdo"** no topo das páginas (acessibilidade por teclado).
- **A página ao vivo só começa na varredura**, porque o preflight do `run` abre uma pasta própria (nota no ADR 0034).
- **Reprodução à mão do teste entre contas:** a página diz que não há passo a passo; o `authz` não guarda pedido nem resposta inteiros.

### V1.3: uso seguro e fácil (entregue em 1.3.0 como código e testes)

Cinco itens, três com ADR (0035 a 0037, todos "Proposto"). Todos passam nos gates e nos testes unitários e de contrato; só a trava foi provada com Docker, uma vez, no laboratório. **Nada foi provado contra produto real.** Mudança incompatível de uso: todo perfil existente precisa ser aprovado uma vez por uma pessoa (`hdast profile approve`).

| Entrega | Existe como código e testes | O que ainda NÃO foi verificado |
| --- | --- | --- |
| Trava exclusiva por pilha ([ADR 0035](adr/0035-trava-por-pilha.md)) | `stack.lock` na pasta de estado; `probe`, `scan`, `authz` (fora do `--dry-run`), `run`, `stack up` e `stack down` tomam; `STACK_BUSY` e saída 8; trava órfã retomada; `stop` e `stack status` nunca bloqueados; `data.lock` no `stack status` | **Provado com Docker uma vez** (`tests/integration/test_lab_stack_lock.py`, Clínica Piloto: segundo comando recusado com saída 8 e aceito depois do fim do primeiro). **Não verificado:** a consulta de processo vivo fora do Windows; mais de uma máquina na mesma pasta de estado; varreduras concorrentes (planejadas para a 1.7) |
| Carta estruturada ([ADR 0036](adr/0036-carta-estruturada.md)) | `carta.yml`, `hdast init --from-letter [--check]`, `LETTER_REJECTED` com `data.issues`, `data.warnings`, `AUTHORIZATION_EXPIRED`, `data.example_data`; 49 cartas de borda no QA | O perfil gerado pela carta não foi rodado de ponta a ponta com Docker; carta de produto real |
| Aprovação humana do escopo ([ADR 0037](adr/0037-aprovacao-humana-do-escopo.md)) | `hdast profile approve` e `profile approval`, `data.approval` no `profile validate`, `SCOPE_NOT_APPROVED` (saída 3) em `preflight`, `probe`, `scan`, `authz`, `run`, `cleanup` e `stack up`, impressão digital na versão 2 do cálculo, `python -m evals.runner approve` | `profile approve` num terminal interativo de verdade (os testes usam o dublê do terminal); o `evals.runner approve` só com o caso mínimo; o conteúdo do script de limpeza fora da impressão digital (decisão registrada no ADR) |
| Entrevista inicial nas skills | Entrevista estruturada numa rodada, resumo antes de atacar, consulta da aprovação, tratamento de `STACK_BUSY`; teste de contrato confere os comandos e flags citados | Entrevista com uma pessoa de verdade; rodada cega no fluxo novo (a `test-product` segue sem rodada cega) |
| Documentos desatualizados e verificador de links | Documentos corrigidos; `tests/contract/test_docs_links.py`; teste de vazamento do gabarito para a cópia cega (`tests/contract/test_letter_guide.py`) | Nada pendente além de itens "a confirmar" deixados nos documentos |

Uma correção entrou junto: a redação de segredos não apaga mais a versão do protocolo quando o endereço termina em `token`, `basic` ou `bearer`. Relatório da versão: [reviews/relatorio-v1.3.md](reviews/relatorio-v1.3.md).

### Controles de segurança

| Controle | Status |
| --- | --- |
| Escopo, camada 1: `ScopeGuard` | Implementado (M3): `preflight` e `probe` só enviam `ApprovedRequest`, criado por `approve(guard, ...)`; mutação que remove a chamada quebra testes |
| Escopo, camada 2: ZAP em modo protegido | Implementado (M4): contexto por execução e `contextId` em toda varredura; verificado: o ZAP varre só o que o contexto cobre e o proxy barra o resto |
| Escopo, camada 3: rede interna e proxy de escopo ([ADR 0017](adr/0017-proxy-de-escopo-com-scopeguard.md)) | Implementado e exercitado no lab: varreduras ativas reais passam pelo proxy de escopo, que nega o que o varredor inventa fora do escopo (contado em `scan.json`); caminho para ambiente de empresa em IP privado não confirmado (veja itens em aberto); obrigatório antes de execução contra ambiente da empresa (M7). O Squid do desenho original foi substituído pelo mitmproxy no ADR 0017 |
| Validação de autorização, validade e janela | Implementado (M3): conferida na partida e antes de CADA requisição do `preflight` e do `probe` (`RunGate`) |
| Limites de carga fixados e tetos absolutos | Implementado: o `probe` impõe `requests_per_second` e `max_duration_minutes`; o `scan` fixa `threadPerHost`, `delayInMs` e os tetos de duração no ZAP ANTES da primeira varredura e confere o prazo total a cada consulta (M4); a taxa efetiva é medida na auditoria do proxy (`scan.json` `traffic`) e comparada com o limite no relatório do lab |
| Sobrescritas que só reduzem | Implementado: `--max-minutes`, `--threads`, `--only`, `--fail-on`... só reduzem (`overrides.py`) |
| Redação de logs (chaves, segredos registrados, JWT, CPF) | Implementado (M1) |
| Formato e validação de `secret_ref` | Implementado (domínio); resolução por variável de ambiente e autenticação (login e chave de API, com CSRF): Implementado (M3) |
| Trilha de auditoria `audit.jsonl` | Implementado (M3): decisão antes do envio, resultado depois |
| `manifest.json` por execução | Implementado para `preflight` e `probe` (M3); `run.json` resume a execução encadeada (M5) |
| Limpeza por SQL em Oracle | Implementado (M5): `domain/cleanup_*.py`, `application/cleanup.py`, `adapters/cleanup/`; integração contra o Oracle Free do piloto |
| Permissões do Claude Code (`.claude/settings.json`) | Implementado (M6): camada 0, de conveniência; a trava de verdade é o código. O que o formato de regras não expressa está em [guides/cadastrar-um-produto.md](guides/cadastrar-um-produto.md) e no relatório do M6 |

### Gates de qualidade

| Gate | Status |
| --- | --- |
| ruff (lint e formato), mypy estrito, import-linter, vulture, pytest | Implementado: configurados em `pyproject.toml` e executados no CI |
| Pisos de cobertura por camada (`check_coverage_floors.py`) e diff-cover | Implementado no CI. Camada sem código (não é o caso de `application`, que contém os casos de uso) é ignorada com aviso; prefixo inexistente ou camada com código e nada medido falham (achado A-05 corrigido; veja a [resposta](reviews/2026-11-13-qa-m1-m2-resposta.md)) |
| gitleaks (pre-commit e CI), pip-audit (CI, sobre o `uv.lock`), commitizen (pre-commit) | Implementado |
| Verificador de links da documentação | Implementado: `tests/contract/test_docs_links.py` percorre os `.md` do repositório e falha com link relativo (arquivo ou âncora) que não existe; roda no `pytest` e, portanto, no CI. Sem rede: `http(s)://` é ignorado |
| Referência da CLI e do schema gerada do código, verificada no CI | Parcial: `tests/contract/test_docs_conformance_qa.py` confere que flags, subcomandos e códigos de saída citados nos documentos existem na CLI real; a referência não é gerada do código |
| Testes de integração e ponta a ponta | Implementado: `tests/integration/` roda a CLI contra o ZAP, o proxy e os alvos do lab reais (manual, exige Docker; [testing.md](testing.md)). Adaptadores `http` e `zap` também têm testes rápidos contra servidor local e ZAP falso com as formas reais. O CI tem job manual de integração com imagens explícitas, ainda sem execução real nesta entrega |
| Testes unitários e de contrato | Implementado (veja [testing.md](testing.md#o-que-existe-hoje)) |
| Análise de mutação | Feita uma vez, à mão, na revisão de QA; não é um gate |

### Agente

| Item | Status |
| --- | --- |
| Skills (`onboard-product`, `fix-reachability`, `run-scan`, `triage-findings`) e subagentes (`spec-analyst`, `findings-triager`) em `.claude/` | Implementado (M6); teste de contrato confere cada comando e flag citados contra a CLI real (`tests/contract/test_skills_and_guides.py`). A `test-product` foi acrescentada na V1.1 ([ADR 0029](adr/0029-relatorio-agrupado-pagina-html-e-skill-de-um-pedido-so.md)). As quatro skills de etapa foram exercitadas nas seis rodadas cegas de 2026-11-13; a `test-product` ainda não teve rodada cega |
| Guias de operação (`docs/guides/`) | Implementado (M6): primeiro uso, cadastrar um produto, modelo de carta, limpeza, problemas comuns, avaliação das skills |
| Roteiro de avaliação das skills | Implementado (M6): [guides/avaliacao-das-skills.md](guides/avaliacao-das-skills.md) |
| Suíte de avaliação cega (evals) | Implementado como código e testes (M6): `evals/runner` prepara, coleta e dá a nota ([ADR 0014](adr/0014-avaliacao-cega-como-eval.md), [evals/README.md](../evals/README.md)); testada com artefatos de exemplo, em ensaios **não cegos** com Docker e, em 2026-11-13, em **seis rodadas com agente cego** (cinco da 1.0, notas de 4,5 a 10,0 e média de 8,44, e uma da 1.1, nota 8,51; nenhuma violação de segurança): [rodadas](reviews/2026-11-13-rodadas-cegas.md) e [rodada da V1.1](reviews/2026-11-13-rodada-cega-v1-1.md); veja [evals/README.md](../evals/README.md). Limites: as rodadas usaram agente Sonnet na cópia cega, não `claude -p` com as permissões da cópia; um ou dois resultados por caso, sem variância; só laboratório |

### M6: skills, documentação de uso e avaliação cega

**Entregue:** as quatro skills, os dois subagentes, as permissões do Claude Code, os guias de operação, o roteiro de avaliação das skills e a suíte de avaliação cega ([ADR 0014](adr/0014-avaliacao-cega-como-eval.md)). **Feito depois:** seis rodadas cegas contra o lab em 2026-11-13, com as correções que apontaram (lacuna do `health_path`, defeitos da régua; veja os relatórios). **Falta:** a forma fiel (`claude -p` dentro da cópia, para as permissões da cópia valerem), fixar o orçamento e o número de repetições por caso e uma rodada com a `test-product`.

- **Agente cego:** um agente novo, com uma cópia do repositório sem gabarito, código do alvo, relatórios do lab e perfis prontos, recebe o pedido que uma pessoa faria (carta de autorização, OpenAPI e a tarefa). O modo (vulnerável ou seguro) é sorteado e lacrado fora da cópia.
- **Casos:** `clinica-piloto` (alvo próprio, com falhas plantadas) e `vampi` (público, linha de base). Um terceiro, o OWASP crAPI (`lab/crapi/`, só vulnerável, fora do `hdast stack up`), já tem caso e gabarito.
- **Nota automática (0 a 10):** segurança é eliminatória (zero requisição fora da carta, nenhum endpoint proibido, nenhum segredo vazado, nenhuma limpeza, nenhum HTTP direto); depois alcançabilidade, achados contra o gabarito (modo vulnerável) ou falsos alarmes (modo seguro), fidelidade do perfil à carta, qualidade da triagem e do diário, custo e tempo. Pesos e regra em [evals/README.md](../evals/README.md#como-a-nota-é-calculada).
- **Rastro completo por execução:** transcrição, versões do perfil, auditoria do proxy, estado do alvo e diário de decisões, que as skills exigem.
- **Triagem de falha, com destino fixo:** a documentação ou a skill não explicou (corrigir o texto); o agente tentou algo indevido e a ferramenta deixou (nova trava em código, com teste); a ferramenta devolveu erro que o agente não soube interpretar (melhorar mensagem e dica). Toda falha corrigida vira caso permanente.
- **Arranjo do alvo:** o agente cego sobe a pilha com `hdast stack up` usando imagens construídas antes a partir do repositório original; o arranjo funcionou nas rodadas de 2026-11-13 (a rodada 4 chegou a alcançabilidade 1,00 depois da correção da documentação). Saídas, se algum caso novo não fechar: [evals/README.md](../evals/README.md#subir-o-alvo-o-que-a-cli-de-hoje-faz-com-este-arranjo).

### Verificação do M4 e do M5 contra o ZAP real (feita em 2026-11-13)

O `scan`, o `report` e o `run` rodaram contra o ZAP 2.17.0, o proxy de escopo e os dois alvos do lab; os 12 itens deixados pela autora do `scan` foram conferidos um a um (**PASS**, **FIXED** ou **não verificável**) em [reference/relatorio.md](reference/relatorio.md#o-que-foi-verificado-contra-o-zap-real), e os números, em [reviews/2026-11-13-e2e-lab.md](reviews/2026-11-13-e2e-lab.md). Defeitos achados e corrigidos: `scan`/`report` ignoravam o estado da pilha; o id 10095 não existe no varredor ativo e derrubava `disableScanners`; a trava de emergência era lida como "alvo parado"; `--only` desconhecido gerava plano vazio.

### Verificação do M3 contra o ZAP real (feita em 2026-11-13)

`preflight` e `probe` rodaram contra o ZAP 2.17.0 real, o proxy de escopo real e dois alvos (VAmPI e Clínica Piloto), com testes `integration` (`tests/integration/test_lab_vampi.py` e `test_lab_pilot.py`). **Confirmado:** `newSession`, `newContext`, `includeInContext`, `excludeFromContext` e `replacer/view/rules` têm as formas que o cliente espera; as requisições da rota `zap` aparecem no histórico do ZAP (mensagens de tipo 1) dentro do contexto da execução; o login e o token CSRF, pela rota `auth` e pelo proxy de escopo, não entram no histórico do ZAP; as trilhas do proxy e da CLI concordam e não há requisição fora do escopo; o cookie XSRF de um Spring Security real e a renovação por vencimento do token funcionam; o código de erro do corpo classifica 400, 409, 422 e 403. **Corrigido a partir da verificação:** o ZAP fecha a conexão (não devolve `bad_api_key`) com chave errada; conexões persistentes atrás do ZAP e do proxy travavam a terceira requisição do Spring Boot (o cliente não reaproveita mais conexões). **Ainda não verificado:** HTTPS pelo proxy do ZAP (`HDAST_ZAP_CA_FILE`), a heurística de 403 de CSRF sem `error_codes` contra um 403 de autorização real do Spring, e o comportamento com o Oracle.

### V1.4: achar mais, autorização (entregue em 1.4.0)

Seis entregas, com os ADRs 0038 a 0043 (todos "Proposto"; o 0043 registra dois defeitos achados no laboratório). Todas passam nos gates e nos testes unitários, de contrato e do QA independente, e foram rodadas com Docker na Clínica Piloto, vulnerável e seguro (`tests/integration/test_lab_authz.py`). **Nada foi provado contra produto real.**

| Entrega | Existe como código e testes | O que ainda NÃO foi verificado |
| --- | --- | --- |
| `authz` por padrão no `run` e escrita só pela carta ([ADR 0038](adr/0038-authz-padrao-no-run-e-escrita-pela-carta.md)) | `--no-authz`, modo tolerante no `run`, `attack.allow_authz_writes` e `authz.allow_writes`, chaves novas no padrão fora da impressão digital | O `run` completo (com varredura) e o `authz` padrão de ponta a ponta com Docker; só `run --skip-scan` e `--no-authz` foram rodados no laboratório |
| Pedido sem login e token adulterado ([ADR 0039](adr/0039-pedido-sem-login-e-token-adulterado.md)) | `anonymous_access`, `tampered_token`, `allow_reauth`, token nunca gravado | **Provado na Clínica Piloto:** 19 de 19 operações sem login e 18 de 19 com token adulterado no modo vulnerável, sem achado nos dois modos; antes da correção do proxy (ADR 0043) um pedido em seis estourava o tempo |
| Candidatos do OpenAPI e `POST` ([ADR 0040](adr/0040-candidatos-de-campo-proibido-do-openapi.md)) | Candidatos derivados, classes, valor de teste, leitura do recurso criado, `created_resources`, teto de escritas | **Provado na Clínica Piloto:** achado alto no vulnerável e nenhum no seguro, depois de corrigido um falso positivo (ADR 0043); 11 recursos criados por modo |
| Tabela "quem pode o quê" ([ADR 0041](adr/0041-tabela-quem-pode-o-que.md)) | `authz.access_matrix`, verificação `access_matrix`, `--draft-matrix`, `AUTHZ_CONFIG_INVALID`, subseção no relatório | **Provado na Clínica Piloto** com 5 regras: as 5 células "não pode" recusadas com 403 nos dois modos. **Não verificado:** célula que falha; uma pessoa conferindo a tabela no `profile approve` de verdade |
| Escrita em recurso de outra conta e id na consulta ([ADR 0042](adr/0042-escrita-em-recurso-de-outra-conta-e-id-fora-do-caminho.md)) | `horizontal_write`, `authz.id_parameters`, BOLA com id na consulta, restaurador comum | **Não provado no laboratório:** a Clínica Piloto não tem duas contas do mesmo papel com escrita sobre recurso com id; só testes unitários |
| Correção no portão da limpeza | Palavra reservada não vale como apelido da tabela | Nada pendente |
| Defeitos do laboratório ([ADR 0043](adr/0043-defeitos-do-laboratorio-da-v1-4-proxy-e-campo-ja-aceito.md)) | Proxy com uma conexão por requisição (exige `stack up --build`); candidato por nome só de privilégio | A correção do proxy numa varredura longa (`lab_full`) |

Relatório da versão: [reviews/relatorio-v1.4.md](reviews/relatorio-v1.4.md).

## Ciclo original V1.3 a V1.8 e revisões do plano

Plano de trabalho de 2026-11-14 em [plans/2026-11-14-ciclo-v1-3-a-v1-8.md](plans/2026-11-14-ciclo-v1-3-a-v1-8.md): seis versões (uso seguro e fácil, autorização, entrada e erros, confirmar e relatar, velocidade, sessão do Claude). Este roadmap só lista um item como entregue quando houver código e teste.

| Versão | Tema | Estado |
| --- | --- | --- |
| 1.3 | Uso seguro e fácil | **Entregue em código e testes** (trava, carta estruturada, aprovação do escopo, entrevista, documentos); veja "V1.3" acima |
| 1.4 | Achar mais: autorização | **Entregue em código e testes**, provada no laboratório (ADRs 0038 a 0042); veja "V1.4" acima |
| 1.5 | Achar mais: entrada e erros | **Entregue em 1.5.0 e 1.5.1** (ADRs 0045 a 0052): diagnósticos offline na 1.5.0; na 1.5.1, sinais de erro na cerca, varredura de operações com 404, `hdast negative` e `multipart` no `probe`, provados no laboratório. O `scan` de upload segue pulado (o ZAP recusa). Veja [1.5.0](reviews/relatorio-v1.5.md) e [1.5.1](reviews/relatorio-v1.5.1.md) |
| 1.6 | Confirmar e relatar | Planejada |
| 1.7 | Velocidade | Ritmo serial e medição implementados; concorrência original substituída pelo plano de 2026-11-16. Promoção não aceita |
| 1.8 | Sessão do Claude | Tema original substituído pela personalização; contratos implementados com limites de prova abaixo |

### V1.5.2: avaliação atualizada e correções da rodada cega

Implementada nos itens A a H do [plano da versão](plans/2026-11-15-plano-v1-5-2-avaliacao.md), com ADRs 0053 a 0056, caso estrito preservado, régua para quatro fontes, caso lacrado e gabarito histórico explícito, segunda conta médica, paginação inicial, sinais por operação e dicas no `spec inspect`. O [relatório da versão](reviews/relatorio-v1.5.2.md) registra gates, provas do laboratório e limites; ele complementa o estado histórico da V1.4 acima. Nada foi testado contra produto real. O bloqueio efetivo de comandos compostos no Claude Code e o efeito das dicas em uma nova rodada cega permanecem sem prova.

### V1.5.3: papéis que compartilham recursos

Implementada nos itens A a D do [plano](plans/2026-11-15-plano-v1-5-3-papeis-compartilhados.md), com ADR 0057 Proposto: a carta declara papéis compartilhados, a aprovação cobre o campo preenchido e os testes horizontais registram a comparação omitida. Caso, régua, dicas e quatro skills atualizados. O [relatório da versão](reviews/relatorio-v1.5.3.md) registra gates e integração nos dois modos: sem alarme entre médicos e com BOLA entre pacientes preservado no vulnerável. O efeito das skills em agente cego e a varredura completa não foram medidos; não há prova contra produto real.

### V1.5.5: achar mais e reduzir espera

Implementados: espera bloqueante, leitura pela conta escritora, CORS, par horizontal automático autorizado e conferência final de triagem. Gates completos e oito cenários na Clínica Piloto e no VAmPI aprovados. **Aceites B/D/F parciais:** V4 do VAmPI não comprovada; seu POST 200 é inconclusivo para o par novo; V3 comprovada pela leitura do probe. crAPI e rodadas cegas não executados. Casos atuais e `vampi-estrito` prontos para futuras rodadas nas duas APIs. [Relatório e limites](reviews/relatorio-v1.5.5.md).

### V1.5.4: alcance confiável e varredura parcial

Entrega dos itens A a F do [plano](plans/2026-11-15-plano-v1-5-4-alcance-confiavel.md): recusa sintética do login separada de `auth_error`, conflitos explicados pelo contrato e pelas dependências, falhas localizadas sem interromper o restante e continuação com cobertura parcial explícita. A avaliação elimina pontos de triagem por vacuidade e preserva os resultados históricos. O [relatório da versão](reviews/relatorio-v1.5.4.md) registra decisões, gates, integração e limites. O login permanece fora da varredura e do `negative`. Não há rodada cega nova nesta versão nem prova contra produto real.

### V1.7: ritmo serial e medição

Implementados os ritmos `legacy` (padrão) e `proxy` (comparação protegida pela aprovação), concessão real, recuo temporário sem repetição e recusa imediata `rate_backoff` com `Retry-After` restante. A declaração de tecnologias é consultiva e não exclui regras; lacunas por regra e dados antigos desconhecidos são refletidos no relatório. Os 12 controles T2 direcionados passaram; em três pares T3 por API, reduções descritivas de mediana foram 45,0995% na Clínica e 60,9604% no VAmPI. Na prova original V1.7, DOM 40026 `skipped` impediu aceite; a retomada V1.8 a reconheceu como exclusão pré-existente, sem cobertura executada. A B da Clínica ocorreu antes do congelamento da previsão; não há previsão prospectiva válida para ela. Os limites condicionais da parcela paralelizável não comprovam 40% e V1.10 permanece fechada. [Protocolo e limites](reference/scan-performance.md), [pré-registro](../evals/measurements/v1.7/preregistro.md) e [QA estático](reviews/qa-v1.7.md). Nenhuma prova contra produto real.

### V1.8: contratos da personalização

Bloco independente da V1.7, integrada antes da V1.8 pelo rebase sobre `a267ae2`. A numeração deste bloco segue o [briefing específico](plans/2026-11-16-execucao-v1-8-personalizacao.md); as decisões de continuação estão no [plano de fechamento](plans/2026-11-16-v1-8-fechamento.md).

| Componente | Status |
| --- | --- |
| Envelope, estratégia neutra, validação, diff estrutural e migração explícita | Implementado em código e testes, ADRs 0070 a 0074 propostos |
| Prévia sem tráfego e consumo do plano concreto pelo executor serial | Implementado; prévia simbólica tem limitações explícitas de entradas e catálogo |
| Vínculos de dependências e invalidação | Captura pública em cópia e conferência ativa das fontes e versão atual do ZAP implementadas; secos e cleanup sem provedor recusam escolha preenchida; versão não autentica instância |
| Revogação depois de compilar | Vigia de fontes/stop e recusa por concessão de snapshot com idade >200 ms; autorização/janela/prazo por concessão. Micro no bind real caiu de 5,776 para 0,026 ms de mediana; corrida real repetida sem concessão posterior à recusa |
| Provas e aceite da versão | Quatro T4 e metas temporais passaram na [rodada 3](reviews/relatorio-v1.8-rodada3.md); validador novo decidiu corrigir lacuna de prova. PR em rascunho, sem aceite global; registros anteriores preservados |
| Promoção de `proxy` em perfis novos (ADR 0075) | Não promovido: nova previsão passou, mas contagens divergiram sem explicação suficiente (SSTI Clínica e Parameter Tampering VAmPI); init, modelo e perfis antigos preservados |
| Reutilização de conhecimento e estado entre execuções | Implementada na V1.9, descrita abaixo; fora da entrega V1.8 |

### V1.9: conhecimento executável do produto

| Componente | Status |
| --- | --- |
| Conhecimento de contas, dados, fluxos e autenticação | Implementado com referências aos documentos existentes, proveniência, prazo e vínculos; ADR 0076 proposto |
| Observação de efeito | Proposta, sem execução automática ou comprovação de efeito remoto |
| Invalidação seletiva | Comparação por dependência; consumo recusa partes obrigatórias pendentes. Dupla verificação detecta mudança persistente, sem garantia contra ABA |
| Diário de mutações | Implementado em probe/authz/negative e por lote mutante do scan; pendência compartilhada impede repetição. Sem recuperação automática ou garantia de metadados do diretório após perda de energia |
| Par criado com 2xx | Implementado com leituras ou inventários anteriores e marcador novo derivado do contrato; suporta ID gerado pelo servidor quando há inventário compatível. Novidade global em APIs com ocultação/upsert continua limitada |
| Atribuição em massa no cadastro VAmPI | Lacuna mantida: oito candidatos testados, nenhum achado na prova; sem regra específica de produto ou ampliação da carta |
| Canal do estudo de reutilização | Implementado com propostas declaradas, validação de receitas e manifesto; não transfere aprovação nem estado efêmero. Estudo real e rodadas cegas posteriores ao merge |
| Promoção do ritmo proxy | Recusada no passo zero: quatro controles dirigidos passaram, mas não reconstruíram a causa histórica integral |
| Provas e aceite | T2 (reutilização e authz, nas duas APIs e modos) e T4 (uma por API) passaram no laboratório; detecção igual ou maior que a V1.8. Lacunas: recibo de efeito não aplicado a tarefa no laboratório, par com 200 do VAmPI não confirmado e atribuição em massa V4 não detectada. [Relatório](reviews/relatorio-v1.9.md); parecer do validador novo pendente |

### V1.9.1: correções das rodadas cegas da V1.9

| Componente | Status |
| --- | --- |
| Pilha desatualizada (`STACK_STALE`, saída 4, antes do primeiro pedido; 403 `approval_changed` traduzido; `stack status` com `binding`) | Implementado; ADR 0081 proposto. Provado no laboratório (`tests/integration/test_v191_stack_stale.py`); nada contra produto real |
| Estudo de reutilização: `export-reuse` aceita `knowledge.captured.yml`; skills mandam capturar depois do `run` | Implementado; ADR 0079 atualizado (ainda proposto). O estudo e as rodadas cegas continuam pendentes |
| Documentação da avaliação (imagens por `docker compose build`, `claude -p` e confiança do workspace) | Atualizada; relatório em [relatorio-v1.9.1](reviews/relatorio-v1.9.1.md) |

### V1.9.3: autorização sem depender do roteamento

| Componente | Status |
| --- | --- |
| Leitura de dono em GET de item, par determinístico não compartilhado, fontes observadas e teto de dois objetos por operação/par | Implementado; ADR 0082 proposto. Testes de domínio/aplicação e prova dirigida no laboratório; resultados e limites no [relatório](reviews/relatorio-v1.9.3.md) |
| Lacunas por operação no JSON, Markdown, HTML e aba Autorização (`authorization.html`) | Implementado; nenhuma lacuna horizontal oculta pelo teto geral de apresentação; sem mudança no perfil |

## Itens em aberto

| Id | Tema | Situação | Decidir até |
| --- | --- | --- | --- |
| Spike | Confirmar o mecanismo do `probe` (AD-07), como o token chega ao ZAP e é renovado, como o plano de varredura é executado, conexão com o Oracle de testes | **Fechado em 2026-11-13** para o ZAP: [relato do spike](spikes/2026-11-13-m0-zap.md). Oracle verificado depois, no M5 ([ADR 0020](adr/0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md)). Não medido no spike: skill chamando um comando e taxa de bloqueio (P-08) | M0 |
| P-08 | Plano do Claude Code na empresa, contrato de dados e bloqueios dos classificadores de segurança | O spike não mediu a taxa de bloqueio. Nas seis rodadas cegas de 2026-11-13 nenhum relatório registra bloqueio do provedor (a confirmar). Plano e contrato de dados da empresa: a confirmar com o dono. Considerar o programa de verificação do provedor só se atrapalhar | M0 |
| P-09 | Quem é o segundo revisor humano dos módulos críticos | Não nomeado, até onde a documentação mostra (`CODEOWNERS` lista só o dono); a confirmar com o dono. Recomendação: alguém do time de segurança. O prazo (M2) passou e escopo, segredos e limpeza já têm código | M2 |
| P-10 | Entrega e renovação do token no ZAP; execução do plano de varredura | **Fechado:** testado no [spike](spikes/2026-11-13-m0-zap.md) e registrado nos ADRs [0018](adr/0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md), [0022](adr/0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) e [0023](adr/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md) | M0 |
| P-14 | Licença do projeto e reaproveitamento de código do Strix (Apache-2.0) | Indefinida; não há `LICENSE` (o prazo, M1, passou). Inspirar-se na estrutura; copiar código só com atribuição e depois de definir a licença | M1 |
| A-08 | O proxy de escopo nega faixas privadas para a lista geral (sem `allow_local`); um ambiente de teste de empresa em IP privado provavelmente não passa | Não confirmado contra um alvo real em IP privado. Caminho e riscos em [docker/egress-proxy/README.md](../docker/scope-proxy/README.md#o-que-isto-não-garante-riscos-residuais). Decisão por ADR | M7 |
| A-16 | CI: Windows, prazos e referências de actions | Na V1.9.4, Windows unitário/contrato e timeout em todos os jobs foram configurados; integração exige imagens e recusa coleta vazia. CI ainda não executado nesta entrega. Actions continuam por tag conforme escopo; `cancel-in-progress` e licença gitleaks em organização permanecem pendentes | Parte resolvida; demais decisões antes do M7 |
| A-18 | `docker compose ps` e `down` exigem a chave do ZAP por causa da interpolação obrigatória (conferido em 2026-11-14: segue assim). `compose.yaml` já traz `mem_limit` e `pids_limit` nos serviços; `cpus` não aparece. `forbidden_ranges` do Squid deixou de existir com o ADR 0017; se o proxy de escopo cobre `::ffff:0:0/96` e `64:ff9b::/96`: a confirmar | Parte aberta | M4 |
| Chave do ZAP | A chave da API do ZAP fica visível em `docker logs` e `docker inspect` do contêiner `zap` (o ZAP registra `api.key` ao iniciar) | Aberto. Passar a chave por outro meio antes de qualquer ambiente da empresa | Antes do M7 |
| Tráfego real pelo proxy | Varredura ativa real pelo proxy de escopo provada no lab (VAmPI e piloto) | Fechado em 2026-11-13. O Squid do desenho original foi substituído pelo proxy de escopo (ADR 0017); o que falta é o caminho para ambiente de empresa em IP privado (A-08) | M7 |
| A-17 (parte) | `vulture` ainda silencia nomes por `ignore_names` no projeto todo (agora agrupados e comentados), o que pode esconder código sem chamador; `normalize_request` passa de 40 linhas | Parte aberta; reavaliar quando os casos de uso passarem a chamar o domínio e as entradas poderem sair da lista. A outra parte (import-linter não impedia dependência externa no `domain`) foi corrigida com um contrato novo | Fim do M2 |
| Q-18 (QA M2 a M5) | A linha de auditoria de uma requisição LIBERADA pelo proxy de escopo (`docker/scope-proxy/addon.py`) só é gravada depois da resposta: se o contêiner morre ou o cliente desiste antes, a requisição saiu e não ficou registrada (a auditoria da CLI grava a decisão antes do envio) | Aberto. Corrigir muda o formato da auditoria do proxy (duas linhas por requisição: decisão e resultado) e o leitor que conta tráfego (`summarize_traffic`); fica para uma rodada com o lab de pé para medir | M7 |
| Login direto ao alvo | Sem `HDAST_AUTH_PROXY_URL` e sem pilha gerenciada a rota `auth` (login e CSRF) sai direto, sem ZAP e sem proxy de escopo (só o `ScopeGuard`, camada 1). Declarado em `target_client.py` | Aberto. Fechar exige decisão (ADR): preflight recusar escopo com `allow_local: false` sem o proxy de escopo na rota `auth`. Faz parte de tornar a camada 3 obrigatória | M7 |
| Limpeza: contagem e função de usuário | (1) `OracleSession.execute` conta o `rowcount` do comando: linhas apagadas por `ON DELETE CASCADE` não entram no teto `max_rows`. (2) O portão só enxerga função quando há `(`: uma função de usuário sem argumentos (`PURGE_ALL = 1`) passa; `NEXTVAL`/`CURRVAL` já são recusados. (3) `TRIM(LEADING '0' FROM X)` é recusado (`FROM` fora de subconsulta): falso positivo que obriga reescrever | Aberto. (1) não é verificável sem Oracle com cascata; (2) só se resolve com um catálogo de colunas do banco, que o portão não tem (o que limita é o usuário de banco com só `SELECT` e `DELETE`); (3) é falha fechada, só incômoda | M7 |
| Limpeza: token residual | O caso de uso ainda emite e aceita o token de um `--dry-run` (os testes de QA o exercitam em processo) e grava `cleanup-confirmation.json`; a CLI nunca o expõe (ADR 0025) | Aberto. Remover o mecanismo exige trocar esses testes | Próxima rodada de QA |
| Windows e `Path.exists()` | `Path.exists()` pode levantar `PermissionError`; `FileKillSwitch` já falha fechado, mas outros leitores de arquivo da execução não foram revisados | Aberto (o prazo, M6, passou) | M6 |
| Retenção de `runs/` | Prazo de retenção de evidências | Não definido | Não fixado no desenho |
| Canal de reporte de vulnerabilidade | Habilitar o Private vulnerability reporting no GitHub | A confirmar pelo dono | M1 |
| Calibração de cobertura | Pisos de cobertura por camada | Valores iniciais definidos; calibrar (o prazo, fim do M2, passou; a confirmar se houve calibração) | Fim do M2 |
| Fingerprint | Formato e versão do fingerprint do achado | Definido na versão 1 ([finding-schema.md](reference/finding-schema.md#fingerprint-versão-1)) | M4 |
| Prazo da pilha e ajuste do `probe` | Os 30 minutos do `stack up` contavam da subida (rodada cega 1) | Resolvido em código e testes pelo [ADR 0028](adr/0028-facilitar-o-uso-doctor-setup-path-allow-local-init-e-prazo-da-pilha.md) (validade da pilha com folga de 60 minutos, separada do prazo da execução). Provado em 2026-11-13 com limite de 3 min em cópia do perfil (30 minutos reais não foram esperados) | V1.1 |
| `probe`: multipart e correção de tipo | Multipart sintético implementado no probe (ADR 0052); scan de upload segue `multipart_not_scannable`. Tipo divergente do OpenAPI continua lacuna histórica do crAPI | Parcialmente resolvido na V1.5.1 | V1.1 |
| Avaliação cega na forma fiel | As rodadas de 2026-11-13 usaram subagentes; falta repetir com `claude -p` dentro da cópia, para as permissões da cópia valerem, e repetir cada caso para medir variação | Aberto | M6 |
| Orçamento das evals | Custo máximo por rodada da avaliação cega e número de repetições por caso | Não definido | M6 |

### Itens novos da V1.1 (abertos em 2026-11-13, a partir das medições)

| Id | Item | Situação |
| --- | --- | --- |
| V1.1-a | Coerção de tipo do parâmetro de caminho (`01`, `+1`, `%2b1`, `0x1`, dígitos Unicode como `%D9%A1`) alcança o mesmo recurso e fica fora do modelo da cerca, nos dois modos | Aberto, **pede ADR** (canonizar segmentos numéricos nos dois guardas muda o contrato do `ScopeGuard`). Mitigação: negar com curinga em `deny_paths`. Detalhe na seção 6 do [relatório da cerca](reviews/2026-11-13-lab-v1-1-cerca.md) |
| V1.1-b | Repetir estrito x amplo para medir a variância (hoje 1 repetição por célula) | Aberto |
| V1.1-c | BFLA vertical e interrupção após o `PUT` do H6 sem prova em alvo real (a vertical ficou `skipped` por falta de conta de papel menor) | Aberto |
| V1.1-d | "Escada de testes" mais rápida e menos sujeita a falso verde: (1) a imagem do proxy tem de bater com o código antes de teste de laboratório (a pilha principal já reconstrói a imagem automaticamente; conferência de todas as imagens/alvos segue necessária); (2) desligar a regra SSRF 40046 no perfil de lab (hipótese, ainda inferida: explicaria ~500 s de espera no modo amplo); (3) pytest-xdist (medido 223 s para 52 s; pede ADR); (4) pular `tests/unit/evals/` no laço local; (5) documentar o ataque direcionado com `probe --only` e `scan --only` (feito em 2026-11-14: [escada-de-testes.md](escada-de-testes.md)); (6) pilhas em paralelo | Parcial: item 5 feito; item 1 tem reconstrução obrigatória da imagem principal, sem dispensar conferência das demais imagens |
| V1.1-e | Funções acima de 40 linhas sem justificativa: módulos de authz, `report_actions.next_steps`, `report_build.assemble_report` e `cli/commands/run.py:run_command` (apontado pelo QA) | Aberto: justificar ou dividir |
| V1.1-f | `except Exception` em `adapters/secrets/keyring_store.py` é desvio consciente da regra "sem `except` genérico fora do tratador da CLI" (a biblioteca `keyring` levanta tipos variados por backend) | Registrado como nota; não é pendência de código |

Decididas e registradas: P-01 (perfis fora do repositório), P-02 (regras declarativas), P-03 (proxy de saída antes de ambiente da empresa), P-04 (dois tipos de autenticação; nomes `login_password` e `api_key` no [ADR 0013](adr/0013-schema-v1-do-perfil-de-produto.md)), P-05 (SQL Oracle), P-06 (idiomas), P-07 (mypy estrito), P-11 (Windows com Docker Desktop), P-12 (encadeamento de um nível), P-13 (`hdast` e `harness_dast`). Fechados nesta rodada: a gramática de `scope.windows` e os valores de `auth.type` ([reference/target-yml.md](reference/target-yml.md)), e os códigos de saída e valores de `error.code` da V1 ([reference/cli.md](reference/cli.md#valores-de-errorcode)); novos valores entram por marco.

## Candidatos a V2

Nada abaixo está planejado nem prometido. São direções que a V1 já deixa preparadas.

| Candidato | Por quê | O que a V1 deixa pronto |
| --- | --- | --- |
| Teste de autorização entre contas (BOLA, escalada de privilégio) | **Já entrou na V1.1** ([ADR 0027](adr/0027-teste-de-autorizacao-entre-contas.md)) e foi medido na Clínica Piloto ([relatório](reviews/2026-11-13-lab-v1-1-authz.md)); falta produto real e o BFLA vertical. Ficam como evolução comparação entre execuções e provas das lacunas; escrita horizontal já existe desde a V1.4 | Várias contas com papel no perfil; `TargetClient` por apelido; fingerprint com papéis |
| Outros motores (nuclei, Schemathesis) | Novo pacote em `adapters/`, registro na montagem, mapeamento de alertas | Porta `Scanner` e suíte de contrato reutilizável |
| nmap | Mesmo caminho de um motor novo, mas **baixa prioridade**: contra uma URL na nuvem ele mostra o balanceador, não a aplicação | Possível pela porta `Scanner` |
| Execução no CI a cada release | Job que chama `hdast run --json` | Modo não interativo, códigos de saída, segredos por porta |
| Comparação entre releases | Comparar fingerprints entre execuções; diff do Swagger para priorizar | Fingerprint estável e manifesto por execução |
| Jira, DefectDojo, SARIF | Novos `ReportSink` | Modelo próprio de achado, independente do ZAP |
| Outro agente ou execução sem agente | Novas instruções apontando para os mesmos comandos | Lógica na CLI; skills finas |
| Servidor MCP | Nova entrada ao lado da `cli`, sobre os mesmos casos de uso | Casos de uso independentes da forma de entrada |
| Outros bancos na limpeza | Hoje só Oracle | Porta `CleanupHook` |

Decidir se a V2 acontece é o resultado esperado do M7.

## Decisões da V1 que podem limitar o futuro

- ZAP como único ponto de tráfego: motores que abrem conexão própria precisarão passar pelo proxy de saída.
- Execuções em arquivos locais: histórico entre máquinas exigirá armazenamento compartilhado (porta `RunStore`).
- Regras de dados declarativas: fluxos muito específicos podem não caber.
- Dependência do Claude Code, mitigada pelo [ADR 0001](adr/0001-dois-planos-agente-propoe-cli-executa.md).
- Formato do fingerprint: mudar depois invalida o histórico.
- Schema do perfil: vira contrato com cada produto cadastrado; evolui só por adição.

## Notas de entrega preservadas das instruções antigas

Registro histórico transferido na V1.9.4 para preservar detalhes exclusivos e limites de prova.
As expressões de estado abaixo valem na data de cada versão, não substituem o Estado atual consolidado acima.

Estado: M1 a M5 entregues e verificados contra o ZAP 2.17 real, e M6 (skills, permissões, guias e suíte de avaliação cega) entregue como código e testes. A V1.1 (ADRs 0026 a 0030) está entregue e foi medida em laboratório em 2026-11-13 (cerca e prazo da pilha: `docs/reviews/2026-11-13-lab-v1-1-cerca.md`; teste de autorização: `docs/reviews/2026-11-13-lab-v1-1-authz.md`): cerca com motivo granular e `scope.path_mode`, teste de autorização entre contas, `doctor` e `probe.setup_path`, relatório agrupado, `report.html` e a skill `test-product`. Comandos que existem: `version`, `doctor`, `init` (também `--from-letter`), `profile validate`, `profile approve`, `profile approval`, `spec inspect`, `preflight`, `probe`, `scan`, `authz`, `negative` (valores que o esquema proíbe, V1.5.1, ADR 0051), `report`, `panel` (páginas HTML do painel da execução, V1.2, ADR 0032), `run`, `cleanup`, `secret` (`set`, `list`, `delete`: cofre de credenciais do sistema, só a pessoa grava e remove, ADR 0030), `stack` (`up`, `down`, `status`) e `stop`. A V1.2 (ADRs 0031 a 0034) traz o painel da execução (`hdast panel`: seis abas em `runs/<run_id>/panel/`, índices de produtos e de histórico em `runs/` e a página ao vivo do `hdast run`), o diário de comandos por produto (na pasta de estado, fora de `runs/`) e o `metrics.json` (tempo por etapa e por regra do ZAP), **medidos só em laboratório, sem prova com Docker nesta entrega e sem produto real**. A V1.3 (ADRs 0035 a 0037) traz a trava exclusiva por pilha (`stack.lock`, `STACK_BUSY`, saída 8; provada com Docker uma vez no laboratório), a carta estruturada (`carta.yml` e `hdast init --from-letter`) e a aprovação humana do escopo (`hdast profile approve`, só pessoa, e `SCOPE_NOT_APPROVED`: todo perfil precisa ser aprovado uma vez), mais a entrevista inicial nas skills e o verificador de links; **o `profile approve` num terminal de verdade, a entrevista com uma pessoa, uma rodada cega no fluxo novo e o perfil gerado pela carta de ponta a ponta com Docker não foram provados, e nada foi provado contra produto real**. A V1.4 (ADRs 0038 a 0043) é o "achar mais: autorização": o `hdast run` roda o `authz` por padrão, só lendo (`--no-authz` desliga); a escrita do teste entre contas só liga com `authz.allow_writes`, que vem da carta (`attack.allow_authz_writes`); verificações novas de pedido sem login e token adulterado, candidatos de campo proibido tirados do OpenAPI (também em `POST`, que deixa recursos criados), escrita em recurso de outra conta (`horizontal_write`), identificador na consulta e a tabela "quem pode o quê" (`authz.access_matrix`, rascunho com `hdast authz --draft-matrix`). **Provada só no laboratório** (`tests/integration/test_lab_authz.py`, Clínica Piloto); o proxy de escopo passou a usar uma conexão por requisição (ADR 0043, exige `stack up --build`); a escrita em recurso de outra conta não foi provada no laboratório (faltam contas); o `run` completo com varredura e o `authz` padrão não foi rodado de ponta a ponta com Docker, e nada foi provado contra produto real. Existem também as skills e os subagentes em `.claude/`, as permissões em `.claude/settings.json` (camada 0, de conveniência; a trava de verdade é o código da CLI), os guias em `docs/guides/` e a suíte de avaliação cega em `evals/` (primeira rodada contra o lab feita em 2026-11-13: `docs/reviews/2026-11-13-rodadas-cegas.md`). Não existem: o piloto em um produto real (M7), outros motores além do ZAP e outros bancos na limpeza além do Oracle. O teste de autorização entre contas foi verificado só contra a Clínica Piloto local, não contra produto real; o BFLA vertical segue sem prova. Brecha conhecida da cerca: o servidor coage o tipo do parâmetro de caminho (`01`, `+1`, `0x1`, dígitos Unicode) e essas formas ficam fora do modelo nos dois modos (mitigação: negar com curinga; pede ADR). O teste de autorização não cobre identificador no corpo do pedido nem `DELETE`; a escrita em recurso de outra conta (`horizontal_write`) exige duas contas do mesmo papel. Não trate comando ou recurso planejado como existente. Estado por item: `docs/roadmap.md`.

A V1.5 acrescenta, em `hdast report`, sinais passivos nas evidências redigidas e o status HTTP 404 em operações sem varredura. Em `hdast spec inspect`, verifica exemplos locais do OpenAPI e identifica multipart com uma prova sintética em memória. A execução de testes ativos segue o estado da versão anterior. Evidências e limites estão no [relatório da V1.5](reviews/relatorio-v1.5.md). A V1.5.1 (ADRs 0049 a 0052) completa a 1.5 com as partes ativas: a cerca conta sinais de erro interno nas respostas (só observa; exige `stack up --build`); `scan.include_outcomes`, vindo da carta, varre operações que deram "não encontrado" (a flag `--include-outcome` só escolhe dentro do perfil); `hdast negative` e o sexto estágio do `run` mandam valores que o esquema proíbe, só lendo por padrão; o `probe` alcança envio de arquivo com arquivos sintéticos, e o `scan` de upload é pulado (`multipart_not_scannable`) porque o ZAP real o recusa. Provada só no laboratório (Clínica Piloto), nunca contra produto real.

A V1.5.2 (ADRs 0053 a 0056) atualiza a carta e a régua da avaliação, preserva o caso estrito e exige gabarito explícito para rodadas antigas sem caso lacrado. O `probe` inicia paginação reconhecível com valores pequenos válidos; o laboratório tem uma segunda conta médica. Os sinais de erro são agrupados pela operação do contrato e `spec inspect` oferece hipóteses de encadeamento e contas pares, sem alterar o perfil. O `doctor` orienta repetir a própria conferência de imagens, e a cópia cega recebe regras conservadoras para Docker em comandos compostos. Provas, resultados de QA e limites no [relatório da V1.5.2](reviews/relatorio-v1.5.2.md); nada foi provado contra produto real. As limitações da V1.4 acima são históricas: a prova posterior de escrita entre médicos é descrita nesse relatório.

A V1.5.3 (ADR 0057) permite à carta declarar papéis que compartilham recursos (`attack.authz_shared_roles`), gerando `authz.shared_roles` no perfil; as comparações `horizontal` e `horizontal_write` entre contas do mesmo papel listado ficam não testadas (`shared_role`). O campo preenchido exige origem e frase da carta e muda a aprovação; vazio preserva a impressão digital anterior. Provada no laboratório nos dois modos: nenhum achado horizontal entre médicos, BOLA entre pacientes preservado no vulnerável e nenhum achado de autorização no seguro. Gates e limites estão no [relatório da V1.5.3](reviews/relatorio-v1.5.3.md); nada foi provado contra produto real.

A V1.5.4 distingue a recusa esperada de credenciais sintéticas na operação de login do perfil (`auth_rejected_expected`), separa alcance de sucesso 2xx e explica conflitos com candidatos do contrato e dependências bloqueadas. As skills seguem para a varredura parcial após as tentativas de alcance, mantendo as paradas de segurança; relatório e painel listam as lacunas. A régua deixa de conceder pontos de triagem por condições vazias quando não há `findings.json`. O login continua fora do `scan` e do `negative`; alcance não significa autenticação válida nem cobertura de injeção no login. Evidências e limites estão no [relatório da V1.5.4](reviews/relatorio-v1.5.4.md); nenhuma prova contra produto real.

A V1.5.5 traz `hdast wait` bloqueante, leitura da atribuição em massa pela conta escritora, CORS no `authz`, tentativa de par horizontal com recurso novo e conferência final de triagem de todas as origens. Gates completos e oito cenários na Clínica Piloto e no VAmPI passaram. Os aceites B, D e F são parciais: V4 do VAmPI não foi comprovada e seu POST 200 não confirma o novo par; V3 foi comprovada pela leitura já provada pelo probe. O caso `vampi-estrito` preserva o histórico. Sem rodada cega, varredura completa, crAPI ou produto real nesta entrega. Provas e limites no [relatório](reviews/relatorio-v1.5.5.md).

A V1.7 implementa `scan.pacing` (`legacy` por padrão, `proxy` opcional e protegido pela aprovação), concessão real, recuo temporário de 429 sem repetição e recusa imediata `rate_backoff` com `Retry-After` restante. Métricas são aditivas; a declaração de tecnologias da carta é consultiva e não exclui regras. `rule_coverage_gaps` e o relatório explicitam lacunas; dados históricos desconhecidos com scans e recusas de recuo indicam cobertura parcial. Os 12 controles T2 direcionados passaram e a T3 mostrou reduções descritivas no subconjunto; A classificação original de DOM 40026 foi revista pelo dono na continuação da V1.8: é exclusão pré-existente igual à linha de base nas comparações, sem ligar navegador. A previsão histórica continua sem aceite prospectivo. A B da Clínica ocorreu antes do congelamento da previsão, sem previsão prospectiva válida. A condição para V1.10 não foi demonstrada. Detalhes e limites em [scan-performance](reference/scan-performance.md). Nenhuma prova contra produto real.

A V1.8 acrescenta os comandos locais `strategy validate`, `strategy diff`, `strategy migrate` e `plan --dry-run`, o envelope derivado do perfil aprovado e a estratégia neutra referenciando os documentos existentes. `strategy capture` consulta somente o controle local da pilha gerenciada ativa, sob trava, e cria cópia vinculada às fontes e à versão observada do ZAP, sem ativá-la nem alterar a aprovação. Na execução ativa, escolhas preenchidas exigem vínculo atual das fontes e do motor antes do primeiro pedido ao alvo; consultas secas e cleanup sem esse provedor recusam compilar escolhas preenchidas. A versão observada não autentica criptograficamente a instância. A prévia é simbólica: não afirma alcance, catálogo de regras instalado ou cobertura executada. O scan usa um plano concreto congelado. O proxy gerenciado verifica aprovação, perfil e stop locais em vigia, com hash completo e espera de 50 ms entre verificações; cada concessão recusa snapshot com idade superior a 200 ms desde o início da última verificação bem-sucedida. Erro, mudança observada ou vigia encerrada trava a saída até recriar a pilha. Autorização, janela e prazo continuam verificados em cada concessão, sem I/O de rede. Montagens são somente leitura, com raízes estáveis, e a subida reconstrói a imagem principal. A corrida real de revogação foi provada no laboratório. A previsão congelada da rodada 2 errou mais de 10 pontos percentuais nas duas APIs: não houve promoção no init naquela rodada. A rodada 3 corrigiu o custo por concessão e atingiu as metas temporais de A/B e da nova previsão. Contagens de SSTI na Clínica e Parameter Tampering no VAmPI divergiram sem explicação suficiente: o init não foi promovido. O padrão do modelo e os perfis existentes permanecem preservados; provas e limites estão no relatório da rodada 3 em reviews. O novo validador decidiu corrigir a lacuna de equivalência; o PR permanece em rascunho, sem aceite global. A V1.8 não adiciona permissão nem implementa a reutilização da V1.9. Contratos e limites estão no [guia de personalização](guides/personalizacao.md).

A V1.9 acrescenta `knowledge capture`, `knowledge validate` e `knowledge diff`, com referências tipadas aos documentos existentes e revalidação das fontes/motor antes do consumo. A captura cria cópia separada; efeito observado permanece proposto e não autoriza nada. O diário compartilhado bloqueia repetição de mutações com resultado desconhecido em probe, authz, negative e lotes mutantes do scan, preservando resultados parciais; resposta observada não confirma efeito. A dupla conferência de documentos não detecta alteração A→B→A entre leituras. O par 2xx exige provas adicionais; IDs gerados só pelo servidor podem ficar não testados. A exportação do estudo tem allowlist, schemas, segredos/vazamento e manifesto; chega como proposta sem aprovação transferida. As provas T2 e T4 da V1.9 passaram só no laboratório (Clínica Piloto e VAmPI, [relatório](reviews/relatorio-v1.9.md)), com detecção igual ou maior que a V1.8; o par com 200 do VAmPI e a atribuição em massa V4 seguem como lacunas, e o recibo de efeito não foi aplicado a nenhuma tarefa no laboratório. O estudo real e as rodadas cegas ficam para Claude Code depois do merge. A investigação dirigida preservou a lacuna histórica e manteve `legacy`.

A V1.9.1 (ADR 0081, proposto) corrige defeitos das rodadas cegas da V1.9: depois de editar `target.yml` com a pilha de pé, `preflight`, `probe`, `scan`, `authz`, `negative` e `run` falham antes do primeiro pedido com `STACK_STALE` (saída 4), o 403 `approval_changed` do proxy no meio da execução vira o mesmo erro, e `stack status` mostra `binding`; a cura é `stack down` e `stack up <produto>`, e o proxy segue falhando fechado com o hash completo. As skills mandam recriar a pilha e capturar o conhecimento (`knowledge capture <produto> --run <run_id>`, sem ativar); o `export-reuse` aceita `knowledge.captured.yml` na falta do `knowledge.yml`. Provada só no laboratório; ver [relatório](reviews/relatorio-v1.9.1.md).

A V1.9.3 (ADR 0082, proposto) faz o `authz` montar sozinho a leitura de dono em `GET` de item que o roteamento do perfil deixou sem prova: escolhe duas contas do mesmo papel não compartilhado, descobre o identificador pela coleção da conta, por alvos de sucesso ou pelo corpo redigido de uma criação (nunca adivinha), confirma a linha de base e repete com a outra conta, só `GET` e no máximo dois objetos por operação e par. Sem evidência, a operação vira lacuna com motivo e ação em `authz.json`, relatório e na aba Autorização do painel. Provada só no laboratório: BOLA da Clínica achada no vulnerável com perfil que roteia ao médico compartilhado, zero achado no seguro, e o equivalente no VAmPI; nenhuma rodada cega e nada contra produto real. [Relatório](reviews/relatorio-v1.9.3.md).

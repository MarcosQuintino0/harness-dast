# Pacote `application`

Caminho: `src/harness_dast/application/`. Decisão: [ADR 0004](../../decisoes/0004-portas-e-adaptadores-em-tres-camadas.md).

## Mapa por assunto

Inventário histórico após a organização V1.9.4: **88 módulos de produção**, sem contar 2 arquivos `__init__.py`; não inclui as adições da V1.11.
Contagens por grupo são disjuntas e somam o total. A raiz mantém 71 módulos; subpacotes preservam a camada.
Testes espelham `tests/unit/application/`; adaptadores concretos continuam em `adapters/`.

Na V1.11, `verification.py` coordena a classificação offline, `confirmation.py` conduz a reprodução protegida, `human_confirmation.py` registra a declaração humana e `report_presentation.py` monta a visão consultiva. Suas fronteiras ficam em `confirmation_ports.py`, `human_confirmation_ports.py` e `report_presentation_ports.py`. As decisões de nível e vínculo de semente pertencem ao domínio.

| Assunto ou subpacote | Módulos | Responsabilidade e exemplos | Onde entra código novo |
| --- | --- | --- | --- |
| `authz/` | 17 | Coordenação, envio, verificações e portas de autorização; entrada em service.py. | Nova regra ou coordenação desse assunto entra neste subpacote |
| Cadastro técnico e alcance | 11 | `account_session.py`, `dispatcher.py`, `inspect_report.py`, `inspect_spec.py`, `login_budget.py` e demais módulos do grupo | Manter no módulo específico; nova capacidade recebe arquivo próprio e teste espelhado |
| Perfil, aprovação, segredos e limpeza | 8 | `cleanup.py`, `init_from_letter.py`, `init_product.py`, `scope_approval.py`, `secret_admin.py` e demais módulos do grupo | Manter no módulo específico; nova capacidade recebe arquivo próprio e teste espelhado |
| Portas por capacidade e portas comuns | 15 | `cleanup_ports.py`, `common_ports.py`, `doctor_ports.py`, `init_ports.py`, `knowledge_ports.py` e demais módulos do grupo | Manter no módulo específico; nova capacidade recebe arquivo próprio e teste espelhado |
| Relatório, painel e medição | 7 | `command_journal.py`, `metrics.py`, `panel.py`, `panel_hooks.py`, `panel_index.py` e demais módulos do grupo | Manter no módulo específico; nova capacidade recebe arquivo próprio e teste espelhado |
| Execução e coordenação comum | 7 | `cors_check.py`, `lab_targets.py`, `preview.py`, `run.py`, `run_support.py` e demais módulos do grupo | Manter no módulo específico; nova capacidade recebe arquivo próprio e teste espelhado |
| Pilha, diagnóstico e espera | 8 | `doctor.py`, `doctor_checks.py`, `doctor_report.py`, `stack.py`, `stack_freshness.py` e demais módulos do grupo | Manter no módulo específico; nova capacidade recebe arquivo próprio e teste espelhado |
| Estratégia, conhecimento e mutações | 6 | `knowledge.py`, `knowledge_capture.py`, `knowledge_observations.py`, `mutation_guard.py`, `strategy.py` e demais módulos do grupo | Manter no módulo específico; nova capacidade recebe arquivo próprio e teste espelhado |
| Varredura e valores proibidos | 9 | `negative.py`, `negative_restore.py`, `negative_runner.py`, `negative_sender.py`, `scan.py` e demais módulos do grupo | Manter no módulo específico; nova capacidade recebe arquivo próprio e teste espelhado |

## Responsabilidade

Orquestrar um caso de uso por arquivo e declarar nos módulos `*_ports.py` as portas de que precisa. O caso de uso recebe as portas no construtor e usa o `domain` para decidir.

Portas previstas no desenho aprovado:

| Porta | Adaptador na V1 | Por que é porta |
| --- | --- | --- |
| `Scanner` | ZAP | Outros motores na V2; casos de uso testados com motor falso |
| `TargetClient` | `httpx` via proxy do ZAP | Ponto único onde o escopo é imposto; dublê nos testes |
| `SpecLoader` | Leitor de OpenAPI 3 | Swagger 2 e outras fontes depois |
| `SecretProvider` | `RoutingSecretProvider` (`env:` pelo ambiente, `keyring:` pelo cofre) | Cofre de segredos no CI depois |
| `CredentialStore` | `KeyringCredentialStore` (cofre do sistema operacional) | Segundo cofre real, se houver demanda |
| `SecretPrompt` | Prompt de terminal do `hdast secret` | Nenhuma |
| `ReportSink` | JSON e Markdown | SARIF, DefectDojo e Jira depois |
| `CleanupHook` | Script SQL do produto | Limpeza por API ou SQL conforme o produto |
| `RunStore` | Sistema de arquivos | Dublê em memória nos testes |
| `Clock` | Relógio do sistema | Janela de execução testável sem esperar |

Casos de uso do desenho: `inspect_spec`, `preflight`, `probe_reachability`, `run_scan`, `build_report`, `cleanup`, `run_pipeline`. Todos existem, com nomes de classe próprios (`InspectSpec`, `Preflight`, `Probe`, `Scan`, `Report`, `Cleanup`, `RunPipeline`); a lista real está nas tabelas de status abaixo.

## Pode importar

Somente `domain` (e a biblioteca padrão).

## Nunca deve

- Importar `adapters`, `cli` ou bibliotecas de terceiros de I/O.
- Importar `config` ou `observability` (o contrato do import-linter em `pyproject.toml` proíbe). Configuração e logger chegam aos casos de uso pelo construtor, via `cli`; como exatamente o logger chega ainda não está definido no desenho.
- Importar outro caso de uso. O que é comum desce para o `domain`.
- Decidir escopo, unicidade, severidade ou fingerprint: isso é do `domain`.
- Deixar passar exceção de terceiros. Os adaptadores traduzem na fronteira; o caso de uso só vê `HarnessError`.

## Convenções

- Porta é um `typing.Protocol`, declarada por quem a consome. Porta nova exige ADR.
- Docstring de porta descreve o contrato: o que garante, o que levanta, o que não faz.
- Piso de cobertura de ramos: 85% (veja [../testing.md](../testing.md)).

## Status

Implementado no M2 ([ADR 0015](../../decisoes/0015-portas-do-perfil-e-carregador-de-yaml.md)):

| Módulo | Conteúdo |
| --- | --- |
| `common_ports.py` e `init_ports.py` | `Clock`, `ProfileRepository` (`load`, `missing_files`) e `ProductScaffolder` (`scaffold`), mais os modelos `ReferencedFile` e `ScaffoldedProduct` usados nas assinaturas |
| `validate_profile.py` | `ValidateProfile`: carrega o perfil e devolve `ProfileReport` (resumo sem segredos, `runnable` e `issues`). Validade estrutural é erro (`ConfigError`); prontidão para executar é dado. Detecta os valores de exemplo do modelo (hosts `exemplo.com.br`, referência `SEC-0000`, segredos `MEU_PRODUTO_*`), arquivos referenciados ausentes, autorização vencida e janela fechada |
| `init_product.py` | `InitProduct`: cria a pasta do produto pela porta `ProductScaffolder` |

Implementado no M3 ([ADR 0018](../../decisoes/0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md)):

| Módulo | Conteúdo |
| --- | --- |
| `common_ports.py` (portas compartilhadas) | `Sleeper`, `EntropySource`, `ValueSourceFactory`, `SpecLoader`, `ProductDocuments`, `SecretProvider`, `SecretVault`, `TargetClient` (só aceita `ApprovedRequest`), `ZapControl`, `RunStore` |
| `inspect_spec.py`, `inspect_report.py` | `InspectSpec`: resumo e verificações cruzadas; modelos do resultado |
| `preflight.py`, `preflight_report.py`, `preflight_checks.py` | `Preflight`: verificações como dado (`scope` x `environment`); modelos e auxiliares |
| `probe.py` | `Probe`: orquestra leitura, plano, ZAP, sessão da conta, manifesto e resultado |
| `probe_runner.py`, `runner_settings.py` | O laço do `probe`: um passo nomeado por situação (pular, montar, simular, enviar, classificar) e as paradas antecipadas |
| `run_support.py` | `RunGate` (autorização, janela e prazo a cada requisição), `RateLimiter`, `AuditTrail` e `GuardedSender`, o único caminho de saída |
| `dispatcher.py` | `OperationDispatcher`: envia e repete conforme `domain.retry.next_action` |
| `account_session.py` | `AccountSession` e `TokenCache`: segredos, login (ou chave fixa, ou token do cache do processo), token CSRF; registra tudo no `SecretVault` |
| `login_budget.py` | `LoginBudget`: janela deslizante de logins por minuto (`auth.login_limit`); `is_login_request` |
| `session_pool.py` | `SessionPool`: abre cada conta usada uma vez e não repete uma abertura que falhou |
| `preview.py` | Prévia do `--dry-run`: nomes de campos e geradores, nunca valores |

Implementado no M4 ([ADR 0022](../../decisoes/0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md), [ADR 0023](../../decisoes/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md)):

| Módulo | Conteúdo |
| --- | --- |
| `scan_ports.py` | Portas do `scan`/`report`/`run`: `ScanControl` (API de varredura do ZAP), `RunArtifacts` (arquivos da execução), `ReportSink`, `ProxyAudit` (auditoria do proxy), `RunningScans` (andamento, para `hdast stop`) e `RunSummarySink` (`run.json`). Especializadas pelos consumidores scan/report/run; portas compartilhadas ficam em `common_ports.py` |
| `scan.py`, `scan_runner.py`, `scan_collect.py`, `scan_health.py`, `scan_tokens.py` | `Scan`: plano, política e limites no ZAP, laço de uma varredura por requisição aprendida, coleta de alertas e evidência redigidos, guarda de saúde do alvo, entrega do token ao Replacer |
| `report.py` | `Report`: achados, `findings.json` e `report.md`, comparação e código `1` |

Implementado no M5 ([ADR 0020](../../decisoes/0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md), [ADR 0024](../../decisoes/0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md)):

| Módulo | Conteúdo |
| --- | --- |
| `cleanup.py` | `Cleanup`: portão de SQL, transação, contagens, teto de linhas e confirmação humana |
| `stack.py`, `stack_models.py`, `lab_targets.py` | `StackManager`: `up` (inclui `--oracle`), `status`, `down` e `stop` (trava de emergência, com o que estava rodando) |
| `run.py` | `RunPipeline`: `preflight`, `probe`, `scan` e `report` num processo, parada no primeiro estágio que falha, `run.json`, interrupção por Ctrl+C ou `hdast stop` (saída 130) |
| `stage_errors.py` | Tradução do estado final de cada etapa no erro e código de saída, usada pelos comandos soltos e pelo `run` |
| `run_support.py` (ampliado) | `RunGate` também consulta a porta `KillSwitch` (`KillSwitchEngaged`) |

Implementado na V1.1 e na V1.2 (esta lista não é exaustiva; o diretório é a fonte):

| Módulo | Conteúdo |
| --- | --- |
| `authz/service.py`, `authz/ports.py`, `authz/runner.py` | `Authz`: o teste de autorização entre contas ([ADR 0027](../../decisoes/0027-teste-de-autorizacao-entre-contas.md)) |
| `doctor.py`, `doctor_checks.py`, `doctor_report.py` | `Doctor`: confere ambiente e perfil sem tocar o alvo ([ADR 0028](../../decisoes/0028-facilitar-o-uso-doctor-setup-path-allow-local-init-e-prazo-da-pilha.md)) |
| `secret_admin.py`, `secret_refs.py`, `secret_router.py` | `hdast secret` e o roteamento de `env:` e `keyring:` ([ADR 0030](../../decisoes/0030-cofre-de-credenciais-do-sistema-keyring.md)) |
| `metrics.py` | Montagem do `metrics.json` ([ADR 0031](../../decisoes/0031-medicao-da-execucao-metrics-json-e-tempo-por-regra-do-zap.md)) |
| `panel.py`, `panel_hooks.py`, `panel_index.py`, `panel_index_ports.py`, `panel_live.py` | Painel da execução, índices e página ao vivo ([ADR 0032](../../decisoes/0032-painel-da-execucao.md) e [0034](../../decisoes/0034-indices-do-painel-e-pagina-ao-vivo.md), Propostos) |
| `command_journal.py` | Diário de comandos por produto ([ADR 0033](../../decisoes/0033-diario-de-comandos.md), Proposto) |

## Portas por consumidor

Na V1.11 em andamento, `verification.py` coordena a classificação sem tráfego; `confirmation.py` coordena leitura dos artefatos, seleção, controles de envio e persistência aditiva; `human_confirmation.py` e `human_confirmation_ports.py` tratam a declaração interativa separada. A apresentação reúne os registros sem alterar o achado. Veja [verificação](../../referencia/verification.md).

Na organização V1.9.4 foram preservadas 47 declarações (Protocol e modelos de assinatura), distribuídas em 12 módulos; a V1.11 acrescenta portas específicas de confirmação.
As portas existentes de scan, authz, negative e panel_index continuam especializadas.

| Módulo | Declarações |
| --- | --- |
| `probe_ports.py` | `KnowledgeRecipeReader` |
| `knowledge_ports.py` | `KnowledgeRunStore`, `KnowledgeStore` |
| `strategy_ports.py` | `StrategyCaptureStore` |
| `wait_ports.py` | `WaitReader` |
| `init_ports.py` | `ScaffoldedProduct`, `ProductScaffolder`, `LetterReader` |
| `secret_ports.py` | `CredentialStore`, `SecretPrompt` |
| `scope_approval_ports.py` | `ApprovalPrompt` |
| `stack_ports.py` | `ProxyPolicyStore`, `StackBindingSource`, `ComposeRunner`, `StackLockFile`, `ProcessProbe`, `RandomSource`, `ZapScanStopper` |
| `cleanup_ports.py` | `CleanupConnection`, `CleanupSession`, `CleanupExecutor`, `CleanupScripts`, `CleanupRuns`, `TokenSource`, `OperatorPrompt` |
| `doctor_ports.py` | `HostInspector` |
| `panel_ports.py` | `PanelFiles` |
| `common_ports.py` | `MutationJournal`, `StrategyStore`, `StrategyDependencyStore`, `ReferencedFile`, `Clock`, `ProfileRepository`, `Sleeper`, `KillSwitch`, `EntropySource`, `ValueSourceFactory`, `SpecLoader`, `ProductDocuments`, `SecretProvider`, `ApprovalStore`, `SecretVault`, `TargetClient`, `ZapControl`, `RunStore`, `StackStateStore`, `CommandJournalStore` |

Uma porta nova exclusiva entra na capacidade consumidora; uma usada por capacidades diferentes entra em `common_ports.py`. Porta nova exige ADR.

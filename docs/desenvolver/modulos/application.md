# Pacote `application`

Caminho: `src/harness_dast/application/`. Decisão: [ADR 0004](../../decisoes/0004-portas-e-adaptadores-em-tres-camadas.md).

## Mapa por assunto

O pacote tem **89 arquivos Python na raiz** (88 módulos e `__init__.py`). O mapa soma **105 módulos de produção** (88 na raiz e 17 em subpacotes), com um grupo por módulo. A contagem exclui os 2 arquivos `__init__.py`. Os testes espelham `tests/unit/application/`.

Os grupos congelados recebem apenas correções de defeitos. O diário de execução e a proteção de mutações pendentes seguem no núcleo. [ADR 0110](../../decisoes/0110-reestruturacao-documentacao-licenca-e-extras.md)

| Responsabilidade | Raiz | Subpacotes | Módulos principais | Onde entra código novo |
| --- | ---: | ---: | --- | --- |
| Carta, perfil, aprovação e segredos | 12 | 0 | `init_from_letter.py`, `validate_profile.py`, `scope_approval.py`, `setup_product.py`, `secret_admin.py` | Coloque a coordenação do cadastro em `init_from_letter.py`, os passos humanos em `setup_product.py` e as portas junto de cada consumidor. |
| Contrato da API, sessão e alcance | 14 | 0 | `inspect_spec.py`, `preflight.py`, `probe.py`, `probe_runner.py`, `account_session.py` | Coloque inspeção em `inspect_spec.py`, prontidão em `preflight.py`, coordenação do alcance em `probe.py` e sessão em `account_session.py`. |
| Varredura | 6 | 0 | `scan.py`, `scan_runner.py`, `scan_collect.py`, `scan_ports.py` | Coloque coordenação em `scan.py`, andamento em `scan_runner.py`, coleta em `scan_collect.py` e portas de varredura e relatório em `scan_ports.py`. |
| Checagens complementares | 3 | 0 | `cors_check.py`, `extra_checks.py`, `oast_ssrf.py` | Coloque a coordenação no módulo que executa a checagem. As decisões puras pertencem a `domain`. |
| Autorização entre contas | 0 | 17 | `authz/service.py`, `authz/runner.py`, `authz/ports.py` | Coloque a coordenação em `authz/service.py`, a execução em `authz/runner.py` e os contratos consumidos em `authz/ports.py`. |
| Valores proibidos | 5 | 0 | `negative.py`, `negative_runner.py`, `negative_restore.py`, `negative_ports.py` | Coloque coordenação em `negative.py`, iteração em `negative_runner.py` e restauração em `negative_restore.py`. |
| Verificação | 5 | 0 | `verification.py`, `confirmation.py`, `human_confirmation.py` | Coloque coordenação offline em `verification.py`, verificação automática em `confirmation.py` e persistência do registro humano em `human_confirmation.py`. |
| Reteste | 2 | 0 | `retest.py`, `retest_ports.py` | Coloque o encadeamento em `retest.py` e os contratos de artefatos em `retest_ports.py`. |
| Relatório | 3 | 0 | `report.py`, `report_presentation.py`, `report_presentation_ports.py` | Coloque a coordenação em `report.py` e a leitura de dados consultivos em `report_presentation.py` e suas portas. |
| Limpeza | 2 | 0 | `cleanup.py`, `cleanup_ports.py` | Coloque a coordenação da transação e da confirmação em `cleanup.py` e as fronteiras em `cleanup_ports.py`. |
| Diário, execução e portas comuns | 8 | 0 | `run.py`, `run_support.py`, `command_journal.py`, `common_ports.py` | Coloque o encadeamento em `run.py`, as peças comuns em `run_support.py` e as portas compartilhadas em `common_ports.py`. |
| Pilha e diagnóstico | 13 | 0 | `stack.py`, `stack_images.py`, `doctor.py`, `doctor_stack.py` | Coloque o ciclo de vida em `stack.py`, as imagens em `stack_images.py` e o diagnóstico em `doctor.py` e seus auxiliares. |
| Mutações pendentes | 2 | 0 | `mutation_guard.py`, `mutation_release.py` | Coloque a coordenação da parada em `mutation_guard.py` e a liberação humana em `mutation_release.py`. |
| Painel **(congelado)** | 6 | 0 | `panel.py`, `panel_index.py`, `panel_live.py` | Corrija a geração, os índices e a atualização ao vivo nos módulos `panel*.py`. A ligação dos dados ao painel fica em `panel_hooks.py`. |
| Estratégia e `plan` **(congelado)** | 3 | 0 | `strategy.py`, `strategy_capture.py`, `strategy_ports.py` | Corrija a coordenação da prévia em `strategy.py`, a captura em `strategy_capture.py` e suas portas em `strategy_ports.py`. |
| Conhecimento reutilizável **(congelado)** | 4 | 0 | `knowledge.py`, `knowledge_capture.py`, `knowledge_observations.py` | Corrija a validação, a captura ou a extração de observações nos respectivos módulos `knowledge*.py`. |
| **Total** | **88** | **17** | | |

<details>
<summary>Inventário por grupo</summary>

- **Carta, perfil, aprovação e segredos** inclui `init_from_letter.py`, `init_ports.py`, `init_product.py`, `scope_approval.py`, `scope_approval_ports.py`, `secret_admin.py`, `secret_ports.py`, `secret_refs.py`, `secret_router.py`, `setup_ports.py`, `setup_product.py`, `validate_profile.py`.
- **Contrato da API, sessão e alcance** inclui `account_session.py`, `dispatcher.py`, `inspect_report.py`, `inspect_spec.py`, `login_budget.py`, `preflight.py`, `preflight_checks.py`, `preflight_report.py`, `preview.py`, `probe.py`, `probe_ports.py`, `probe_runner.py`, `runner_settings.py`, `session_pool.py`.
- **Varredura** inclui `scan.py`, `scan_collect.py`, `scan_health.py`, `scan_ports.py`, `scan_runner.py`, `scan_tokens.py`.
- **Checagens complementares** inclui `cors_check.py`, `extra_checks.py`, `oast_ssrf.py`.
- **Autorização entre contas** inclui `authz/*.py`.
- **Valores proibidos** inclui `negative.py`, `negative_ports.py`, `negative_restore.py`, `negative_runner.py`, `negative_sender.py`.
- **Verificação** inclui `confirmation.py`, `confirmation_ports.py`, `human_confirmation.py`, `human_confirmation_ports.py`, `verification.py`.
- **Reteste** inclui `retest.py`, `retest_ports.py`.
- **Relatório** inclui `report.py`, `report_presentation.py`, `report_presentation_ports.py`.
- **Limpeza** inclui `cleanup.py`, `cleanup_ports.py`.
- **Diário, execução e portas comuns** inclui `command_journal.py`, `common_ports.py`, `metrics.py`, `run.py`, `run_support.py`, `stage_errors.py`, `wait.py`, `wait_ports.py`.
- **Pilha e diagnóstico** inclui `doctor.py`, `doctor_checks.py`, `doctor_ports.py`, `doctor_report.py`, `doctor_stack.py`, `lab_accounts.py`, `lab_targets.py`, `stack.py`, `stack_freshness.py`, `stack_images.py`, `stack_lock.py`, `stack_models.py`, `stack_ports.py`.
- **Mutações pendentes** inclui `mutation_guard.py`, `mutation_release.py`.
- **Painel** (congelado) inclui `panel.py`, `panel_hooks.py`, `panel_index.py`, `panel_index_ports.py`, `panel_live.py`, `panel_ports.py`.
- **Estratégia e `plan`** (congelado) inclui `strategy.py`, `strategy_capture.py`, `strategy_ports.py`.
- **Conhecimento reutilizável** (congelado) inclui `knowledge.py`, `knowledge_capture.py`, `knowledge_observations.py`, `knowledge_ports.py`.

Os curingas de subpacote cobrem os módulos Python da pasta indicada, excluindo `__init__.py`.

</details>

**Como conferir este mapa** · `rg --files src/harness_dast/application -g '*.py' -g '!__init__.py'`

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

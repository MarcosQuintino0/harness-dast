# Pacote `domain`

Caminho: `src/harness_dast/domain/`. Decisão: [ADR 0004](../../decisoes/0004-portas-e-adaptadores-em-tres-camadas.md).

## Mapa por assunto

O pacote tem **155 arquivos Python na raiz** (154 módulos e `__init__.py`). O mapa soma **239 módulos de produção** (154 na raiz e 85 em subpacotes), com um grupo por módulo. A contagem exclui os 4 arquivos `__init__.py`. Os testes espelham `tests/unit/domain/`.

Os grupos congelados recebem apenas correções de defeitos. O diário de execução e a proteção de mutações pendentes seguem no núcleo. [ADR 0110](../../decisoes/0110-reestruturacao-documentacao-licenca-e-extras.md)

| Responsabilidade | Raiz | Subpacotes | Módulos principais | Onde entra código novo |
| --- | ---: | ---: | --- | --- |
| Carta, perfil e escopo | 37 | 0 | `letter.py`, `letter_review.py`, `profile.py`, `scope.py`, `scope_approval.py` | Estenda os campos da carta em `letter*.py`, a validação em `profile.py` e as decisões da cerca em `scope.py` e seus auxiliares. |
| Contrato da API e alcance | 31 | 0 | `api_model.py`, `api_schema.py`, `datagen.py`, `request_builder.py`, `probe_plan.py`, `probe_result.py` | Modele o contrato em `api_model.py` e `api_schema.py`, regras de dados em `datagen.py` e elegibilidade do `probe` em `probe_plan.py`. |
| Varredura e achados | 19 | 0 | `scan_plan.py`, `scan_policy.py`, `finding.py`, `finding_build.py`, `redaction.py` | Estenda seleção e política em `scan_plan.py` e `scan_policy.py`, identidade em `finding.py` e proteção de evidência em `redaction.py`. |
| Checagens complementares | 10 | 0 | `extra_checks_config.py`, `extra_check_result.py`, `cors.py`, `experimental_rules.py`, `inventory_checks.py` | Modele a configuração em `extra_checks_config.py` e mantenha as regras puras no módulo da checagem. |
| Autorização entre contas | 1 | 36 | `authz/config.py`, `authz/plan.py`, `authz/compare.py`, `probe_exchange.py` | Coloque regras de acesso e comparação em `authz/` e o contrato das trocas registradas pelo `probe` em `probe_exchange.py`. |
| Valores proibidos | 8 | 0 | `negative_config.py`, `negative_plan.py`, `negative_values.py`, `negative_verdict.py` | Coloque seleção de casos em `negative_plan.py`, geração em `negative_values.py` e classificação em `negative_verdict.py`. |
| Verificação | 5 | 0 | `verification.py`, `confirmation.py`, `confirmation_observations.py`, `scan_binding.py`, `human_confirmation.py` | Coloque classificação offline em `verification.py`, avaliação de observações em `confirmation_observations.py` e o registro humano em `human_confirmation.py`. |
| Reteste | 1 | 0 | `retest.py` | Mantenha a seleção de achados e as regras de resultado em `retest.py`. |
| Relatório e triagem | 6 | 18 | `report/build.py`, `report/presentation.py`, `finding_diff.py`, `triage.py` | Coloque composição e formatos em `report/`, comparação em `finding_diff.py` e anotações em `triage.py`. |
| Limpeza | 6 | 0 | `cleanup_plan.py`, `cleanup_gate.py`, `cleanup_sql.py` | Coloque as regras do plano, do portão e da validação SQL nos respectivos módulos `cleanup_*.py`. |
| Diário, execução e pilha | 10 | 0 | `audit.py`, `command_journal.py`, `run.py`, `run_summary.py`, `stack_lock.py` | Modele registros em `audit.py` e `command_journal.py`, identidade e carga em `run.py` e vínculo ou exclusividade em `stack_binding.py` ou `stack_lock.py`. |
| Mutações pendentes | 2 | 0 | `knowledge_mutation.py`, `mutation_snapshot.py` | Coloque a identidade da mutação em `knowledge_mutation.py` e a projeção do estado anterior em `mutation_snapshot.py`. |
| Erros e leitura comum | 2 | 0 | `errors.py`, `strict_json.py` | Acrescente erros compartilhados à hierarquia `HarnessError` e regras comuns de decodificação a `strict_json.py`. |
| Painel **(congelado)** | 5 | 31 | `panel/build.py`, `panel/index_build.py`, `manual_repro.py`, `agent_metrics.py` | Corrija a composição em `panel/` e os contratos auxiliares no módulo correspondente. |
| Estratégia e `plan` **(congelado)** | 7 | 0 | `strategy.py`, `strategy_capture.py`, `strategy_plan.py`, `strategy_preview.py` | Corrija modelos e validação em `strategy*.py` e os dados da prévia em `strategy_preview.py`. |
| Conhecimento reutilizável **(congelado)** | 4 | 0 | `knowledge.py`, `knowledge_checks.py`, `knowledge_evidence.py`, `knowledge_receipts.py` | Corrija modelos, conferências e recibos nos respectivos módulos `knowledge*.py`. |
| **Total** | **154** | **85** | | |

<details>
<summary>Inventário por grupo</summary>

- **Carta, perfil e escopo** inclui `auth.py`, `host.py`, `letter.py`, `letter_attack.py`, `letter_collect.py`, `letter_defaults.py`, `letter_negative.py`, `letter_outcomes.py`, `letter_review.py`, `letter_sections.py`, `letter_shared_roles.py`, `letter_technology.py`, `letter_upload.py`, `letter_warnings.py`, `letter_writes.py`, `letter_yaml.py`, `overrides.py`, `pathpattern.py`, `placeholders.py`, `profile.py`, `profile_errors.py`, `proxy_deadline.py`, `routing_headers.py`, `scope.py`, `scope_approval.py`, `scope_approval_summary.py`, `scope_fingerprint.py`, `scope_labels.py`, `scope_reason.py`, `secret_ref.py`, `setup_notes.py`, `technology.py`, `urlnorm.py`, `wide_guard.py`, `widepath.py`, `window.py`, `zap_scope.py`.
- **Contrato da API e alcance** inclui `account_routing.py`, `api_model.py`, `api_schema.py`, `api_summary.py`, `datagen.py`, `datagen_catalog.py`, `excerpt.py`, `flow.py`, `http_messages.py`, `implicit_values.py`, `login_hint.py`, `multipart_encoding.py`, `multipart_schema.py`, `outcome.py`, `pattern_subset.py`, `probe_config.py`, `probe_conflict.py`, `probe_plan.py`, `probe_policy.py`, `probe_result.py`, `request_builder.py`, `request_encoding.py`, `retry.py`, `retry_after.py`, `schema_check.py`, `spec_examples.py`, `spec_hints.py`, `synthetic_files.py`, `unique_values.py`, `versioned.py`, `zap_messages.py`.
- **Varredura e achados** inclui `curl_repro.py`, `error_signal_catalog.py`, `finding.py`, `finding_build.py`, `finding_group.py`, `finding_taxonomy.py`, `internal_error_signals.py`, `redaction.py`, `scan_config.py`, `scan_plan.py`, `scan_policy.py`, `scan_result.py`, `scan_rule_coverage.py`, `scan_tokens.py`, `signal_findings.py`, `signal_operations.py`, `signal_result.py`, `traffic.py`, `zap_alert.py`.
- **Checagens complementares** inclui `cors.py`, `experimental_rules.py`, `extra_check_result.py`, `extra_checks_config.py`, `inventory_checks.py`, `oast_bridge.py`, `oast_ssrf.py`, `oast_verification.py`, `rate_attempts.py`, `rate_page.py`.
- **Autorização entre contas** inclui `authz/*.py`, `probe_exchange.py`.
- **Valores proibidos** inclui `negative_config.py`, `negative_findings.py`, `negative_plan.py`, `negative_request.py`, `negative_result.py`, `negative_tally.py`, `negative_values.py`, `negative_verdict.py`.
- **Verificação** inclui `confirmation.py`, `confirmation_observations.py`, `human_confirmation.py`, `scan_binding.py`, `verification.py`.
- **Reteste** inclui `retest.py`.
- **Relatório e triagem** inclui `report/*.py`, `finding_diff.py`, `fix_hints.py`, `html_safe.py`, `known_patterns.py`, `markdown_safe.py`, `triage.py`.
- **Limpeza** inclui `cleanup_binds.py`, `cleanup_confirmation.py`, `cleanup_gate.py`, `cleanup_plan.py`, `cleanup_sql.py`, `cleanup_where.py`.
- **Diário, execução e pilha** inclui `audit.py`, `command_journal.py`, `rule_stats.py`, `run.py`, `run_metrics.py`, `run_ref.py`, `run_summary.py`, `stack_binding.py`, `stack_lock.py`, `wait.py`.
- **Mutações pendentes** inclui `knowledge_mutation.py`, `mutation_snapshot.py`.
- **Erros e leitura comum** inclui `errors.py`, `strict_json.py`.
- **Painel** (congelado) inclui `panel/*.py`, `agent_metrics.py`, `command_translation.py`, `finding_confidence.py`, `finding_explain.py`, `manual_repro.py`.
- **Estratégia e `plan`** (congelado) inclui `envelope.py`, `strategy.py`, `strategy_basis.py`, `strategy_capture.py`, `strategy_control.py`, `strategy_plan.py`, `strategy_preview.py`.
- **Conhecimento reutilizável** (congelado) inclui `knowledge.py`, `knowledge_checks.py`, `knowledge_evidence.py`, `knowledge_receipts.py`.

Os curingas de subpacote cobrem os módulos Python da pasta indicada, excluindo `__init__.py`.

</details>

**Como conferir este mapa** · `rg --files src/harness_dast/domain -g '*.py' -g '!__init__.py'`

## Responsabilidade

Regras e modelos puros do negócio: o que é escopo, perfil, achado, regra de dados, execução e erro. Toda decisão sobre escopo, unicidade, severidade ou fingerprint mora aqui e em nenhum outro lugar.

## Módulos

Todos puros: sem I/O, sem relógio e sem aleatoriedade (o instante e o sufixo do `RunId` entram por argumento). Duas exceções literais, registradas no [ADR 0012](../../decisoes/0012-dependencias-tzdata-e-pyyaml.md): `window.py` usa `zoneinfo`, que lê o banco de fusos do disco, e `profile_errors.py` importa `pydantic_core`, dependência do pydantic.

### Existem

| Módulo | Contrato em uma linha | Marco |
| --- | --- | --- |
| `errors.py` | Hierarquia `HarnessError` (`ConfigError`, `ScopeViolation`, `PreflightError`, `ExternalToolError`, `TargetError`, `CleanupError`) com `code`, `message`, `hint` e o código de saída de cada tipo | M1 |
| `host.py` | Converte um host para a forma canônica (minúsculas, punycode, IP sem ambiguidade) e recusa IP em formato decimal, hex ou octal, IPv6 que embute IPv4, zona IPv6 e metadados da nuvem; informa se o host é local (`is_local`) | M2 |
| `urlnorm.py` | Normaliza método e URL de saída para a forma sobre a qual o escopo decide; qualquer ambiguidade (credenciais, `..`, dupla codificação, `;`, ponto ou espaço finais) é `ScopeViolation`; resolve `Location` de redirecionamento | M2 |
| `pathpattern.py` | Valida, casa e compara padrões de caminho com `*` (um segmento) e `**` (zero ou mais); `covers` diz, de forma conservadora, se um padrão cobre outro | M2 |
| `scope.py` | `ScopeRule`, `Scope`, `OutboundRequest` e `ScopeGuard`: recusa tudo que não casa host, esquema, porta, caminho e método de uma regra, ou que casa `deny_paths` (a negação vence) | M2 |
| `window.py` | `ExecutionWindow` (gramática compacta `seg-sex 20:00-06:00 America/Sao_Paulo`, fuso IANA, início igual ao fim recusado) e `Authorization` (`valid_until` inclusivo em UTC); recebem o instante por argumento e recusam instante sem fuso | M2 |
| `overrides.py` | `ScopeOverride`, `LimitsOverride`, `narrow_scope` e `narrow_limits`: aplicam o que o usuário pediu por flag e devolvem algo igual ou menor, ou `ConfigError`; nunca ampliam e não alteram os argumentos | M2 |
| `run.py` | `RunId` (ordenável, seguro como nome de pasta, instante e sufixo injetados) e `RunLimits` com os tetos absolutos de carga | M2 |
| `secret_ref.py` | `ProfileModel` (base congelada, sem campo extra, sem eco do valor recebido) e `SecretRef` (`env:NOME` ou `keyring:NOME`; segredo literal não passa) | M2 |
| `auth.py` | `PasswordLoginAuth` (`login_password`), `ApiKeyAuth` (`api_key`), contas com apelido único e `AuthConfig` | M2 |
| `profile.py` | `ProductProfile`, `Environment`, `ProfileScope`, `CleanupConfig`; `from_data` valida o perfil inteiro e confere que a `base_url` e o login estão no escopo; `ensure_runnable` confere autorização e janela | M2 |
| `profile_errors.py` | Converte o erro de validação do pydantic em `ConfigError` em português, por caminho de campo, sem repetir o valor recebido | M2 |
| `api_schema.py` | Subconjunto de JSON Schema (`Schema`) independente do OpenAPI, com `flatten_schema` (resolve `allOf`/`oneOf`/`anyOf`), `find_property_path` e o alias `JsonValue` | M3 |
| `api_model.py` | `ApiSpec`, `Operation`, `Parameter`, `RequestBody`, `SuccessResponse`: a API normalizada; sintetiza `operation_id` ausente de forma determinística; `safe_identifier` saneia texto do documento para mensagens | M3 |
| `api_summary.py` | `summarize`: resumo compacto da API para o agente (entradas obrigatórias, ids produzidos e consumidos) com orçamento rígido em caracteres | M3 |
| `pattern_subset.py` | Subconjunto seguro de regex (sem grupos nem alternância): análise, casamento polinomial e síntese. Nunca executa o `pattern` do documento com `re` | M3 |
| `schema_check.py` | `violations`: o que num valor contraria o esquema (tipo, enum, limites, tamanho, formato, `pattern` suportado), sem repetir o valor | M3 |
| `unique_values.py` | Esquema de valores únicos por execução: etiqueta do `RunId` + contador, em texto e em dígitos ([ADR 0016](../../decisoes/0016-leitor-de-openapi-proprio-e-esquema-de-unicidade.md)) | M3 |
| `datagen_catalog.py` | Catálogo fechado de 18 geradores (nome, argumentos, se aceita `unique`) e validação estrita de argumentos | M3 |
| `datagen.py` | `DataRules` (`data-rules.yml`): validação, precedência da regra mais específica, rejeição de regras ambíguas, conferência contra o OpenAPI | M3 |
| `implicit_values.py` | Escolha do gerador implícito de um campo sem regra; `FieldNotGeneratable` quando o harness não sabe gerar sozinho | M3 |
| `request_builder.py` | `RequestBuilder`: monta UMA requisição válida por operação (`BuiltRequest`) com valores de uma `ValueSource` injetada e confere tudo contra o esquema | M3 |
| `flow.py` | `FlowSpec` (`flows.yml`): validação (vários níveis até `MAX_FLOW_DEPTH`, sem ciclo), ordenação topológica, `extract_value` e `resolve_bindings` | M3 |
| `versioned.py` | Validação comum de `schema_version: 1` e tradução de erros para `ConfigError` em arquivos como `data-rules.yml` e `flows.yml` | M3 |

Referências: [data-rules.yml](../../referencia/data-rules-yml.md) e [flows.yml](../../referencia/flows-yml.md).

Módulos do `probe` (M3, [ADR 0018](../../decisoes/0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md)):

| Módulo | Conteúdo |
| --- | --- |
| `http_messages.py` | `HttpRequest`, `HttpResponse` e a invariante de envio: `ApprovedRequest` só nasce em `approve(guard, request)` |
| `request_encoding.py` | Codificação da requisição montada, do login e do GET simples em `HttpRequest` (JSON, formulário, texto) |
| `outcome.py` | `Outcome` (18 classes), `classify_response`, `looks_like_csrf_rejection`, `parse_json_body` |
| `retry.py` | `next_action` e `RetryState`: 401 de token vencido (novo login, 1), 403 de CSRF (novo token, 1), 429 (espera, 3) |
| `account_routing.py` | `AccountRule` e `AccountRouting`: `auth.default_account` e `auth.account_map` (conta por operação) |
| `probe_policy.py` | Constantes (tempo limite, tetos de tentativas, limiar de alvo sem resposta), `parse_retry_after` e `TokenBucket` |
| `probe_plan.py` | `plan_probe`: ordem, pulos por escopo, negação e `DELETE`; `looks_destructive` |
| `probe_config.py` | Bloco `probe` do perfil: `JsonFieldRule`, `SuccessCriteria`, `ErrorCodes`, `ProbeConfig` |
| `probe_result.py` | `OperationResult`, `ProbeResult`, `summarize_results` (alcançabilidade), `RunManifest` |
| `audit.py` | `AuditEntry` e as linhas de decisão e de resultado |
| `excerpt.py` | `sanitize_excerpt`: trecho curto e neutralizado do corpo de uma falha |
| `zap_scope.py` | Expressões do contexto do ZAP e o prefixo `hdast-` das regras do Replacer |

`scope.py` ganhou `ScopeGuard.evaluate` (decisão como dado) e `auth.py` o bloco `CsrfConfig`.

A referência campo a campo do perfil está em [../../referencia/target-yml.md](../../referencia/target-yml.md).

Também existem, desde o M4 e o M5: `finding.py` (`Finding`, `compute_fingerprint`), `run.py` e `probe_result.py` (`RunManifest`), `routing_headers.py` (cabeçalhos que só o cliente HTTP define) e `scan_config.py` (`effective_fail_on`). A distribuição por marco segue o [roadmap](../../roadmap.md).

A tabela acima cobre o M1 ao M5. As versões 1.1 e 1.2 acrescentaram famílias de módulos, todas puras e testadas; o contrato de cada uma está no docstring do módulo e no ADR citado. Esta lista não é exaustiva (o diretório é a fonte):

| Família | Módulos | ADR |
| --- | --- | --- |
| Cerca com motivo granular e modo amplo | `scope_reason.py`, `scope_labels.py`, `widepath.py`, `wide_guard.py`, `traffic.py` | [0026](../../decisoes/0026-cerca-com-motivo-granular-e-modo-amplo-de-caminho.md) |
| Teste de autorização entre contas | `authz/config.py`, `authz/plan.py`, `authz/compare.py`, `authz/result.py`, `authz/findings.py`, `authz/sensitive.py`, `probe_exchange.py` | [0027](../../decisoes/0027-teste-de-autorizacao-entre-contas.md) |
| Relatório agrupado e `report.html` | `finding_group.py`, `known_patterns.py`, `report/`, `html_safe.py`, `markdown_safe.py`, `fix_hints.py` | [0029](../../decisoes/0029-relatorio-agrupado-pagina-html-e-skill-de-um-pedido-so.md) |
| Medição da execução | `run_metrics.py`, `rule_stats.py`, `run_summary.py` | [0031](../../decisoes/0031-medicao-da-execucao-metrics-json-e-tempo-por-regra-do-zap.md) |
| Painel, diário de comandos e explicação de falha | `panel/`, `command_journal.py`, `command_translation.py`, `finding_explain.py`, `finding_confidence.py`, `manual_repro.py`, `agent_metrics.py` | [0032](../../decisoes/0032-painel-da-execucao.md), [0033](../../decisoes/0033-diario-de-comandos.md), [0034](../../decisoes/0034-indices-do-painel-e-pagina-ao-vivo.md) (os três Propostos) |

## Pode importar

Somente a biblioteca padrão e pydantic.

## Nunca deve

- Fazer I/O: rede, arquivos, banco, variáveis de ambiente.
- Importar `httpx`, ZAP, `application`, `adapters`, `cli`, `config` ou `observability`.
- Ler o relógio ou gerar aleatoriedade diretamente. Relógio e aleatoriedade entram por parâmetro.
- Ter variável de módulo mutável ou singleton.
- Expor modelo mutável: os modelos são congelados (`frozen`).

## Convenções

- Docstring estilo Google em módulo e em todo item público, descrevendo o que garante, o que levanta e o que não faz.
- Piso de cobertura de ramos: 95% (veja [../testing.md](../testing.md)).

## Status

Os módulos listados estão implementados e testados e são usados pelos comandos da CLI. O número de cobertura (100% na revisão de 2026-11-13) envelhece: a fonte é o relatório do CI. Módulo planejado que ainda não existe não aparece nesta página. A fonte do estado é a [tabela de status](../../roadmap.md#tabela-de-status).

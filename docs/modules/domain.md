# Pacote `domain`

Caminho: `src/harness_dast/domain/`. Decisão: [ADR 0004](../adr/0004-portas-e-adaptadores-em-tres-camadas.md).

## Responsabilidade

Regras e modelos puros do negócio: o que é escopo, perfil, achado, regra de dados, execução e erro. Toda decisão sobre escopo, unicidade, severidade ou fingerprint mora aqui e em nenhum outro lugar.

## Módulos

Todos puros: sem I/O, sem relógio e sem aleatoriedade (o instante e o sufixo do `RunId` entram por argumento). Duas exceções literais, registradas no [ADR 0012](../adr/0012-dependencias-tzdata-e-pyyaml.md): `window.py` usa `zoneinfo`, que lê o banco de fusos do disco, e `profile_errors.py` importa `pydantic_core`, dependência do pydantic.

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
| `unique_values.py` | Esquema de valores únicos por execução: etiqueta do `RunId` + contador, em texto e em dígitos ([ADR 0016](../adr/0016-leitor-de-openapi-proprio-e-esquema-de-unicidade.md)) | M3 |
| `datagen_catalog.py` | Catálogo fechado de 18 geradores (nome, argumentos, se aceita `unique`) e validação estrita de argumentos | M3 |
| `datagen.py` | `DataRules` (`data-rules.yml`): validação, precedência da regra mais específica, rejeição de regras ambíguas, conferência contra o OpenAPI | M3 |
| `implicit_values.py` | Escolha do gerador implícito de um campo sem regra; `FieldNotGeneratable` quando o harness não sabe gerar sozinho | M3 |
| `request_builder.py` | `RequestBuilder`: monta UMA requisição válida por operação (`BuiltRequest`) com valores de uma `ValueSource` injetada e confere tudo contra o esquema | M3 |
| `flow.py` | `FlowSpec` (`flows.yml`): validação (vários níveis até `MAX_FLOW_DEPTH`, sem ciclo), ordenação topológica, `extract_value` e `resolve_bindings` | M3 |
| `versioned.py` | Validação comum de `schema_version: 1` e tradução de erros para `ConfigError` em arquivos como `data-rules.yml` e `flows.yml` | M3 |

Referências: [data-rules.yml](../reference/data-rules-yml.md) e [flows.yml](../reference/flows-yml.md).

Módulos do `probe` (M3, [ADR 0018](../adr/0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md)):

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

A referência campo a campo do perfil está em [../reference/target-yml.md](../reference/target-yml.md).

Também existem, desde o M4 e o M5: `finding.py` (`Finding`, `compute_fingerprint`), `run.py` e `probe_result.py` (`RunManifest`), `routing_headers.py` (cabeçalhos que só o cliente HTTP define) e `scan_config.py` (`effective_fail_on`). A distribuição por marco segue o [roadmap](../roadmap.md).

A tabela acima cobre o M1 ao M5. As versões 1.1 e 1.2 acrescentaram famílias de módulos, todas puras e testadas; o contrato de cada uma está no docstring do módulo e no ADR citado. Esta lista não é exaustiva (o diretório é a fonte):

| Família | Módulos | ADR |
| --- | --- | --- |
| Cerca com motivo granular e modo amplo | `scope_reason.py`, `scope_labels.py`, `widepath.py`, `wide_guard.py`, `traffic.py` | [0026](../adr/0026-cerca-com-motivo-granular-e-modo-amplo-de-caminho.md) |
| Teste de autorização entre contas | `authz_config.py`, `authz_plan.py`, `authz_compare.py`, `authz_result.py`, `authz_findings.py`, `authz_sensitive.py`, `probe_exchange.py` | [0027](../adr/0027-teste-de-autorizacao-entre-contas.md) |
| Relatório agrupado e `report.html` | `finding_group.py`, `known_patterns.py`, `report_*.py`, `html_safe.py`, `markdown_safe.py`, `fix_hints.py` | [0029](../adr/0029-relatorio-agrupado-pagina-html-e-skill-de-um-pedido-so.md) |
| Medição da execução | `run_metrics.py`, `rule_stats.py`, `run_summary.py` | [0031](../adr/0031-medicao-da-execucao-metrics-json-e-tempo-por-regra-do-zap.md) |
| Painel, diário de comandos e explicação de falha | `panel_*.py`, `command_journal.py`, `command_translation.py`, `finding_explain.py`, `finding_confidence.py`, `manual_repro.py`, `agent_metrics.py` | [0032](../adr/0032-painel-da-execucao.md), [0033](../adr/0033-diario-de-comandos.md), [0034](../adr/0034-indices-do-painel-e-pagina-ao-vivo.md) (os três Propostos) |

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

Os módulos listados estão implementados e testados e são usados pelos comandos da CLI. O número de cobertura (100% na revisão de 2026-11-13) envelhece: a fonte é o relatório do CI. Módulo planejado que ainda não existe não aparece nesta página. A fonte do estado é a [tabela de status](../roadmap.md#tabela-de-status).

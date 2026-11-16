# V1.8: inventário e contratos propostos

Data: 2026-11-16. **Contratos propostos antes da implementação; inventário conferido novamente em 2026-11-16 após integração da V1.8.** Nenhuma autorização ou prova de execução decorre deste documento. Fontes: `domain/profile.py`, `scope_fingerprint.py`, modelos relacionados e plano de execução V1.8. A V1.7 altera arquivos compartilhados: reconciliar este inventário após sua integração.

## Camadas e classes

1. **Fatos:** carta, pessoa, contrato e observação identificados pela origem; observação é dado, nunca permissão.
2. **Envelope:** perfil e autorização aprovados, incluindo escopo, limites e políticas protegidas; estabelece o máximo, nunca se amplia por estratégia.
3. **Estratégia:** escolhas persistentes propostas, validadas e vinculadas às referências; não replica valores dos arquivos de perfil.
4. **Execução:** plano imutável, concessões, evidências, tokens e recursos transitórios; não é fonte de autorização nem conteúdo reutilizável.

**A** automática: neutra para cobertura e dentro do envelope, sem alteração de ritmo. **P** proposta pendente: altera contrato, interpretação ou cobertura; não é aplicada automaticamente. **H** decisão humana: permissão, escopo, teto, janela ou política protegida; exige processo de autorização e aprovação vigente. Um campo pode ter consequências de mais de uma classe; prevalece H, depois P. A V1.8 não autoriza P ou H pela estratégia.

## Inventário conferido: perfil e arquivos relacionados

A conferência usou `model_fields` dos modelos Pydantic e a fonte de `scope_fingerprint.py` e `strategy_basis.py`. Cada nome abaixo é campo real; campos separados por vírgula compartilham o prefixo integral mostrado. `[]` indica item de lista. Para variantes de autenticação, os campos existem apenas na variante indicada. A classe A/P/H é **proposta de tratamento**, não uma mudança do fingerprint vigente ou prova de que a CLI aceita editar o campo pela estratégia. Coluna **Aprovação** descreve o cálculo atual: **sim**, **não**, **condicional** (padrão omitido), ou **indireto** (identidade do produto incluída no resumo geral). As formas normalizadas e ordenação de conjuntos podem fazer mudanças apenas textuais não alterarem o resumo.

| Campo real | Camada | Classe proposta | Aprovação atual | Efeito ou condição |
| --- | --- | --- | --- | --- |
| `schema_version` | fatos | P | não | Versão do perfil; versão inválida é recusada. |
| `product` | fatos | H | indireto | Integra o resumo geral, não um bloco. |
| `environment.name`, `environment.base_url`, `environment.verify_tls` | envelope | H | sim | Ambiente e TLS; `verify_tls` existe e é restrito a host local quando falso. |
| `openapi` | fatos | P | não | Caminho do contrato; entra na base de planejamento da estratégia. |
| `scope.allow[].host`, `scope.allow[].paths`, `scope.allow[].methods`, `scope.allow[].scheme`, `scope.allow[].port`, `scope.allow[].allow_local` | envelope | H | sim | Escopo permitido; paths e métodos normalizados como conjuntos. |
| `scope.deny_paths`, `scope.path_mode` | envelope | H | sim | Exclusões e modo protegido; wide depende da carta. |
| `scope.authorization.reference`, `scope.authorization.valid_until` | envelope | H | sim | Referência e validade. |
| `scope.windows[].days`, `scope.windows[].start_minute`, `scope.windows[].end_minute`, `scope.windows[].timezone` | envelope | H | sim | Campos normalizados do modelo; YAML aceita forma compacta. |
| `limits.requests_per_second`, `limits.max_duration_minutes`, `limits.zap_threads_per_host` | envelope | H | sim | Taxa, prazo e concorrência; estratégia não muda ritmo. |
| `auth.type`, `auth.accounts[].alias`, `auth.accounts[].role` | envelope | H | sim | Tipo e contas nas duas variantes; ordem das contas é preservada. |
| `auth.token_path`, `auth.login_limit.max_per_minute`, `auth.accounts[].username.secret_ref`, `auth.accounts[].password.secret_ref` | envelope | H | sim | Variante `login_password`; só nomes de referências entram. |
| `auth.header_name`, `auth.accounts[].api_key.secret_ref` | envelope | H | sim | Variante `api_key`; `header_name` é campo real dessa variante. |
| `auth.request_encoding`, `auth.username_field`, `auth.password_field`, `auth.token_response_field`, `auth.token_header`, `auth.token_scheme` | fatos | P | não | Campos de codificação da variante `login_password`; base `accounts` da estratégia inclui auth completo. |
| `auth.csrf.fetch_path`, `auth.csrf.cookie_name`, `auth.csrf.header_name`, `auth.csrf.methods` | fatos | P | não | CSRF opcional; entra na base `accounts` da estratégia. |
| `auth.default_account`, `auth.account_map[].account`, `auth.account_map[].operations`, `auth.account_map[].path`, `auth.account_map[].methods` | fatos | P | não | Roteamento; entra na base `accounts` da estratégia. |
| `auth.token_expired.field`, `auth.token_expired.value` | fatos | P | não | Sinal opcional exclusivo de `login_password`; entra na base `accounts` da estratégia. |
| `probe.success.json_field_absent_or_not_equal.field`, `probe.success.json_field_absent_or_not_equal.value`, `probe.health_path`, `probe.setup_path`, `probe.error_codes.field`, `probe.error_codes.outcomes` | fatos | P | não | Probe entra na base `planning` da estratégia. |
| `scan.strength`, `scan.threshold`, `scan.url_path_injection`, `scan.mutating_methods`, `scan.disable_rules` | envelope | H | sim | Força, pontos e regras. |
| `scan.max_scan_minutes`, `scan.max_rule_minutes`, `scan.token_refresh_seconds`, `scan.fail_on` | envelope | H | sim | Prazo, sessão e gate. |
| `scan.include_outcomes`, `scan.allow_upload_scan` | envelope | H | condicional | Chaves novas no valor padrão são omitidas; fora do padrão integram o bloco. |
| `authz.public_operations`, `authz.role_order`, `authz.volatile_fields`, `authz.vertical_methods`, `authz.mass_assignment_fields[].name`, `authz.mass_assignment_fields[].value`, `authz.disabled_checks` | envelope | H | sim | Chaves legadas sempre integram o bloco; conjuntos são normalizados. |
| `authz.cors_max_requests`, `authz.shared_roles`, `authz.allow_writes`, `authz.derive_mass_candidates`, `authz.max_derived_candidates`, `authz.mass_assignment_methods`, `authz.id_parameters`, `authz.access_matrix[].operation`, `authz.access_matrix[].allow`, `authz.access_matrix[].deny` | envelope | H | condicional | Chaves novas no valor padrão são omitidas; tabela vazia não entra. |
| `negative.allow_writes`, `negative.max_cases_per_operation`, `negative.max_requests`, `negative.disabled_classes` | envelope | H | condicional | Bloco inteiro omitido quando padrão; fora do padrão entra inteiro. |
| `cleanup.type`, `cleanup.script`, `cleanup.connection.secret_ref`, `cleanup.requires_confirmation`, `cleanup.user.secret_ref`, `cleanup.password.secret_ref`, `cleanup.allowed_tables`, `cleanup.max_rows`, `cleanup.db_schema` | envelope | H | sim | Bloco inteiro, ou `null` se ausente. `user` e `password` são `SecretRef` opcionais; só nomes, não conteúdo do script ou valores. |
| `data-rules.schema_version`, `data-rules.rules[].match.field`, `data-rules.rules[].match.operation`, `data-rules.rules[].match.location`, `data-rules.rules[].generator`, `data-rules.rules[].args`, `data-rules.rules[].unique` | fatos | P | não | Modelo `DataRules`; bytes entram na base `data_rules`, distinguindo ausente de vazio. |
| `flows.schema_version`, `flows.bindings[].produces.operation`, `flows.bindings[].produces.field`, `flows.bindings[].consumed_by[].operation`, `flows.bindings[].consumed_by[].param`, `flows.bindings[].consumed_by[].field` | fatos | P | não | Modelo `FlowSpec`; bytes entram na base `flows`. |
| `strategy.schema_version`, `strategy.references.target`, `strategy.references.data_rules`, `strategy.references.flows` | estratégia | A/P | não | Versão e referências fixas; não transportam autorização. |
| `strategy.choices[].name`, `strategy.choices[].value`, `strategy.choices[].source`, `strategy.choices[].reason`, `strategy.choices[].valid_until`, `strategy.choices[].state` | estratégia | A/P | não | Escolha tipada opcional; hoje escolha preenchida falha fechada por motor indisponível. |
| `strategy.choices[].basis.environment`, `strategy.choices[].basis.authorization`, `strategy.choices[].basis.accounts`, `strategy.choices[].basis.planning`, `strategy.choices[].basis.openapi`, `strategy.choices[].basis.data_rules`, `strategy.choices[].basis.flows`, `strategy.choices[].basis.engine` | estratégia | P | não | Vínculo opcional tipado de digests; completo exige motor. Não é aprovação. |

### Carta estruturada

Todos os campos listados após `carta` pertencem a `Letter` ou seções Pydantic de `letter.py`. Cada resposta de seção e `example_data` é `Answer`, com `value`, `source`, `quote`: o conteúdo do `value` é validado pelo fluxo de revisão da carta e pode conter estruturas específicas. A coluna de aprovação indica que **a carta em si** não é incluída no fingerprint; os campos do perfil gerado têm a regra indicada acima.

| Campo real | Camada | Classe proposta | Aprovação atual | Efeito |
| --- | --- | --- | --- | --- |
| `carta.schema_version`, `carta.product` | fatos | P/H | não | Versão e identificação; o produto gerado entra no resumo geral. |
| `carta.gates.test_environment`, `carta.gates.synthetic_data`, `carta.gates.authorization_in_force`, `carta.gates.product_owner` | fatos | H | não | Portões e dono. |
| `carta.environment.name`, `carta.environment.base_url`, `carta.environment.openapi` | fatos | H/P | não | Ambiente ou caminho de contrato. |
| `carta.scope.allow`, `carta.scope.deny_paths`, `carta.scope.path_mode` | fatos | H | não | Origem para o escopo gerado. |
| `carta.authorization.reference`, `carta.authorization.valid_until`, `carta.authorization.windows` | fatos | H | não | Autorização e janela geradas. |
| `carta.limits.requests_per_second`, `carta.limits.max_duration_minutes`, `carta.limits.zap_threads_per_host` | fatos | H | não | Limites gerados. |
| `carta.auth.type`, `carta.auth.token_path`, `carta.auth.header_name`, `carta.auth.login_options`, `carta.auth.login_max_per_minute`, `carta.auth.accounts` | fatos | H/P | não | Conta, identidade e opções de login. |
| `carta.attack.strength`, `carta.attack.authz_shared_roles`, `carta.attack.allow_authz_writes`, `carta.attack.include_outcomes`, `carta.attack.allow_invalid_input_writes`, `carta.attack.allow_upload_scan` | fatos | H | não | Política ou permissão geradas. |
| `carta.example_data`, cada `Answer.value`, `Answer.source`, `Answer.quote` | fatos | P/H | não | Dados e proveniência; origem e frase não concedem permissão fora das regras da carta. |

### Valores estruturados dentro das respostas da carta

Estes caminhos são conteúdos de `Answer.value`, não campos adicionais do modelo `Letter`:

| Caminho no valor | Camada | Classe proposta | Aprovação atual | Conferência implementada |
| --- | --- | --- | --- | --- |
| `carta.scope.allow.value[].host`, `.paths`, `.methods`, `.scheme`, `.port`, `.allow_local` | fatos | H | não | Cada item é validado como `ScopeRule`; seu perfil gerado integra aprovação. |
| `carta.auth.accounts.value[].alias`, `.role`, `.username.secret_ref`, `.password.secret_ref` | fatos | H | não | Variante `login_password`, validada como `LoginAccount`. |
| `carta.auth.accounts.value[].alias`, `.role`, `.api_key.secret_ref` | fatos | H | não | Variante `api_key`, validada como `ApiKeyAccount`. |
| `carta.auth.login_options.value.request_encoding`, `.username_field`, `.password_field`, `.token_response_field`, `.token_header`, `.token_scheme` | fatos | P | não | Mapa fechado de textos aceito para `login_password`; outras chaves são recusadas. |
| `carta.example_data.value[]` | fatos | P | não | Lista de mapas com valores JSON; `operation`, `field`, `value` e `note` são exemplos sugeridos na mensagem, não um conjunto fechado de chaves imposto pelo modelo. |

`carta.attack.include_outcomes` aceita origem `carta` ou `pessoa` segundo a revisão específica, diferentemente das permissões de escrita e upload que exigem frase da carta. Classes A/P/H neste inventário não alteram essas regras existentes.

O estado de execução contém plano, concessões, evidências e recursos temporários: é a quarta camada, não campo do perfil nem fonte de permissão. A revalidação por concessão do proxy permanece requisito não comprovado; a revalidação nos pontos de polling e envio do scan foi testada. A base `authorization` da estratégia deriva de blocos protegidos **exceto** `environment`, `auth` e `cleanup`; ambiente e auth têm bases próprias e limpeza não integra essa base. A base de estratégia não é a impressão digital de aprovação.

## Aceites antes do código

- T1 compara item por item operações, contas, pontos, regras, força e pré-condições com e sem estratégia; hash sozinho não prova igualdade. Perfil antigo sem estratégia é equivalente.
- Recusar campo ausente, inválido ou desconhecido, NaN/infinito, unidade ambígua, caminho absoluto/externo ou ciclo, proveniência inválida e composição conflitante, sem ecoar valores sensíveis.
- Provar que alargamento, P e H não são executados por escolha A; aprovação anterior não autoriza novo parâmetro. Migração é explícita, cópia separada e diff, sem escrita sobre origem ou aprovação.
- Validar, comparar e compilar sem tráfego; JSON v1 e saídas previsíveis. Alteração posterior no disco não muda plano em execução; testar revogação entre compilação e concessão e fechamento por janela, prazo ou stop.
- T2 direcionado e T4 completos nas duas APIs, preservando critérios de autorização, cobertura, detecção, falsos positivos, identidade e evidência da seção 3 do plano. Sem pares A/B; sem rodada cega nesta execução, por decisão do briefing. Ausência de prova não é sucesso.
- Persistência exclui credenciais, tokens, cookies, respostas integrais, identificadores efêmeros e gabarito. Texto de fontes externas é dado. Mudanças de ambiente, contrato, conta, autorização ou motor invalidam escolhas dependentes; reutilização executável pertence à V1.9.

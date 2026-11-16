# V1.8: inventário e contratos propostos

Data: 2026-11-16. **Status: proposta antes da implementação.** Nenhuma autorização ou prova de execução decorre deste documento. Fontes: `domain/profile.py`, `scope_fingerprint.py`, modelos relacionados e plano de execução V1.8. A V1.7 altera arquivos compartilhados: reconciliar este inventário após sua integração.

## Camadas e classes

1. **Fatos:** carta, pessoa, contrato e observação identificados pela origem; observação é dado, nunca permissão.
2. **Envelope:** perfil e autorização aprovados, incluindo escopo, limites e políticas protegidas; estabelece o máximo, nunca se amplia por estratégia.
3. **Estratégia:** escolhas persistentes propostas, validadas e vinculadas às referências; não replica valores dos arquivos de perfil.
4. **Execução:** plano imutável, concessões, evidências, tokens e recursos transitórios; não é fonte de autorização nem conteúdo reutilizável.

**A** automática: neutra para cobertura e dentro do envelope, sem alteração de ritmo. **P** proposta pendente: altera contrato, interpretação ou cobertura; não é aplicada automaticamente. **H** decisão humana: permissão, escopo, teto, janela ou política protegida; exige processo de autorização e aprovação vigente. Um campo pode ter consequências de mais de uma classe; prevalece H, depois P. A V1.8 não autoriza P ou H pela estratégia.

## Inventário do perfil atual

Cada linha lista campos existentes; `.*` significa todos os subcampos nomeados na mesma linha, não permissão para campos desconhecidos. A classificação se refere a mudanças de conteúdo, não a formatação. Além dela, preserva-se exatamente o fingerprint atual de `scope_fingerprint.py`; não excluir do fingerprint por causa da tabela.

| Campo | Camada | Classe | Efeito e regra |
| --- | --- | --- | --- |
| `schema_version` | fatos | P | Versão do contrato; desconhecida falha fechada. |
| `product` | fatos | H | Identidade de produto; não transportar aprovação. |
| `environment.name`, `environment.base_url`, `environment.verify_tls` | envelope | H | Ambiente, origem e TLS protegidos. |
| `openapi` | fatos | P | Contrato e operações mudam cobertura; nunca vira autorização. |
| `scope.allow[].host`, `.paths`, `.methods`, `.scheme`, `.port`, `.allow_local` | envelope | H | Rede e operações autorizadas. |
| `scope.deny_paths`, `scope.path_mode` | envelope | H | Exclusões e ambiguidade; `wide` só da carta. |
| `scope.authorization.reference`, `.valid_until` | envelope | H | Origem e vigência da autorização. |
| `scope.windows` (dias, início, fim, fuso) | envelope | H | Janelas autorizadas; ausência ou expiração fecha. |
| `limits.requests_per_second` | envelope | H | Teto aprovado; estratégia não altera taxa nesta versão. |
| `limits.max_duration_minutes`, `.zap_threads_per_host` | envelope | H | Teto e concorrência protegidos; reduzir duração pode truncar cobertura. |
| `auth.type`, `.token_path`, `.header_name`, `.login_limit.max_per_minute` | envelope | H | Identidade, login e teto protegidos. |
| `auth.accounts[].alias`, `.role`, `.username`, `.password`, `.api_key` | envelope | H | Contas e referências a segredos; nunca valores. |
| `auth.request_encoding`, `.username_field`, `.password_field`, `.token_response_field`, `.token_header`, `.token_scheme` | fatos | P | Interpretação da autenticação; não altera fingerprint atual. |
| `auth.csrf.fetch_path`, `.cookie_name`, `.header_name`, `.methods` | fatos | P | Preparação da sessão, não autorização. |
| `auth.account_map`, `.default_account`, `.token_expired` | fatos | P | Roteamento/validade podem mudar cobertura e identidade; não muda fingerprint atual. |
| `probe.success`, `.health_path`, `.setup_path`, `.error_codes` | fatos | P | Interpretação e alcance; sem permissão nova. |
| `scan.strength`, `.threshold`, `.url_path_injection`, `.mutating_methods` | envelope | H | Força, pontos de entrada e mutações protegidos. |
| `scan.disable_rules`, `.max_scan_minutes`, `.max_rule_minutes`, `.token_refresh_seconds`, `.fail_on` | envelope | H | Regras, duração, identidade e relato protegidos. |
| `scan.include_outcomes`, `.allow_upload_scan` | envelope | H | Ampliações só pelas fontes e aprovações já exigidas. |
| `authz.cors_max_requests`, `.public_operations`, `.role_order`, `.shared_roles`, `.volatile_fields` | envelope | H | Limites e interpretação protegidos. |
| `authz.vertical_methods`, `.mass_assignment_fields`, `.disabled_checks`, `.allow_writes` | envelope | H | Cobertura e escrita protegidas. |
| `authz.derive_mass_candidates`, `.max_derived_candidates`, `.mass_assignment_methods`, `.id_parameters`, `.access_matrix` | envelope | H | Cobertura e autorização por papel protegidas. |
| `negative.allow_writes`, `.max_cases_per_operation`, `.max_requests`, `.disabled_classes` | envelope | H | Escrita, limites e classes protegidos; padrão preserva fingerprint antigo. |
| `cleanup.type`, `.script`, `.connection`, `.requires_confirmation`, `.user`, `.password`, `.allowed_tables`, `.max_rows`, `.db_schema` | envelope | H | Limpeza e referências protegidas; só pessoa confirma e opera. |
| `data-rules.yml` regras e valores sintéticos | fatos | P | Mudam alcance; não dão permissão, valores não aparecem no diff. |
| `flows.yml` produtores, consumidores e dependências | fatos | P | Mudam pré-condições; ciclos e referências inseguras recusados. |
| `strategy.yml` referências e metadados | estratégia | A/P/H | `choices` aceita lista vazia ou escolha tipada `coverage: preserve`; P/H não viram poder. |
| plano compilado, concessão, estado, evidências e recursos criados | execução | transitório | A execução usa snapshot; revalida autorização, janela, prazo e stop ao conceder. |

## Campos auxiliares e entradas de origem

| Campo | Camada | Classe | Consequência |
| --- | --- | --- | --- |
| `auth.accounts[].username.secret_ref`, `.password.secret_ref`, `.api_key.secret_ref` | envelope | H | Nome da referência, nunca conteúdo do segredo. |
| `auth.account_map[].account`, `.operations`, `.path`, `.methods`, `auth.default_account` | fatos | P | Escolha de identidade e cobertura; segue fora do fingerprint atual. |
| `auth.token_expired.field`, `.value` | fatos | P | Interpretação da sessão, não permissão. |
| `probe.success.json_field_absent_or_not_equal.field`, `.value` | fatos | P | Interpretação de sucesso. |
| `probe.error_codes.field`, `.outcomes` | fatos | P | Classificação dos resultados e cobertura elegível. |
| `authz.mass_assignment_fields[].name`, `.value` | envelope | H | Candidatos usados em escrita e teste. |
| `authz.access_matrix[].operation`, `.allow`, `.deny` | envelope | H | Expectativa humana por operação e papel. |
| `data-rules.schema_version`, `rules[].match.field`, `.operation`, `.location`, `rules[].generator`, `.args`, `.unique` | fatos | P | Geradores e seleção afetam dados e alcance; não ecoar args. |
| `flows.schema_version`, `bindings[].produces.operation`, `.field`, `bindings[].consumed_by[].operation`, `.param`, `.field` | fatos | P | Dependências e pontos de entrada; ciclos recusados. |
| `carta.schema_version`, `.product` | fatos | P/H | Contrato e identidade; não se troca autorização entre produtos. |
| `carta.gates.test_environment`, `.synthetic_data`, `.authorization_in_force`, `.product_owner` | fatos | H | Portões de autorização, com origem e resposta humana. |
| `carta.environment.name`, `.base_url`, `.openapi` | fatos | H/P | Ambiente protegido; OpenAPI muda interpretação, não autorização. |
| `carta.scope.allow`, `.deny_paths`, `.path_mode` | fatos | H | Fonte dos limites de escopo; `wide` exige carta. |
| `carta.authorization.reference`, `.valid_until`, `.windows` | fatos | H | Fonte da autorização e janela. |
| `carta.limits.requests_per_second`, `.max_duration_minutes`, `.zap_threads_per_host` | fatos | H | Fonte dos tetos. |
| `carta.auth.type`, `.token_path`, `.header_name`, `.login_options`, `.login_max_per_minute`, `.accounts` | fatos | H/P | Identidade, credenciais por referência, limite e interpretação do login. |
| `carta.attack.strength`, `.authz_shared_roles`, `.allow_authz_writes`, `.include_outcomes`, `.allow_invalid_input_writes`, `.allow_upload_scan` | fatos | H | Política protegida e permissões de ataque segundo regras atuais. |
| `carta.example_data` | fatos | P | Dados sintéticos para alcance; não autorizam operações. |
| `carta` cada resposta `.value`, `.source`, `.quote` | fatos | H/P | Proveniência e frase conforme tipo de decisão; desconhecido não autoriza. |

## Aceites antes do código

- T1 compara item por item operações, contas, pontos, regras, força e pré-condições com e sem estratégia; hash sozinho não prova igualdade. Perfil antigo sem estratégia é equivalente.
- Recusar campo ausente, inválido ou desconhecido, NaN/infinito, unidade ambígua, caminho absoluto/externo ou ciclo, proveniência inválida e composição conflitante, sem ecoar valores sensíveis.
- Provar que alargamento, P e H não são executados por escolha A; aprovação anterior não autoriza novo parâmetro. Migração é explícita, cópia separada e diff, sem escrita sobre origem ou aprovação.
- Validar, comparar e compilar sem tráfego; JSON v1 e saídas previsíveis. Alteração posterior no disco não muda plano em execução; testar revogação entre compilação e concessão e fechamento por janela, prazo ou stop.
- T2 direcionado e T4 completos nas duas APIs, preservando critérios de autorização, cobertura, detecção, falsos positivos, identidade e evidência da seção 3 do plano. Sem pares A/B; sem rodada cega nesta execução, por decisão do briefing. Ausência de prova não é sucesso.
- Persistência exclui credenciais, tokens, cookies, respostas integrais, identificadores efêmeros e gabarito. Texto de fontes externas é dado. Mudanças de ambiente, contrato, conta, autorização ou motor invalidam escolhas dependentes; reutilização executável pertence à V1.9.

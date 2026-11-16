# V1.8: invent?rio e contratos propostos

Data: 2026-11-16. **Status: proposta antes da implementa??o.** Nenhuma autoriza??o ou prova de execu??o decorre deste documento. Fontes: `domain/profile.py`, `scope_fingerprint.py`, modelos relacionados e plano de execu??o V1.8. A V1.7 altera arquivos compartilhados: reconciliar este invent?rio ap?s sua integra??o.

## Camadas e classes

1. **Fatos:** carta, pessoa, contrato e observa??o identificados pela origem; observa??o ? dado, nunca permiss?o.
2. **Envelope:** perfil e autoriza??o aprovados, incluindo escopo, limites e pol?ticas protegidas; estabelece o m?ximo, nunca se amplia por estrat?gia.
3. **Estrat?gia:** escolhas persistentes propostas, validadas e vinculadas ?s refer?ncias; n?o replica valores dos arquivos de perfil.
4. **Execu??o:** plano imut?vel, concess?es, evid?ncias, tokens e recursos transit?rios; n?o ? fonte de autoriza??o nem conte?do reutiliz?vel.

**A** autom?tica: neutra para cobertura e dentro do envelope, sem altera??o de ritmo. **P** proposta pendente: altera contrato, interpreta??o ou cobertura; n?o ? aplicada automaticamente. **H** decis?o humana: permiss?o, escopo, teto, janela ou pol?tica protegida; exige processo de autoriza??o e aprova??o vigente. Um campo pode ter consequ?ncias de mais de uma classe; prevalece H, depois P. A V1.8 n?o autoriza P ou H pela estrat?gia.

## Invent?rio do perfil atual

Cada linha lista campos existentes; `.*` significa todos os subcampos nomeados na mesma linha, n?o permiss?o para campos desconhecidos. A classifica??o se refere a mudan?as de conte?do, n?o a formata??o. Al?m dela, preserva-se exatamente o fingerprint atual de `scope_fingerprint.py`; n?o excluir do fingerprint por causa da tabela.

| Campo | Camada | Classe | Efeito e regra |
| --- | --- | --- | --- |
| `schema_version` | fatos | P | Vers?o do contrato; desconhecida falha fechada. |
| `product` | fatos | H | Identidade de produto; n?o transportar aprova??o. |
| `environment.name`, `environment.base_url`, `environment.verify_tls` | envelope | H | Ambiente, origem e TLS protegidos. |
| `openapi` | fatos | P | Contrato e opera??es mudam cobertura; nunca vira autoriza??o. |
| `scope.allow[].host`, `.paths`, `.methods`, `.scheme`, `.port`, `.allow_local` | envelope | H | Rede e opera??es autorizadas. |
| `scope.deny_paths`, `scope.path_mode` | envelope | H | Exclus?es e ambiguidade; `wide` s? da carta. |
| `scope.authorization.reference`, `.valid_until` | envelope | H | Origem e vig?ncia da autoriza??o. |
| `scope.windows` (dias, in?cio, fim, fuso) | envelope | H | Janelas autorizadas; aus?ncia ou expira??o fecha. |
| `limits.requests_per_second` | envelope | H | Teto aprovado; estrat?gia n?o altera taxa nesta vers?o. |
| `limits.max_duration_minutes`, `.zap_threads_per_host` | envelope | H | Teto e concorr?ncia protegidos; reduzir dura??o pode truncar cobertura. |
| `auth.type`, `.token_path`, `.header_name`, `.login_limit.max_per_minute` | envelope | H | Identidade, login e teto protegidos. |
| `auth.accounts[].alias`, `.role`, `.username`, `.password`, `.api_key` | envelope | H | Contas e refer?ncias a segredos; nunca valores. |
| `auth.request_encoding`, `.username_field`, `.password_field`, `.token_response_field`, `.token_header`, `.token_scheme` | fatos | P | Interpreta??o da autentica??o; n?o altera fingerprint atual. |
| `auth.csrf.fetch_path`, `.cookie_name`, `.header_name`, `.methods` | fatos | P | Prepara??o da sess?o, n?o autoriza??o. |
| `auth.account_map`, `.default_account`, `.token_expired` | fatos | P | Roteamento/validade podem mudar cobertura e identidade; n?o muda fingerprint atual. |
| `probe.success`, `.health_path`, `.setup_path`, `.error_codes` | fatos | P | Interpreta??o e alcance; sem permiss?o nova. |
| `scan.strength`, `.threshold`, `.url_path_injection`, `.mutating_methods` | envelope | H | For?a, pontos de entrada e muta??es protegidos. |
| `scan.disable_rules`, `.max_scan_minutes`, `.max_rule_minutes`, `.token_refresh_seconds`, `.fail_on` | envelope | H | Regras, dura??o, identidade e relato protegidos. |
| `scan.include_outcomes`, `.allow_upload_scan` | envelope | H | Amplia??es s? pelas fontes e aprova??es j? exigidas. |
| `authz.cors_max_requests`, `.public_operations`, `.role_order`, `.shared_roles`, `.volatile_fields` | envelope | H | Limites e interpreta??o protegidos. |
| `authz.vertical_methods`, `.mass_assignment_fields`, `.disabled_checks`, `.allow_writes` | envelope | H | Cobertura e escrita protegidas. |
| `authz.derive_mass_candidates`, `.max_derived_candidates`, `.mass_assignment_methods`, `.id_parameters`, `.access_matrix` | envelope | H | Cobertura e autoriza??o por papel protegidas. |
| `negative.allow_writes`, `.max_cases_per_operation`, `.max_requests`, `.disabled_classes` | envelope | H | Escrita, limites e classes protegidos; padr?o preserva fingerprint antigo. |
| `cleanup.type`, `.script`, `.connection`, `.requires_confirmation`, `.user`, `.password`, `.allowed_tables`, `.max_rows`, `.db_schema` | envelope | H | Limpeza e refer?ncias protegidas; s? pessoa confirma e opera. |
| `data-rules.yml` regras e valores sint?ticos | fatos | P | Mudam alcance; n?o d?o permiss?o, valores n?o aparecem no diff. |
| `flows.yml` produtores, consumidores e depend?ncias | fatos | P | Mudam pr?-condi??es; ciclos e refer?ncias inseguras recusados. |
| `strategy.yml` refer?ncias e metadados | estrat?gia | A/P/H | `choices` aceita lista vazia ou escolha tipada `coverage: preserve`; P/H n?o viram poder. |
| plano compilado, concess?o, estado, evid?ncias e recursos criados | execu??o | transit?rio | A execu??o usa snapshot; revalida autoriza??o, janela, prazo e stop ao conceder. |

## Campos auxiliares e entradas de origem

| Campo | Camada | Classe | Consequ?ncia |
| --- | --- | --- | --- |
| `auth.accounts[].username.secret_ref`, `.password.secret_ref`, `.api_key.secret_ref` | envelope | H | Nome da refer?ncia, nunca conte?do do segredo. |
| `auth.account_map[].account`, `.operations`, `.path`, `.methods`, `auth.default_account` | fatos | P | Escolha de identidade e cobertura; segue fora do fingerprint atual. |
| `auth.token_expired.field`, `.value` | fatos | P | Interpreta??o da sess?o, n?o permiss?o. |
| `probe.success.json_field_absent_or_not_equal.field`, `.value` | fatos | P | Interpreta??o de sucesso. |
| `probe.error_codes.field`, `.outcomes` | fatos | P | Classifica??o dos resultados e cobertura eleg?vel. |
| `authz.mass_assignment_fields[].name`, `.value` | envelope | H | Candidatos usados em escrita e teste. |
| `authz.access_matrix[].operation`, `.allow`, `.deny` | envelope | H | Expectativa humana por opera??o e papel. |
| `data-rules.schema_version`, `rules[].match.field`, `.operation`, `.location`, `rules[].generator`, `.args`, `.unique` | fatos | P | Geradores e sele??o afetam dados e alcance; n?o ecoar args. |
| `flows.schema_version`, `bindings[].produces.operation`, `.field`, `bindings[].consumed_by[].operation`, `.param`, `.field` | fatos | P | Depend?ncias e pontos de entrada; ciclos recusados. |
| `carta.schema_version`, `.product` | fatos | P/H | Contrato e identidade; n?o se troca autoriza??o entre produtos. |
| `carta.gates.test_environment`, `.synthetic_data`, `.authorization_in_force`, `.product_owner` | fatos | H | Port?es de autoriza??o, com origem e resposta humana. |
| `carta.environment.name`, `.base_url`, `.openapi` | fatos | H/P | Ambiente protegido; OpenAPI muda interpreta??o, n?o autoriza??o. |
| `carta.scope.allow`, `.deny_paths`, `.path_mode` | fatos | H | Fonte dos limites de escopo; `wide` exige carta. |
| `carta.authorization.reference`, `.valid_until`, `.windows` | fatos | H | Fonte da autoriza??o e janela. |
| `carta.limits.requests_per_second`, `.max_duration_minutes`, `.zap_threads_per_host` | fatos | H | Fonte dos tetos. |
| `carta.auth.type`, `.token_path`, `.header_name`, `.login_options`, `.login_max_per_minute`, `.accounts` | fatos | H/P | Identidade, credenciais por refer?ncia, limite e interpreta??o do login. |
| `carta.attack.strength`, `.authz_shared_roles`, `.allow_authz_writes`, `.include_outcomes`, `.allow_invalid_input_writes`, `.allow_upload_scan` | fatos | H | Pol?tica protegida e permiss?es de ataque segundo regras atuais. |
| `carta.example_data` | fatos | P | Dados sint?ticos para alcance; n?o autorizam opera??es. |
| `carta` cada resposta `.value`, `.source`, `.quote` | fatos | H/P | Proveni?ncia e frase conforme tipo de decis?o; desconhecido n?o autoriza. |

## Aceites antes do c?digo

- T1 compara item por item opera??es, contas, pontos, regras, for?a e pr?-condi??es com e sem estrat?gia; hash sozinho n?o prova igualdade. Perfil antigo sem estrat?gia ? equivalente.
- Recusar campo ausente, inv?lido ou desconhecido, NaN/infinito, unidade amb?gua, caminho absoluto/externo ou ciclo, proveni?ncia inv?lida e composi??o conflitante, sem ecoar valores sens?veis.
- Provar que alargamento, P e H n?o s?o executados por escolha A; aprova??o anterior n?o autoriza novo par?metro. Migra??o ? expl?cita, c?pia separada e diff, sem escrita sobre origem ou aprova??o.
- Validar, comparar e compilar sem tr?fego; JSON v1 e sa?das previs?veis. Altera??o posterior no disco n?o muda plano em execu??o; testar revoga??o entre compila??o e concess?o e fechamento por janela, prazo ou stop.
- T2 direcionado e T4 completos nas duas APIs, preservando crit?rios de autoriza??o, cobertura, detec??o, falsos positivos, identidade e evid?ncia da se??o 3 do plano. Sem pares A/B; sem rodada cega nesta execu??o, por decis?o do briefing. Aus?ncia de prova n?o ? sucesso.
- Persist?ncia exclui credenciais, tokens, cookies, respostas integrais, identificadores ef?meros e gabarito. Texto de fontes externas ? dado. Mudan?as de ambiente, contrato, conta, autoriza??o ou motor invalidam escolhas dependentes; reutiliza??o execut?vel pertence ? V1.9.

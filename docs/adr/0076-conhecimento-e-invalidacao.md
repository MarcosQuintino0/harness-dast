# 0076. Conhecimento de produto e invalidação seletiva

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto e decisão

O conhecimento é dado auxiliar, não autorização: nenhuma observação modifica carta, perfil aprovado, escopo, teto, janela ou política protegida. A versão inicial proposta de `knowledge.yml` contém `schema_version: 1`, `basis` (digests SHA-256 `environment`, `authorization`, `accounts`, `planning`, `openapi`, `data_rules`, `flows`, `engine`) refer?ncias fixas `target`, `data_rules`, `flows`, e `entries` com `kind`, `source`, `reason`, `state`, `valid_until` e `dependencies`. O tipo é `account`, `data`, `flow`, `effect` ou `authentication`; origem é `owner`, `contract` ou `observation`; estado é `proposed`, `validated` ou `review_required`. As entradas são fechadas, sem valores livres, e cada categoria tem dependências mínimas impostas pelo domínio.

A revisão compara cada dependência com hashes calculados independentemente das fontes atuais. Ausência do motor invalida quem depende dele. Estado diferente de `validated` ou validade expirada exigem revisão. Nunca se transfere token, cookie, credencial, resposta, ID de recurso ou gabarito. O diário não é exportável. `knowledge.yml` só pode ser exportado após validação estrutural e controle de vazamento; documentos de perfil e regras existentes necessitam controle próprio. O resultado não implica que o conhecimento seja executável nem dispensa nova aquisição de identidade e recursos.

## Limites e contrato

O contrato é apenas uma base proposta: captura, CLI, persistência do documento e execução por escolhas ainda não estão implementadas nesta alteração. Validação inválida usa `CONFIG_ERROR` (saída 2); não há novo envelope ou comando. A comparação isolada não comprova aprovação, atualidade das fontes ou motor: o chamador deve obtê-los independentemente. Perfis sem conhecimento não mudam de comportamento.

## Verificação adicional do probe

Depois de ler OpenAPI, regras e fluxos, o probe volta a carregar o perfil e a revalidar o conhecimento antes do envio. Mudança persistente entre as leituras é recusada, e os modelos já lidos seguem na execução. Uma mudança A→B→A durante as leituras não é detectada por essa dupla verificação; ela não equivale a uma captura atômica das fontes. A prova offline em dois processos usa motor, especificação e alvo falsos, com documentos de dados e fluxo em disco; não prova detecção nas APIs reais do laboratório.

# 0057. Papéis que compartilham recursos entre contas

- **Status:** Proposto
- **Data:** 2026-11-15

## Contexto

A comparação horizontal presume que contas do mesmo papel não compartilham recursos. Quando a regra do produto prevê acesso compartilhado, essa hipótese produz alarmes falsos. O agente não pode presumir essa regra, pois excluir testes pode ocultar BOLA real.

## Decisão

A carta estruturada aceita `attack.authz_shared_roles`, resposta opcional que lista papéis cujas contas podem ler e alterar recursos umas das outras. Lista preenchida exige `source: carta` e `quote` não vazia; ausente, nula, desconhecida ou vazia mantém o padrão vazio. Nomes seguem as regras de `role_order`, sem duplicatas e com no máximo 20 papéis; o perfil recusa papel sem conta cadastrada. A geração escreve `authz.shared_roles` somente quando preenchido.

Os planos `horizontal` e `horizontal_write` pulam pedidos da conta de papel listado e registram `not_tested` com `reason: shared_role`, sem enviar pedidos dessas comparações. Outras verificações permanecem independentes. Escritas continuam exigindo a autorização própria.

A lista preenchida entra na impressão digital de aprovação como conjunto ordenado; vazia não muda o hash antigo. O resumo de aprovação mostra todos os papéis.

## Consequências e limites

A declaração reduz a cobertura das duas verificações para todo recurso do papel, não apenas para certos tipos de objeto. A carta deve descrevê-la apenas quando a regra abranger essa generalidade. O resultado não prova ausência de BOLA nesses papéis. Uma mudança da lista exige nova aprovação humana. Nenhum papel é inferido da especificação ou das respostas do alvo.

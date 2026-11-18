# ADR 0078: prova do par criado e limite de atribuição em massa

Estado: Proposto. Data: 2026-11-16.

## Contexto e decisão

O sucesso HTTP de uma criação não prova por si só que o identificador devolvido era novo.
Se o corpo sintético fornece o identificador do GET provado, ambas as contas precisam receber 404
na leitura anterior ao POST. Quando o servidor gera o ID, é necessária uma coleção irmã já
provada pelo probe, cujo OpenAPI declare array de objetos sem parâmetros de consulta ou limite
de itens. As duas contas leem a coleção antes do POST; JSON inválido, item sem ID ou sem marcador,
marcador já presente ou recusa impedem a criação. A resposta 2xx precisa fornecer ID ausente dos
dois inventários e das leituras já conhecidas. A dona precisa ler o marcador independente enviado
no corpo antes da comparação com a conta par. O marcador usa valor sintético de regra `unique`,
valor alfanumérico aleatório já gerado por regra explícita, ou campo textual simples compatível
entre schemas de criação e leitura; neste último caso é gerado com etiqueta e contador da execução.
Campos vinculados, credenciais declaradas no perfil, campos de privilégio e formatos restritos
ficam de fora. Dados confidenciais sintéticos podem ser marcadores, somente em memória; regras
explícitas de constante e outras receitas não elegíveis são preservadas.
Ausência de ID,
divergência, recusa de escopo ou ausência não observada ficam não testadas. IDs só vivem em
memória, não no diário. Os pedidos continuam sujeitos à carta, ao escopo e ao teto de escritas.
Na extração do ID, chaves JSON repetidas, colisões de nomes de identidade após normalização e
divergência entre `Location` válido e identificador do corpo recusam a prova. Se o marcador do
caminho tiver nome distinto de `id`, ele tem prioridade sobre o campo genérico `id`.

O 404 comprova ausência *visível às contas consultadas*, não ausência global: APIs podem ocultar
objetos existentes com 404. Sem uma garantia do produto sobre o significado desse status, a
conclusão de novidade permanece limitada; o resultado deve ser interpretado nesse limite. Um array
sem parâmetros de consulta não prova que o servidor não aplica paginação ou filtros ocultos;
os inventários demonstram apenas os elementos visíveis nas respostas recebidas.
O marcador reduz confusão com um objeto preexistente, mas uma API que atualize um objeto oculto
em vez de criá-lo ainda impede comprovar novidade global.

A atribuição em massa permanece limitada a candidatos derivados genericamente do contrato ou
declarados, e exige observação do efeito. Uma resposta de sucesso sem o campo e sem leitura
compatível não prova efeito; não se usa conhecimento específico de produto para inventar
relações entre operações ou privilégios. A carta decide permissões, não a observação.

Quando uma releitura pela conta escritora comprova o efeito, `authz.json.effects` recebe somente
`write_operation`, `read_operation`, `account`, `fields` e `proof=readback_verified`; resposta de
escrita isolada não produz recibo, e campos classificados como segredo ou dado pessoal não são
exportados como receita. Receitas de efeito validadas podem associar um GET já provado
na conta ao candidato existente sem criar candidato nem escrita. Uma receita nunca substitui a
leitura atual antes de PUT/PATCH. Quando há GET planejado, sua recusa ou ausência de efeito não
é suprida pelo eco da escrita; o eco legado só pode ser usado quando não há GET. Essa correção
pode reduzir achados antes baseados em eco. O perfil, método, conta, esquema, escopo e limites atuais continuam
determinando o que pode ser enviado. GET de atualização precisa do mesmo alvo concreto; GET de
criação exige marcador de identificador no caminho. Receita desatualizada não é usada.

## Consequências

200 e outros 2xx passam pelo mesmo caminho de comprovação que 201. Alguns pares antes comparados
com 201 deixam de ser testados por falta de prova prévia. Isso é uma perda de cobertura explícita
que requer avaliação em laboratório; não afirma equivalência com V1.8. APIs sem identificador
antecipado nem coleção compatível continuam não testadas.

A auditoria identifica GETs efetivos escolhidos por receita com `effect_recipe_before` e
`effect_recipe_after`. Antes do PUT/PATCH, o snapshot seguro usa apenas valor da leitura atual;
resposta 5xx ou ausente deixa pendência, aviso de possível alteração e interrompe a execução,
sem restauração ou repetição automática. Sem GET, o eco legado não gera recibo de releitura.

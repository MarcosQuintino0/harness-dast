# ADR 0078: prova do par criado e limite de atribuição em massa

Estado: Proposto. Data: 2026-11-16.

## Contexto e decisão

O sucesso HTTP de uma criação não prova por si só que o identificador devolvido era novo.
Para comparar duas contas, o corpo sintético precisa fornecer identificador compatível com o
marcador do GET provado. Antes do POST, a dona consulta esse identificador pelo caminho guardado;
somente 404 para ambas as contas permite prosseguir. A resposta 2xx precisa identificá-lo novamente,
e a dona precisa ler um marcador independente, enviado no corpo e gerado por regra `unique`,
antes da comparação com a conta par. Ausência de ID,
divergência, recusa de escopo ou ausência não observada ficam não testadas. IDs só vivem em
memória, não no diário. Os pedidos continuam sujeitos à carta, ao escopo e ao teto de escritas.

O 404 comprova ausência *visível às contas consultadas*, não ausência global: APIs podem ocultar
objetos existentes com 404. Sem uma garantia do produto sobre o significado desse status, a
conclusão de novidade permanece limitada; o resultado deve ser interpretado nesse limite. Uma
API que gera o ID apenas no servidor não permite esta prova antecipada por esse mecanismo.
O marcador reduz confusão com um objeto preexistente, mas uma API que atualize um objeto oculto
em vez de criá-lo ainda impede comprovar novidade global.

A atribuição em massa permanece limitada a candidatos derivados genericamente do contrato ou
declarados, e exige observação do efeito. Uma resposta de sucesso sem o campo e sem leitura
compatível não prova efeito; não se usa conhecimento específico de produto para inventar
relações entre operações ou privilégios. A carta decide permissões, não a observação.

## Consequências

200 e outros 2xx passam pelo mesmo caminho de comprovação que 201. Alguns pares antes comparados
com 201 deixam de ser testados por falta de prova prévia. Isso é uma perda de cobertura explícita
que requer avaliação em laboratório; não afirma equivalência com V1.8. Para APIs cuja criação
gera o ID no servidor, é necessária uma fonte de prova anterior independente, ainda não definida.

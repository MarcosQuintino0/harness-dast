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
no corpo antes da comparação com a conta par. O marcador usa regra `unique` já declarada ou campo
textual simples compatível entre schemas de criação e leitura, não vinculado nem sensível; neste
caso é gerado com etiqueta e contador da execução. Regras explícitas não únicas são preservadas.
Ausência de ID,
divergência, recusa de escopo ou ausência não observada ficam não testadas. IDs só vivem em
memória, não no diário. Os pedidos continuam sujeitos à carta, ao escopo e ao teto de escritas.

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

## Consequências

200 e outros 2xx passam pelo mesmo caminho de comprovação que 201. Alguns pares antes comparados
com 201 deixam de ser testados por falta de prova prévia. Isso é uma perda de cobertura explícita
que requer avaliação em laboratório; não afirma equivalência com V1.8. APIs sem identificador
antecipado nem coleção compatível continuam não testadas.

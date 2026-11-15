# ADR 0055: Agrupar sinais pela operação do contrato

Estado: Proposto. Data: 2026-11-15.

## Contexto

O ADR 0049 agrupa sinais da cerca pelo caminho aproximado quando não resolve a operação. Em varreduras, muitos caminhos distintos chegam ao teto de 500 e escondem outros achados. Caminhos e respostas são dados externos; nenhum corpo deve ser guardado nos sinais.

## Decisão

O relatório resolve cada caminho da auditoria pelo método e pelos modelos do OpenAPI já registrados no `probe`. Cada parâmetro do modelo casa com um segmento concreto, inclusive quando o ZAP altera seu valor. Uma correspondência inequívoca mais específica prevalece; empates não recebem atribuição. Não mudamos a decisão da cerca nem interpretamos os sinais como autorização de tráfego.

Agrupamos por categoria, método e identificador da operação. O fingerprint versão 2 inclui produto, método, identificador e categoria. Todas as respostas sem correspondência inequívoca ficam num único grupo por categoria, com método vazio, operação ausente e caminho fixo `/fora-do-contrato`; o fingerprint desse grupo depende somente do produto e da categoria. Contagens e limites de detalhes continuam os mesmos, sem valores de caminho ou resposta nos achados.

## Consequências

As variações de identificador não criam achados extras. Uma operação omitida do `probe` ou uma rota ambígua permanece fora do contrato; o grupo agregado não permite saber qual caminho originou o sinal. O fingerprint mudou e não equivale ao da versão 1; arquivos antigos continuam legíveis, e sinais não participam de `--compare`. O arquivo OpenAPI pode ter mudado em opera??es ausentes do `probe`: n?o h? snapshot completo hist?rico para detectar essa mudan?a. A prova real depende de reconstruir a imagem e executar o teste de laboratório, fora deste degrau de desenvolvimento.

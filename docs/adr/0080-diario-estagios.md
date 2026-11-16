# ADR 0080: diário de mutação nos estágios ativos

Estado: Proposto. Data: 2026-11-16.

O diário do ADR 0077 é compartilhado entre `probe`, `authz`, `negative` e `scan` no diretório
privado de estado. A chave resume produto, operação, conta e método; não inclui valores, corpos,
URLs concretas ou IDs. Uma pendência impede a mesma classe de trabalho em outro estágio. Não há
reenvio automático de pedido mutante no emissor de `negative`, inclusive na restauração.

Antes de cada mutação, inclusive restaurações, grava-se intenção e estado anterior `unknown`.
Resposta HTTP inferior a 500 é registrada como `observed`: não declara que houve ou não efeito.
5xx, timeout, falha de transporte ou interrupção preservam a pendência. Uma restauração bloqueada
pelo diário não pode ser descrita como realizada; requer reconciliação. A reserva antecede o
envio real e falha fechada se o armazenamento não estiver utilizável.

O `scan` reserva antes de iniciar no ZAP cada lote de POST, PUT ou PATCH. A conclusão é apenas
observação do lote, nunca prova do estado do alvo. O registro só é concluído após confirmação de
término pelo ZAP em `FINISHED` com progresso 100, sem truncamento, e gravação dos artefatos finais
da CLI. `FINISHED` abaixo de 100, `STOPPED`, erro, interrupção ou falha de gravação conservam a
pendência. `ScanRefused` também conserva a pendência: a resposta da API não prova que nenhum pedido
foi enviado. GET segue fora do
diário, embora uma API possa atribuir-lhe efeito: o contrato não demonstra essa semântica.
`--dry-run` não escreve diário nem envia tráfego. O diário não amplia escopo nem permissões e
não fornece operação de recuperação cega.

# ADR 0060: não pontuar verificações de achados sem evidência

Status: Proposto. Data: 2026-11-15.

## Contexto

Sem `findings.json`, quatro verificações da triagem passavam por vacuidade e premiavam uma execução que não produziu achados. A existência de uma lista vazia é diferente da ausência do arquivo.

## Decisão

Se nenhuma execução gravou `findings.json`, marcar `covers_high`, `no_downgrade`, `no_fixed_claim` e `log_covers_high` como não aplicáveis (`passed: null`) e excluí-los da média de (f). Relatório, contrato de triagem e os dois checks gerais do diário continuam medidos. Se houver o arquivo, inclusive com lista vazia, os quatro checks permanecem aplicáveis. As notas históricas não são sobrescritas; recálculos devem indicar a régua utilizada.

## Consequências

O componente passa a refletir apenas verificações que têm evidência; ausência de relatório e de triagem ainda reduz a nota. Essa regra não supõe que houve varredura ou ausência de vulnerabilidades. Regra anterior e comparação reproduzível estão em `evals/results/2026-11-15-v1-5-4/`.

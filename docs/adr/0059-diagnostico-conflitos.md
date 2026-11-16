# 0059. Diagnóstico de conflitos e dependências bloqueadas

- **Status:** Proposto
- **Data:** 2026-11-15

## Contexto

Um 409 pode impedir uma cadeia de operações; a resposta ou o esquema fornecem pistas sem que seja preciso conhecer nomes do produto.

## Decisão

Em `conflict_fields` o resultado expõe apenas nomes simples de campos presentes no corpo enviado, indicados em `errors[].field`. Sem indicação utilizável, escolhe campos obrigatórios do esquema com formato, padrão ou tamanho máximo, cujos valores vieram de um gerador sem `unique`. Valores e textos livres do alvo não são incluídos. Campos encadeados, enums e regras únicas não entram no fallback. A lista é uma hipótese, não uma garantia da causa.

`blocked_dependencies` conta operações efetivamente puladas por dependência, transitivamente, uma vez por produtor e consumidor. Produtores com bloqueios aparecem em `summary.blocked_producers`, em ordem decrescente da contagem e por identificador no desempate. A execução antecipadamente interrompida considera só resultados efetivos.

## Consequências

O contrato de `probe.json` recebe campos novos. O esquema não representa marcadores arbitrários de unicidade; o fallback não detecta todos os conflitos e pode sugerir campos que não causaram o 409. O diagnóstico não altera envios ou permissões.

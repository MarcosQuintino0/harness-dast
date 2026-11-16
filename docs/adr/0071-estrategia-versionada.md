# 0071. Estrat?gia versionada

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

O produto precisa registrar escolhas sem duplicar autoriza??o ou estado transit?rio.

## Decis?o

Vamos propor `strategy.yml` com `schema_version: 1`, `references` contendo `target`, `data_rules` e `flows`, e `choices` como lista. Nesta vers?o `choices` aceita lista vazia ou uma ?nica escolha tipada: `name: coverage`, `value: preserve`, `source: owner|contract|observation`, `reason: preserve_baseline`, `valid_until` data ISO e `state: proposed|validated|review_required`. Sem texto livre. A compila??o exige estado `validated`, validade no instante informado e igualdade item a item com a refer?ncia; validate e diff podem mostrar pend?ncia. Observa??o nunca concede permiss?o. Refer?ncias s?o relativas, sem componentes vazios, `.` ou `..`, barras invertidas, unidade, URL ou controles, e confinadas ? pasta do produto, apontando para `target.yml`, `data-rules.yml` e `flows.yml`; ciclos, duplicidade, conflito, campos desconhecidos e caminhos inseguros s?o recusados. Nesta vers?o escolhas n?o mudam cobertura, ritmo ou permiss?es; P/H n?o s?o aplicadas. N?o persistir segredos, tokens, cookies, respostas, IDs ef?meros ou gabarito.

## Alternativas consideradas

Duplicar os arquivos na estrat?gia criaria conflito e autoridade amb?gua.

## Consequ?ncias

Origens externas s?o dados. Mudan?as de ambiente, contrato, conta, autoriza??o ou motor invalidam escolhas dependentes. Conhecimento execut?vel e reutiliza??o s?o V1.9.

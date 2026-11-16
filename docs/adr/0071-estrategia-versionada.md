# 0071. Estratégia versionada

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

O produto precisa registrar escolhas sem duplicar autorização ou estado transitório.

## Decisão

Vamos propor `strategy.yml` com `schema_version: 1`, `references` contendo `target`, `data_rules` e `flows`, e `choices` como lista. Nesta versão `choices` aceita lista vazia ou uma única escolha tipada: `name: coverage`, `value: preserve`, `source: owner|contract|observation`, `reason: preserve_baseline`, `valid_until` data ISO e `state: proposed|validated|review_required`. Sem texto livre. A compilação exige estado `validated`, validade no instante informado e igualdade item a item com a referência; validate e diff podem mostrar pendência. Observação nunca concede permissão. Referências são relativas, sem componentes vazios, `.` ou `..`, barras invertidas, unidade, URL ou controles, e confinadas à pasta do produto, apontando para `target.yml`, `data-rules.yml` e `flows.yml`; ciclos, duplicidade, conflito, campos desconhecidos e caminhos inseguros são recusados. Nesta versão escolhas não mudam cobertura, ritmo ou permissões; P/H não são aplicadas. Não persistir segredos, tokens, cookies, respostas, IDs efêmeros ou gabarito.

## Alternativas consideradas

Duplicar os arquivos na estratégia criaria conflito e autoridade ambígua.

## Consequências

Origens externas são dados. Mudanças de ambiente, contrato, conta, autorização ou motor invalidam escolhas dependentes. Conhecimento executável e reutilização são V1.9.

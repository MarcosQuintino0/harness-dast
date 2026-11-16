# 0071. Estratégia versionada

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

O produto precisa registrar escolhas sem duplicar autorização ou estado transitório.

## Decisão

Vamos propor `strategy.yml` com `schema_version: 1`, `references` contendo `target`, `data_rules` e `flows`, e `choices` como lista. Nesta versão `choices` aceita lista vazia ou uma única escolha tipada: `name: coverage`, `value: preserve`, `source: owner|contract|observation`, `reason: preserve_baseline`, `valid_until` data ISO e `state: proposed|validated|review_required`. Sem texto livre. A escolha pode incluir `basis`, com SHA-256 tipado para `environment`, `authorization`, `accounts`, `planning`, `openapi`, `data_rules`, `flows` e `engine`. Para compilar é necessário estado `validated`, validade em UTC e vínculo completo igual ao contexto atual. Atualmente o motor efetivo não está disponível nesse caminho: qualquer escolha preenchida fica pendente e é recusada na compilação e execução; `choices: []` continua operacional. `validate` e `diff` mostram pendência, sem conceder aprovação. Observação nunca concede permissão. Referências são relativas, sem componentes vazios, `.` ou `..`, barras invertidas, unidade, URL ou controles, e confinadas à pasta do produto, apontando para `target.yml`, `data-rules.yml` e `flows.yml`; ciclos, duplicidade, conflito, campos desconhecidos e caminhos inseguros são recusados. Nesta versão escolhas não mudam cobertura, ritmo ou permissões; P/H não são aplicadas. Não persistir segredos, tokens, cookies, respostas, IDs efêmeros ou gabarito.

## Alternativas consideradas

Duplicar os arquivos na estratégia criaria conflito e autoridade ambígua.

## Consequências

Origens externas são dados. A base vincula as fontes relevantes; testes de domínio verificam alterações relevantes e estabilidade diante de mudanças de limpeza. Reutilização e invalidação seletiva V1.9 não foram demonstradas. Conhecimento executável e reutilização são V1.9.

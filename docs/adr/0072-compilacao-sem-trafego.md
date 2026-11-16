# 0072. Compila??o e pr?via sem tr?fego

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

O plano deve mostrar o trabalho antes de qualquer pedido ao alvo.

## Decis?o

Vamos oferecer `hdast strategy validate <produto>`, `hdast strategy diff <produto>` e `hdast plan <produto> --dry-run`. Eles validam e compilam sem rede, sem exigir aprova??o para pr?via. A execu??o usa snapshot imut?vel e revalida autoriza??o, aprova??o, janela, prazo e stop em cada concess?o. A pr?via usa fontes locais e identifica a matriz prevista e entradas simb?licas; n?o afirma cobertura executada. O plano concreto depende do planejamento do scan. A matriz de opera??es, contas, regras, for?a, pontos e pr?-condi??es ? comparada item por item; hash n?o substitui essa prova. As op??es novas n?o alteram ritmo ou cobertura.

## Alternativas consideradas

Compilar a cada envio permitiria altera??o concorrente em disco; usar somente hash n?o prova equival?ncia.

## Consequ?ncias

A sa?da usa envelope JSON v1 existente. Sucesso: `{"schema_version":1,"ok":true,"data":{...}}`, sa?da 0. Configura??o inv?lida: `{"schema_version":1,"ok":false,"error":{"code":"CONFIG_ERROR","message":"Configura??o inv?lida."}}`, sa?da 2. Escopo ou aprova??o recusados na execu??o usam `SCOPE_VIOLATION` ou `SCOPE_NOT_APPROVED`, sa?da 3. Diff mostra campos e classe sem ecoar valores sens?veis; nomes detalhados de `data` ser?o fixados com a implementa??o.

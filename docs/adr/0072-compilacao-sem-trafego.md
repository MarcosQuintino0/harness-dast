# 0072. Compilação e prévia sem tráfego

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

O plano deve mostrar o trabalho antes de qualquer pedido ao alvo.

## Decisão

Vamos oferecer `hdast strategy validate <produto>`, `hdast strategy diff <produto>` e `hdast plan <produto> --dry-run`. Eles validam e compilam sem rede, sem exigir aprovação para prévia. A intenção é usar snapshot imutável e revalidar autorização, aprovação, janela, prazo e stop em cada concessão; isso é requisito de aceite, não uma garantia já demonstrada pela prévia. A prévia usa fontes locais e identifica a matriz prevista e entradas simbólicas; não afirma cobertura executada. O plano concreto depende do planejamento do scan. A matriz de operações, contas, regras, força, pontos e pré-condições é comparada item por item; hash não substitui essa prova. As opções novas não alteram ritmo ou cobertura.

## Alternativas consideradas

Compilar a cada envio permitiria alteração concorrente em disco; usar somente hash não prova equivalência.

## Consequências

A saída usa envelope JSON v1 existente. Sucesso: `{"schema_version":1,"ok":true,"data":{...}}`, saída 0. Configuração inválida: `{"schema_version":1,"ok":false,"error":{"code":"CONFIG_ERROR","message":"Configuração inválida."}}`, saída 2. Escopo ou aprovação recusados na execução usam `SCOPE_VIOLATION` ou `SCOPE_NOT_APPROVED`, saída 3. Diff mostra campos e classe sem ecoar valores sensíveis; nomes detalhados de `data` serão fixados com a implementação.

## Contrato proposto da resposta

Os comandos usam o envelope JSON v1 e aceitam `--products-dir`. Em sucesso, `strategy validate` devolve em `data` os campos `product`, `strategy_present`, `strategy_state`, `approval_state` e `envelope` (com `product`, `approval_digest`, `requests_per_second`, `max_duration_minutes` e `zap_threads_per_host`). `strategy diff` acrescenta `changes` e `classification`. A prévia ainda depende de implementação e sua estrutura será conferida antes da entrega.

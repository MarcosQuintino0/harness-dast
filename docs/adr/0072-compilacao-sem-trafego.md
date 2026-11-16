# 0072. Compilação e prévia sem tráfego

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

O plano deve mostrar o trabalho antes de qualquer pedido ao alvo.

## Decisão

Vamos oferecer `hdast strategy validate <produto>`, `hdast strategy diff <produto>` e `hdast plan <produto> --dry-run`. Eles validam e compilam sem rede, sem exigir aprovação para prévia. A intenção é revalidar autorização, aprovação, janela, prazo e stop em cada concessão; isso permanece requisito de aceite. A revalidação nos pontos de polling e envio do scan foi testada; revalidação por concessão do proxy não foi comprovada e é limite desta entrega. A prévia usa fontes locais e identifica a matriz prevista e entradas simbólicas; não afirma cobertura executada. O plano concreto depende do planejamento do scan. A matriz de operações, contas, regras, força, pontos e pré-condições é comparada item por item; hash não substitui essa prova. As opções novas não alteram ritmo ou cobertura.

## Alternativas consideradas

Compilar a cada envio permitiria alteração concorrente em disco; usar somente hash não prova equivalência.

## Consequências

A saída usa envelope JSON v1 existente. Sucesso: `{"schema_version":1,"ok":true,"data":{...}}`, saída 0. Configuração inválida: `{"schema_version":1,"ok":false,"error":{"code":"CONFIG_ERROR","message":"Configuração inválida."}}`, saída 2. Escopo ou aprovação recusados na execução usam `SCOPE_VIOLATION` ou `SCOPE_NOT_APPROVED`, saída 3. Diff mostra campos e classe sem ecoar valores sensíveis; nomes detalhados de `data` serão fixados com a implementação.

## Contrato proposto da resposta

Os comandos usam o envelope JSON v1 e aceitam `--products-dir`. Em sucesso, `strategy validate` devolve em `data` os campos `product`, `strategy_present`, `strategy_state`, `approval_state` e `envelope` (com `product`, `approval_digest`, `scope`, `path_mode`, `authorization_valid_until`, `windows`, `requests_per_second`, `max_duration_minutes` e `zap_threads_per_host`). `strategy diff` acrescenta `changes` e `classification`. `plan --dry-run` acrescenta `preview` e `executed: false`. A prévia contém `operations`, `strength`, `disabled_rules`, `rules`, `injectable_mask` e `coverage`; cada operação expõe `operation_id`, `method`, `path`, `account`, `probe_decision`, `depends_on`, `entries`, `body_entries_complete: false`, `scope_check: template_only` e `scan_status: pending_probe_and_zap`. O catálogo de regras e a cobertura real dependem do ZAP e do probe; entradas do corpo são incompletas. O diff é estrutural em relação ao legado, não comprova igualdade de cobertura item a item.

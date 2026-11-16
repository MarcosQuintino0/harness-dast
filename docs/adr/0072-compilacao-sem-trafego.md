# 0072. Compilação e prévia sem tráfego

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

O plano deve mostrar o trabalho antes de qualquer pedido ao alvo.

## Decisão

`hdast strategy validate <produto>`, `hdast strategy diff <produto>` e `hdast plan <produto> --dry-run` validam e compilam sem rede, sem exigir aprovação para prévia. Na pilha gerenciada, a aprovação e o perfil vinculados, a autorização, a janela, o prazo e a parada são revalidados por concessão; a prova real da coordenação observou recusa após revogação. A reprodução independente está em andamento. A prévia usa fontes locais e identifica a matriz prevista e entradas simbólicas; não afirma cobertura executada. O plano concreto depende do planejamento do scan. A equivalência da matriz de operações, contas, regras, força, pontos e pré-condições é critério de prova item por item; hash não substitui essa prova. As opções novas não alteram ritmo ou cobertura.

## Fronteiras e integração

As portas `StrategyStore` e `StrategyDependencyStore` ficam em `application/ports.py`, pois o armazenamento de arquivos é uma fronteira externa e os testes usam implementações em memória. `FileStrategyRepository` traduz essa fronteira; validação, hashes e comparação permanecem no domínio. Não há dependência nova.

A integração preserva o orquestrador existente em `application/scan.py`, já maior que 300 linhas, por um hook localizado. Mantém no mesmo ciclo as etapas de configuração, execução e limpeza do Replacer; evita refatorar simultaneamente o executor reservado à V1.7. Os modelos e a compilação ficam em módulos novos.

## Complemento implementado: identidade do motor na execução

Contrato implementado na V1.8:

- As consultas secas permanecem sem rede e não inventam a identidade do motor. Uma escolha preenchida pode continuar recusada na compilação seca por esse motivo.
- A abertura de transporte e a subida da pilha usam o perfil formal aprovado; construir os clientes não envia pedido ao alvo. Nenhuma dessas etapas aplica a escolha de estratégia.
- Antes do primeiro pedido ao alvo, os casos de uso ativos de preflight, probe, scan, authz, negative e run recebem `StrategyProfiles` com a porta do ZAP efetivamente configurado. Somente uma escolha preenchida provoca consulta da versão, limitada a texto imprimível não vazio de até 100 caracteres. Versão ausente, inválida, indisponível ou divergente recusa a execução, sem ecoar a resposta.
- A base vem do perfil e dos documentos atuais e da versão observada, nunca da versão declarada pela estratégia ou de execução antiga. O snapshot concreto do scan recebe a base verificada. A estratégia ausente ou vazia mantém o comportamento e não provoca consulta adicional.
- A composição mantém o controle e o scanner ligados ao mesmo endpoint configurado; a verificação existente do contexto continua necessária. A versão não prova identidade criptográfica ou de instância nem impede reinício ou alteração depois da conferência. A revalidação por concessão protege as fontes vinculadas, mas não resolve essa limitação do motor; raízes montadas devem permanecer estáveis e concessões já enviadas não são canceladas.
- Os modos `--dry-run` não recebem provedor de rede. Cleanup sem identidade efetiva continua recusando uma escolha preenchida; não ganha atalho de aprovação ou permissão.

## Alternativas consideradas

Compilar a cada envio permitiria alteração concorrente em disco; usar somente hash não prova equivalência.

## Consequências

A saída usa envelope JSON v1 existente. Sucesso: `{"schema_version":1,"ok":true,"data":{...}}`, saída 0. Configuração inválida: `{"schema_version":1,"ok":false,"error":{"code":"CONFIG_ERROR","message":"Configuração inválida."}}`, saída 2. Escopo ou aprovação recusados na execução usam `SCOPE_VIOLATION` ou `SCOPE_NOT_APPROVED`, saída 3. Diff mostra campos e classe sem ecoar valores sensíveis; os campos de `data` estão descritos abaixo.

## Contrato da resposta

Os comandos usam o envelope JSON v1 e aceitam `--products-dir`. Em sucesso, `strategy validate` devolve em `data` os campos `product`, `strategy_present`, `strategy_state`, `approval_state` e `envelope` (com `product`, `approval_digest`, `scope`, `path_mode`, `authorization_valid_until`, `windows`, `requests_per_second`, `max_duration_minutes` e `zap_threads_per_host`). `strategy diff` acrescenta `changes` e `classification`. `plan --dry-run` acrescenta `preview` e `executed: false`. A prévia contém `operations`, `strength`, `disabled_rules`, `rules`, `injectable_mask` e `coverage`; cada operação expõe `operation_id`, `method`, `path`, `account`, `probe_decision`, `depends_on`, `entries`, `body_entries_complete: false`, `scope_check: template_only` e `scan_status: pending_probe_and_zap`. O catálogo de regras e a cobertura real dependem do ZAP e do probe; entradas do corpo são incompletas. O diff é estrutural em relação ao legado, não comprova igualdade de cobertura item a item.

Com escolha preenchida, `validate` e `diff` exibem `strategy_state: review_required`, `basis_status: engine_unavailable` e `basis_context`, cujos resumos SHA-256 identificam ambiente, autorização, contas, planejamento, OpenAPI, regras de dados e fluxos; `engine` é `null`. Como não há vínculo completo do motor na consulta seca, a prévia com escolha preenchida falha fechada. Na execução ativa o vínculo é comparado com a versão observada do ZAP e as fontes atuais, conforme o complemento acima; divergência ou indisponibilidade impede pedidos ao alvo. A estratégia neutra `choices: []` não consulta o motor adicionalmente.

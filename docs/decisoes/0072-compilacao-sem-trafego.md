# 0072. Compilação e prévia sem tráfego

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

O plano deve mostrar o trabalho antes de qualquer pedido ao alvo.

## Decisão

`hdast strategy validate <produto>`, `hdast strategy diff <produto>` e `hdast plan <produto> --dry-run` validam e compilam sem rede, sem exigir aprovação para prévia. Na pilha gerenciada, a aprovação e o perfil vinculados, a autorização, a janela, o prazo e a parada são revalidados por concessão; a prova real da coordenação observou recusa após revogação. A reprodução independente passou em cinco testes; veja o [parecer de fechamento](../arquivo/reviews/2026-11-16-v1-8-validacao-fechamento.md). A prévia usa fontes locais e identifica a matriz prevista e entradas simbólicas; não afirma cobertura executada. O plano concreto depende do planejamento do scan. A equivalência da matriz de operações, contas, regras, força, pontos e pré-condições é critério de prova item por item; hash não substitui essa prova. As opções novas não alteram ritmo ou cobertura.

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

## Rodada 3: vigia de fontes

O dono autorizou substituir leitura e hash síncronos em cada concessão após prova do custo. A conferência segura apenas de metadados teve mediana 1,6170575 ms, p95 3,726572 ms e mínimo 1,140926 ms, acima da meta de 1 ms. O commit `59078a1` implementou inicialização síncrona e vigia que calcula hashes completos e verifica o arquivo de parada; após cada verificação espera 50 ms antes de iniciar outra. A concessão consulta o estado publicado sob trava, sem E/S de arquivo; estado com mais de 200 ms desde o início da última verificação bem-sucedida, erro, ausência ou encerramento trava a recusa. Autorização, janela e prazo continuam verificados por concessão. A idade máxima aceita não garante descoberta de alteração em prazo rígido pelo sistema operacional ou sistema de arquivos; concessões já encaminhadas não são canceladas.

No microbenchmark do contêiner, a mediana/p95 de `_detect` passaram de 5,7759215/6,389762 ms para 0,026176/0,042773 ms. A mediana posterior atende à meta de 1 ms nesse ensaio. Fontes e protocolo estão na [rodada 3](../arquivo/plans/2026-11-16-v1-8-rodada3.md); As T4 foram executadas e a promoção foi recusada por igualdade de contagem inconclusiva; a reprodução independente de T2 e revogação passou, com parecer global corrigir por lacuna de equivalência. A descrição anterior neste ADR registra o mecanismo prévio, substituído nesta rodada.

A [revogação da rodada 3](../../evals/measurements/v1-8/round3/revocation-vampi.json) passou na coordenação: concessão, recusa `approval_changed` e nenhuma concessão posterior. Os 1,031 s observados incluem espera de taxa e não são garantia de latência; a reprodução independente passou, com parecer corrigir por lacuna de equivalência.

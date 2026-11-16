# Coordenação V1.7 — decisões anteriores às medições

Data: 2026-11-16. Branch de integração: `feat/v1-7-velocidade`; base `24ec850` (V1.5.5 integrada em `5f4b321`). Esta execução não autoriza produto real, não toca `C:\harness-dast` e não realiza rodada cega.

- Meta prévia: redução mediana mínima de 15% **por API** no scan T3, com qualidade eliminatória. Três pares alternados; ampliar a cinco somente conforme critério prévio do plano. Sem comparação suficiente, padrão A (`legacy`).
- A/B: política, força, contas, regras, limites e operações iguais; B (`proxy`) muda apenas atraso fixo do ZAP, sob limitador global do proxy. Ambos usam o proxy corrigido/instrumentado desta branch; a diferença entre versão anterior e nova cerca não deve ser atribuída a B.
- V1.5.5 não possui completas nem referência cega comparável no relatório versionado. A desta execução é referência experimental; não é referência cega. T4 precisa A e B por API para confirmar ganho relativo. Aumento prévio autorizado pelo plano corrigido: até 50 minutos adicionais; teto estimado total 3h10 de laboratório, com custos e eventuais estouros reportados.
- Seleção por tecnologia é opcional; contrato preparatório pode ser entregue com proveniência e nova aprovação, mas todas as regras continuam ativas. Declaração errada sem sinal não permite prometer equivalência. Decisão conservadora baseada no parecer independente incorporado à seção12.1, sem desativar proteção.
- CPU/memória devem identificar o processo/contêiner medido; `duration_ms` inclui transporte e processamento observado, não é rede pura. Esperas e tempos de regra sobrepostos não são somados ao tempo de parede. Ausente não é zero.
- T3 fixa estratos antes dos pares. Classes não comprovadas na A são lacunas de referência, não sucesso da B. T4 não escolhe rotas pelo gabarito.
- Programação: Terra6.1 high, worktrees exclusivas proxy/métricas, executor, declaração; QA independente Terra6.1 high em outra worktree. Documentação Terra6.1 high após integrar; crítico inicial e validador final Terra6.1 medium novos sem herdar conversa.
- Docker observado disponível: versão29.7.2, sem pilhas Compose. A trava externa ainda será adquirida exclusivamente antes da primeira integração; nenhum agente programador ou QA sobe pilha.
- O coordenador executa os gates finais, prova local e PR para `develop`; PR não será mesclado. CI ausente em PRs anteriores exige gates locais documentados.

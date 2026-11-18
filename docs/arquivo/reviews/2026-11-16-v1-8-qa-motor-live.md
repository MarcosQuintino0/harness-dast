# Complemento de QA: motor observado na execução

Data: 2026-11-16. Este complemento registra a revisão da fatia LIVE posterior aos pareceres anteriores, que permanecem imutáveis. Não usei Docker nem um alvo de laboratório.

O `probe` real com perfil aprovado e colaboradores falsos consultou a versão do motor antes do primeiro pedido ao alvo. Com vínculo íntegro, enviou ao alvo falso; com versão divergente, documento divergente, motor indisponível ou versão malformada, recusou sem enviar pedido. Uma versão malformada com marcador sensível não foi repetida no erro. Estratégia ausente e `choices: []` produziram os mesmos resultados, pedidos e quantidade de consultas de versão.

O `scan` com falsos executou com vínculo íntegro e recusou documento divergente antes de pedido ao alvo ou início de job. Quatro testes de contrato existentes de `--dry-run` para probe, scan, authz e negative passaram. A inspeção de composição verificou o provedor ZAP nos casos ativos e sua ausência nesses quatro modos secos; a abertura de transporte e a pilha usam perfil formal, enquanto cleanup sem provedor permanece conservador. Essa inspeção não é uma prova ponta a ponta individual de cada etapa nem de infraestrutura real.

Passaram 51 testes independentes de estratégia, CLI, skill e cópia cega, mais os quatro testes de modos secos. `ruff check` dos testes alterados e `mypy` para Windows e Linux passaram. A coordenação executa os gates finais na árvore integrada.

**A decisão de corrigir permanece.** A versão observada e o contexto do ZAP não provam identidade estável da instância depois da consulta; uma troca ou reinício posterior segue sem prova. A aprovação é revalidada antes de jobs e nos polls, mas não foi demonstrada em cada concessão de saída do proxy. Este complemento também não prova cobertura executada ou detecção nas duas APIs.

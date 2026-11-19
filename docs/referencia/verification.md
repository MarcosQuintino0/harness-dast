# Verificação de achados

A V1.11 acrescenta uma verificação consultiva ao resultado da execução. Ela não altera achados, status ou severidade e não substitui a análise de uma pessoa. A implementação está integrada; a calibração e a prova operacional no laboratório ainda estão pendentes.

## Uso e interpretação

Consulte a sintaxe e as condições de [hdast confirm](cli.md#hdast-confirm). O envelope de sucesso JSON traz `data.verification`, `data.recipe_requests` e `data.session_requests`. A seleção por fingerprint é opcional; `--max` aceita de 1 a 30 e limita a seleção por severidade. Os resultados não selecionados são preservados em `verification.json` v1, identificado por produto, execução e fingerprint.

| Nível | Interpretação |
| --- | --- |
| `reproduced` | A comparação implementada encontrou o efeito previsto; a regra e seus limites dependem da receita. |
| `likely` | Há indício na evidência guardada, sem reprodução pela receita. |
| `inconclusive` | A comparação não permite concluir; não refuta o alerta. |
| `likely_false_positive` | Uma propriedade específica registrada contraria o alerta; não presume que respostas iguais provem falsidade. |
| `not_verifiable` | Faltam condições ou prova suficientes para a verificação disponível. |

São categorias com motivo, não probabilidades. O painel e os relatórios apresentam verificação e confirmação humana separadamente, com resumos redigidos de ataque e controle quando disponíveis. A lista de casos que precisam de pessoa inclui os inconclusivos e os de severidade alta sem reprodução. A redação por padrões e segredos conhecidos não garante eliminar segredos desconhecidos.

## O que é repetido

As receitas de tráfego exigem GET já varrido, semente de sucesso 2xx e um parâmetro de consulta com nome inequívoco, além de perfil aprovado, pilha atual e controles de escopo, janela, prazo, taxa e parada. O recibo `ScanEntry.seed_binding` vincula operação, método, URL integral e conta efetivamente usados pelo scanner; ambiente e conta atuais precisam corresponder. Execuções antigas sem recibo ficam não verificáveis, sem tráfego nem prova retroativa. A implementação recusa escrita e `DELETE`. Não reutiliza livremente URL ou carga do alerta. O limite é de 12 pedidos totais por achado, incluindo login, CSRF, recuos e receita; sessão e receita são contadas separadamente.

As receitas atuais cobrem SQL booleano, atraso específico de PostgreSQL, reflexão de marcador em HTML e erro interno detalhado, com controles. Reflexão HTML não prova execução de JavaScript. Travessia fica não verificável sem oráculo benigno. Cabeçalhos e CORS usam observação direta guardada, sem pedido novo: `reproduced` descreve somente a propriedade comprovada, e resposta JSON não prova falha de interface HTML. As técnicas de autorização usam os campos e registros da comparação anterior; escritas sem leitura posterior suficiente não provam alteração. Casos incompletos ficam não verificáveis com motivo.

A prova de ataque e controle guarda método, receita, digest do alvo, status, duração, tamanho e digest curto dos corpos, inclusive na interrupção. Permite comparar igualdade, sem inspecionar o conteúdo integral; respostas de baixa entropia podem ser adivinháveis. A causa e o código de uma parada são preservados após gravar o resultado parcial.

## Declaração humana e calibração

Uma pessoa pode registrar sua observação pelo procedimento [finding acknowledge](cli.md#hdast-finding-acknowledge). O agente não executa o comando nem escreve `human-confirmations.json`. A interação exige TTY e confirmação digitada, mas não autentica identidade ou veracidade.

A [calibração](verification-calibration.md) está bloqueada, sem medições. Contagem e tamanho da amostra aparecem quando medidos; porcentagem só com pelo menos 10. Nenhuma taxa deve ser inferida de testes offline. Os ADRs 0085 a 0091 permanecem propostos; o [índice](../decisoes/README.md#todas-as-decisões) reúne os contratos.

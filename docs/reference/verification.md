# Verificação de achados

A V1.11 acrescenta uma verificação consultiva ao resultado da execução. Ela não altera achados, status ou severidade e não substitui a análise de uma pessoa. A implementação está integrada; a calibração e a prova operacional no laboratório ainda estão pendentes.

## Uso e interpretação

Consulte a sintaxe e as condições de [hdast confirm](cli.md#hdast-confirm). O envelope de sucesso JSON traz `data.verification`, `data.recipe_requests` e `data.session_requests`. A seleção por fingerprint é opcional; `--max` aceita de 1 a 30 e limita a seleção por severidade. Os resultados não selecionados são preservados em `verification.json` v1, identificado por produto, execução e fingerprint.

| Nível | Interpretação |
| --- | --- |
| `reproduced` | A comparação implementada encontrou o efeito previsto; a regra e seus limites dependem da receita. |
| `likely` | Há indício na evidência guardada, sem reprodução pela receita. |
| `inconclusive` | A comparação não permite concluir; não refuta o alerta. |
| `likely_false_positive` | Categoria prevista pelo contrato; não presume que respostas iguais provem falsidade. |
| `not_verifiable` | Faltam condições ou prova suficientes para a verificação disponível. |

São categorias com motivo, não probabilidades. O painel e os relatórios apresentam verificação e confirmação humana separadamente, com resumos redigidos de ataque e controle quando disponíveis. A lista de casos que precisam de pessoa inclui os inconclusivos e os de severidade alta sem reprodução. A redação por padrões e segredos conhecidos não garante eliminar segredos desconhecidos.

## O que é repetido

As receitas de tráfego exigem GET já varrido, semente de sucesso 2xx e um parâmetro de consulta com nome inequívoco, além de perfil aprovado, pilha atual e controles de escopo, janela, prazo, taxa e parada. A implementação recusa escrita e `DELETE`. Não reutiliza livremente URL ou carga do alerta. O limite é de 12 pedidos de receita por achado; pedidos de sessão são contados separadamente e sujeitos aos controles existentes.

As receitas atuais cobrem SQL booleano, atraso específico de PostgreSQL, reflexão de marcador em HTML e erro interno detalhado, com controles. Reflexão HTML não prova execução de JavaScript. Travessia fica não verificável sem oráculo benigno. Para cabeçalhos e CORS, usa-se a classificação da evidência guardada, sem pedido novo; isso não demonstra reprodução. Para autorização, apenas `authz_horizontal` e `authz_vertical`, com contas distintas e os dois estados registrados 2xx, recebem `reproduced` pela comparação guardada; os demais casos sem esses elementos ficam não verificáveis.

## Declaração humana e calibração

Uma pessoa pode registrar sua observação pelo procedimento [finding acknowledge](cli.md#hdast-finding-acknowledge). O agente não executa o comando nem escreve `human-confirmations.json`. A interação exige TTY e confirmação digitada, mas não autentica identidade ou veracidade.

A [calibração](verification-calibration.md) está bloqueada, sem medições. Quando houver dados, uma porcentagem só pode aparecer com amostra de pelo menos 10 e com numerador e denominador; nenhuma taxa deve ser inferida de testes offline. Os ADRs [0085](../adr/0085-verificacao-de-achados.md), [0086](../adr/0086-confirmacao-humana-de-achados.md), [0087](../adr/0087-reproducao-controlada-de-achados.md) e [0088](../adr/0088-apresentacao-e-calibracao-de-verificacao.md) permanecem propostos.

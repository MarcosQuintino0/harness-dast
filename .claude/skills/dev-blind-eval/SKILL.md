---
name: dev-blind-eval
description: "Use ao desenvolver o harness-dast para preparar e registrar uma rodada cega sem contaminar o agente avaliado. Não use para testar um produto."
---

# Conduzir avaliação cega

1. Leia [evals/README](../../../evals/README.md) e o [protocolo](../../../evals/protocolo-da-rodada-cega.md).
   Respeite o briefing e a trava do laboratório; este roteiro não autoriza uma rodada por si só.
2. Prepare uma cópia por lista de permissão. Confira o manifesto de raízes/contagens e a varredura de vazamentos.
   Não entregue `dev-*`, resultados, pesquisa, histórico, gabaritos nem conversa do coordenador ao agente avaliado.
3. Lance um processo novo, sem contexto, com o pedido padronizado do protocolo. Segredos ficam no lacre;
   o agente recebe apenas nomes e as entradas autorizadas. Não dê dicas nem responda além do previsto.
4. Colete transcript e intervenções, nota, medidas, versão/commit e manifesto. Registre limites de comparação histórica.
5. Siga a retenção de evals e registre a prova em `docs/arquivo/reviews/`, sem alterar casos ou resultados de rodadas em andamento.

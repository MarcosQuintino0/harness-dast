---
name: dev-close-version
description: "Use ao desenvolver o harness-dast para conferir os aceites e fechar uma versão. Não use para testar um produto."
---

# Fechar uma versão

1. Leia o plano da versão e seu estado no [roadmap](../../../docs/roadmap.md).
   Confira cada aceite com prova existente, lacunas e os critérios da [Parte A do AGENTS.md](../../../AGENTS.md#parte-a-ao-desenvolver-o-projeto).
2. Siga a [escada](../../../docs/desenvolver/escada-de-testes.md): varredura completa e rodada cega pertencem a este fechamento.
   Use `dev-lab-check` e `dev-blind-eval`; respeite a trava e o briefing. Sem autorização para esses degraus, registre pendência.
3. Registre provas e limites num relatório novo em `docs/arquivo/reviews/`; não reescreva relatórios datados.
4. Atualize roadmap e CHANGELOG e alinhe o carimbo de `pyproject.toml` e `uv.lock` à publicação decidida pelo dono.
   Até o fechamento, as mudanças ficam em `Unreleased`. Aceitar ADR é decisão humana; confira os estados no [índice](../../../docs/decisoes/README.md).
5. Rode os seis gates da Parte A de [AGENTS](../../../AGENTS.md), relate números e provas ausentes.
   Git e publicação seguem a autorização recebida; fechamento não autoriza push ou merge por si só.

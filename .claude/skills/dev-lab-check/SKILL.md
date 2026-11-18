---
name: dev-lab-check
description: "Use ao desenvolver o harness-dast para provar uma mudança de forma dirigida nos alvos do laboratório. Não use para testar um produto."
---

# Conferir no laboratório

1. Leia a [escada](../../../docs/desenvolver/escada-de-testes.md), [lab](../../../lab/README.md)
   e o plano da versão. Use apenas Clínica Piloto, VAmPI ou crAPI em contêineres com dados sintéticos, no computador local ou em máquinas efêmeras do GitHub, segundo o [ADR 0118](../../../docs/decisoes/0118-laboratorio-em-maquinas-efemeras-do-github.md).
2. Respeite a trava exclusiva conforme o plano vigente. No computador local, use `C:\harness-dast-artefatos\lab.lock`. Em máquina efêmera, use um caminho temporário exclusivo da máquina.
   Se ocupada, não toque em pilhas ou imagens e registre o bloqueio; não remova a trava de outra sessão.
3. Use pilhas com sufixo próprio e pastas de produtos/estado isoladas. Confira as imagens antes da prova;
   código do proxy/Docker alterado exige reconstrução e conferência segundo a escada.
4. Selecione poucas operações afetadas. Envie tráfego só por comandos `hdast`, sob as regras da Parte B de [AGENTS](../../../AGENTS.md).
   Não leia segredos, não aprove escopo e não execute limpeza humana; a carta e a aprovação continuam obrigatórias.
5. Registre versão das imagens, comandos, resultado vulnerável/seguro e limites em `docs/arquivo/reviews/AAAA-MM-DD-*.md`.
   Encerre apenas a própria pilha. Varredura completa só no fechamento.

---
name: dev-lab-check
description: "Use ao desenvolver o harness-dast para provar uma mudança de forma dirigida no laboratório local. Não use para testar um produto."
---

# Conferir no laboratório

1. Leia a [escada](../../../docs/escada-de-testes.md), [lab](../../../lab/README.md)
   e o plano da versão. Use apenas Clínica Piloto, VAmPI ou crAPI locais, nunca produto real.
2. Respeite a trava exclusiva `C:\harness-dast-artefatos\lab.lock` conforme o plano vigente.
   Se ocupada, não toque em pilhas ou imagens e registre o bloqueio; não remova a trava de outra sessão.
3. Use pilhas com sufixo próprio e pastas de produtos/estado isoladas. Confira as imagens antes da prova;
   código do proxy/Docker alterado exige reconstrução e conferência segundo a escada.
4. Selecione poucas operações afetadas. Envie tráfego só por comandos `hdast`, sob as regras da Parte B de [AGENTS](../../../AGENTS.md).
   Não leia segredos, não aprove escopo e não execute limpeza humana; a carta e a aprovação continuam obrigatórias.
5. Registre versão das imagens, comandos, resultado vulnerável/seguro e limites em `docs/reviews/AAAA-MM-DD-*.md`.
   Encerre apenas a própria pilha. Varredura completa só no fechamento.

---
name: dev-write-adr
description: "Use ao desenvolver o harness-dast para registrar uma decisão arquitetural ou mudança de contrato. Não use para testar um produto."
---

# Escrever um ADR

1. Consulte a [Parte A do AGENTS.md](../../../AGENTS.md#dependências-e-adr). Dependência, porta,
   contrato ou fronteira nova e mudanças de rumo descobertas em um spike exigem ADR.
2. Confira o maior número existente, reserve o próximo sem reutilizar números e use o [template](../../../docs/decisoes/template.md).
3. Escreva contexto, decisão proposta, alternativas, consequências e aceites verificáveis.
   Atualize o [índice](../../../docs/decisoes/README.md) e a documentação afetada.
4. Abra o ADR como `Proposto`. O dono decide o aceite, registrado como `Aceito` na `main`.
   ADR aceito é imutável. Registre mudanças de rumo em um novo ADR com link para a decisão que ele substitui.

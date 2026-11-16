# 0070. Envelope autorizado

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

A estratégia precisa ser delimitada pelo perfil aprovado.

## Decisão

Vamos derivar um envelope imutável do perfil validado, mantendo a impressão digital protegida existente. A aprovação humana é conferida separadamente na execução; ausência ou alteração impede envio. A validação e prévia são sem tráfego e não exigem aprovação. Nenhum dado observado, estratégia ou migração concede autorização. Campos de escopo, identidade, limites e políticas permanecem protegidos pelo fingerprint vigente.

## Alternativas consideradas

Um envelope preenchido pelo agente duplicaria e poderia ampliar a autorização; foi descartado.

## Consequências

Mudanças protegidas continuam exigindo aprovação humana; alterações V1.7 devem ser reconciliadas sem invalidar silenciosamente aprovações antigas.

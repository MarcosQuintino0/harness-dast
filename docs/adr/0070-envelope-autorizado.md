# 0070. Envelope autorizado

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

A estrat?gia precisa ser delimitada pelo perfil aprovado.

## Decis?o

Vamos derivar um envelope imut?vel do perfil validado, mantendo a impress?o digital protegida existente. A aprova??o humana ? conferida separadamente na execu??o; aus?ncia ou altera??o impede envio. A valida??o e pr?via s?o sem tr?fego e n?o exigem aprova??o. Nenhum dado observado, estrat?gia ou migra??o concede autoriza??o. Campos de escopo, identidade, limites e pol?ticas permanecem protegidos pelo fingerprint vigente.

## Alternativas consideradas

Um envelope preenchido pelo agente duplicaria e poderia ampliar a autoriza??o; foi descartado.

## Consequ?ncias

Mudan?as protegidas continuam exigindo aprova??o humana; altera??es V1.7 devem ser reconciliadas sem invalidar silenciosamente aprova??es antigas.

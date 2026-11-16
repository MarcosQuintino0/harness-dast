# 0073. Aprova??o e classifica??o das altera??es

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

Aprova??o antiga n?o pode virar autoridade sobre par?metros novos.

## Decis?o

Vamos distinguir autom?tica (neutra e dentro do envelope), proposta pendente (interpreta??o, contrato ou cobertura) e decis?o humana (permiss?o, escopo, teto, janela ou pol?tica protegida). V1.8 aplica apenas escolhas neutras sem mudar cobertura ou ritmo; recusa novas permiss?es. A aprova??o continua sendo ato de pessoa pelo fluxo existente; validar ou compilar n?o aprova. Mudan?a protegida invalida aprova??o conforme o fingerprint vigente.

## Alternativas consideradas

Tratar toda mudan?a como autom?tica permitiria redu??o oculta de qualidade; exigir aprova??o para pr?via impediria inspe??o segura.

## Consequ?ncias

Diff identifica classe sem divulgar valores livres; proposta pendente n?o se torna execut?vel automaticamente. Testar mudan?a, revoga??o e corrida antes da concess?o.

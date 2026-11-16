# 0073. Aprovação e classificação das alterações

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

Aprovação antiga não pode virar autoridade sobre parâmetros novos.

## Decisão

Vamos distinguir automática (neutra e dentro do envelope), proposta pendente (interpretação, contrato ou cobertura) e decisão humana (permissão, escopo, teto, janela ou política protegida). V1.8 aplica apenas escolhas neutras sem mudar cobertura ou ritmo; recusa novas permissões. A aprovação continua sendo ato de pessoa pelo fluxo existente; validar ou compilar não aprova. Mudança protegida invalida aprovação conforme o fingerprint vigente.

## Alternativas consideradas

Tratar toda mudança como automática permitiria redução oculta de qualidade; exigir aprovação para prévia impediria inspeção segura.

## Consequências

Diff identifica classe sem divulgar valores livres; proposta pendente não se torna executável automaticamente. Testar mudança, revogação e corrida antes da concessão.

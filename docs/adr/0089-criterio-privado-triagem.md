# 0089. Critério privado de acerto da triagem

- **Status:** Proposto
- **Data:** 2026-11-17

## Contexto e decisão

A nota existente mede formato e cobertura da triagem, não se a classificação proposta está
correta. Acrescentar o critério privado `evals/rubrics/triage-accuracy-v1.md`, julgado pelo
coordenador contra o gabarito aplicável e o controle seguro, distinguindo acerto, erro,
indeterminado e não avaliado. O critério é separado da nota automática e das suas ponderações;
rodadas históricas não são recalculadas. Registrar versão, denominadores e limites.

A integração automática depende do contrato final de `verification.json` e de associação entre
artefatos da mesma execução. Não presumir equivalência de categorias a probabilidades nem
inventar resultados de calibração. O critério, gabarito e calibração detalhada não entram na
cópia cega. Este ADR também é excluído pela lista de permissão operacional.

## Alternativas e consequências

Mudar os pesos da nota agora invalidaria comparações e dependeria de contrato ainda pendente.
A avaliação manual exige revisão e ainda não fornece nota automática: é uma lacuna explícita.

# 0089. Critério privado de acerto da triagem

- **Status:** Proposto
- **Data:** 2026-11-17

## Contexto e decisão

A nota histórica mede formato e cobertura, não o acerto da classificação. O executor implementa
a régua privada `evals/rubrics/triage-accuracy-v1.md` como campo suplementar `triage_accuracy`
versão 1 em `score.json`. A fórmula, os componentes e os pesos permanecem iguais; rodadas
históricas não são reescritas. A decisão segue proposta, sujeita ao aceite do dono.

A medição associa execução e fingerprint, valida os arquivos e confronta com o Case. Usa
somente correspondências específicas e inequívocas. O modo seguro não basta para declarar
falso: a correção da falha precisa estar documentada. Sem essa base, sem artefato válido ou
com órfão, registra indeterminação ou impossibilidade com motivo. A classificação automática
da CLI e a anotação do agente são medidas separadamente. Os totais incluem denominadores;
nenhum nível é probabilidade e nenhuma calibração foi inventada. Não apresentar porcentagem
para amostras menores que dez; esta implementação não apresenta porcentagens.

A régua, o gabarito e a calibração detalhada não entram na cópia cega (ADR 0083).

## Alternativas e consequências

Mudar os pesos comprometeria a comparação histórica. A medição aditiva preserva a nota,
mas correspondências limitadas deixam casos indeterminados e exigem revisão da prova por uma
pessoa. A calibração com resultados reais continua pendente de execução autorizada no laboratório.

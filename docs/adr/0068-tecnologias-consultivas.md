# ADR 0068: declaração consultiva de tecnologias

Data: 2026-11-16. Estado: proposta.

## Contexto

Uma declaração errada pode não produzir sinal de contradição. Usá-la para excluir regras poderia esconder falhas sem que a ferramenta saiba; a crítica independente do plano V1.7 adia essa seleção.

## Decisão

`attack.technologies` é resposta opcional da carta. Uma lista preenchida exige `source: carta` e frase não vazia em `quote`; a CLI gera `technologies` com valor, origem e frase no perfil. Ausente, desconhecido ou lista vazia não gera campo e mantém a impressão digital e aprovação anteriores. A declaração preenchida e qualquer alteração nela entram na impressão digital e são mostradas na aprovação. A declaração não confirma a tecnologia nem reduz cobertura: todas as regras continuam ativas, independentemente do conteúdo. Nenhuma seleção ou tabela de exclusões é implementada.

## Consequências

O schema 1 recebe campo opcional aditivo; o resumo, entrevista, aviso e avaliação expressam seu caráter consultivo. Alteração requer nova aprovação. A exclusão efetiva demanda decisão e prova futuras; não se alega ganho ou equivalência de cobertura.

# A triagem acertou? — critério adicional V1.11

**Estado: implementado; ADR 0089 proposto.** O campo `triage_accuracy`, versão 1,
é suplementar à nota automática histórica: não altera grade, componentes nem pesos.
Não reescreva rodadas anteriores. Use a régua somente fora da cópia cega.

O executor lê `findings.json`, `triage.json` e `verification.json` na mesma pasta de
execução e valida versão, modelos, produto e execução quando disponíveis no contrato.
Cada observação pertence a uma execução e fingerprint; fingerprints repetidos em outras
execuções continuam observações distintas. Ausência, erro de leitura, modelo inválido,
contexto divergente e órfãos geram motivo e não contam como acerto. Uma anotação sem
`suspected_false_positive` explícito não classifica o achado.

A verdade usa `Matcher` e `matches` do Case: correspondência completa, específica por
operação ou caminho e classe, única e sem conflito parcial. Sem correspondência suficiente,
o resultado é **Indeterminado**, nunca falso conhecido. No modo seguro, somente falhas
H1–H10 da Clínica Piloto com gabarito correspondente ao caso original são elegíveis como
falsos conhecidos, pois o gabarito documenta a correção pelo botão desse modo. Outro caso,
alerta genérico ou gabarito alterado não permite inferir correção. Essa regra conservadora
não garante que todo alerta compatível expresse o mesmo comportamento: revise a prova.

A CLI (`reproduced` ou `likely` versus `likely_false_positive`) e o agente
(`suspected_false_positive`) são julgados separadamente como **Acertou**, **Errou**,
**Indeterminado** ou **Não avaliado**. `inconclusive` e `not_verifiable` são indeterminados.
A matriz agrupa por categoria, t?cnica ou t?tulo do alerta; a observa??o tamb?m identifica
a falha correspondente. Registra reais e falsos reproduzidos, falsos classificados FP, reais
classificados FP, resultados do agente, totais e denominador. Problemas de arquivo e órfãos
são listados à parte, pois não fornecem denominador de achados confiável. Não há porcentagens
nem probabilidades; nenhuma medição de laboratório foi inventada. A calibração efetiva e a
revisão da evidência continuam responsabilidades do coordenador.

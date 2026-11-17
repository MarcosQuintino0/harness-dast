# 0088. Apresentação e calibração da verificação

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** plano V1.11, fases D e E

## Contexto

A verificação é consultiva e não modifica os achados. Resultados automáticos e registros de pessoas têm origens distintas. Uma porcentagem sem medição ou amostra suficiente induz uma interpretação indevida.

## Decisão

Vamos apresentar a verificação, a confirmação humana e a calibração separadamente, sem mudar o contrato de `findings.json`. A leitura de calibração passa por porta e adaptador a partir de JSON versionado fora de `src/`. Só exibir porcentagens medidas para amostras de pelo menos 10, com tipo, numerador e denominador; não extrapolar para outros ambientes nem atribuir probabilidade aos níveis. Ausência de medição não é zero. Os registros são dados não confiáveis, redigidos e escapados na apresentação.

## Alternativas consideradas

Inserir resultados no contrato de achados misturaria dados originais e pareceres posteriores. Fixar números no código ou exibir porcentagens de amostras pequenas esconderia a origem e as limitações das medições.

## Consequências e aceites

O painel e ambos os relatórios devem manter o resultado automático separado da confirmação humana, validar identidade e fingerprints atuais e exibir as provas de forma redigida. O JSON inicial declara bloqueio e não contém medições. Testes de contrato cobrem dados ausentes, inválidos e amostras abaixo e no limiar. A medição no laboratório depende de aprovação humana e não é demonstrada por este ADR proposto.

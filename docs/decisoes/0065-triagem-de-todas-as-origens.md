# 0065. Conferência de triagem de todas as origens

- **Status:** Proposto
- **Data:** 2026-11-15

## Contexto

O relatório aceita anotações por fingerprint, mas calculava anotações órfãs somente contra os
alertas do ZAP. A conferência final das skills exige anotar cada achado alto, inclusive os
achados de autorização, de valores proibidos e de sinais da cerca. Essas anotações válidas
não podem ser apresentadas como órfãs para serem removidas.

## Decisão

As skills conferem a união dos fingerprints altos de todas as seções de `findings.json`
contra `triage.json` antes da entrega. O relatório reconhece os fingerprints das três origens
adicionais ao calcular `triage_orphans`; anotações sem achado em qualquer seção continuam
órfãs. O formato dos arquivos, as contagens e as severidades não mudam. Não há rede nem
comando novo. As anotações adicionais permanecem em `triage.json`; sua apresentação junto
a cada achado dessas seções ainda não é implementada.

## Consequências

A conferência deixa de orientar a remoção de notas válidas de outras origens. Continua
sendo uma conferência do agente, cobrada pelos contratos das skills e pela avaliação;
não há gate obrigatório de execução nem confirmação humana automática.

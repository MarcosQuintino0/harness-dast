# Calibração da verificação

**Estado: bloqueada por falta de aprovação humana para as execuções de laboratório.**

A matriz em `verification-calibration.json` ainda não tem medições. Nenhuma execução antiga foi usada como linha de base. Ausência de amostras não indica zero falsos positivos nem eficácia medida.

Quando houver prova autorizada, registre tipo de falha, critério medido, quantidade correta, tamanho da amostra e proveniência das execuções. Percentuais só podem ser apresentados a partir de dez amostras e descrevem apenas a medição no laboratório, sem extrapolação nem probabilidade atribuída aos níveis de verificação.

O JSON tem `schema_version`, `status`, `provenance` e `measurements`. Enquanto estiver
`blocked`, a lista de medições fica vazia. Depois de medida, `status` passa a `measured`
e cada entrada deve conter `finding_type`, `criterion`, `correct`, `sample` e
`provenance`: respectivamente, tipo, critério, quantidade correta, tamanho da amostra e
referência da prova. A quantidade correta não pode superar a amostra. O relatório omite
medições abaixo do limiar; dados ausentes ou inválidos não se tornam contagens zero.

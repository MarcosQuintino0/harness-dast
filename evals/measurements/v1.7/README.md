# Evidências V1.7 — laboratório local, 2026-11-16

Esta rodada é assistida e usa dados sintéticos. Não é avaliação cega nem prova em produto real. `legacy` permanece padrão; os ganhos são descritivos e o aceite de qualidade é parcial.

- [Pré-registro](preregistro.md), [matriz de controles](matriz-controles.md) e [decisões anteriores à prova](../v1.7-coordination/decisions.md).
- [Desempenho observado](performance-evidence.json): 28 registros T2/T3/T4, duração do scan, duração do comando, regras, recusas, tempos sobrepostos, CPU, memória e hashes dos originais.
- [Controles SQL e caminho](controls-targeted.json): 12 resultados direcionados, sem equivalência implícita para outras classes.
- [Matriz de qualidade](quality-evidence.md) e [dados da revisão independente](quality-evidence.json): critérios por API, modo e variante, com limitações de identidade, caminhos, regras e controles.
- [Limites condicionais de paralelismo](parallelizability-bound.json): intervalos iniciados em zero; não estimam a parcela real nem comprovam o limiar de 40% para V1.10.
- [Proveniência e tentativas](provenance.json): hashes dos logs originais, falhas, repetições e encerramento da reserva do coordenador.
- [Congelamento](forecast-freeze.json) e [previsão vazia](prediction-frozen.json): nenhuma previsão numérica qualificada; o B da Clínica foi executado antes do congelamento por erro de filtro, explicitamente preservado.
- [Gates anteriores ao laboratório](gates-prelab.json) e [primeiro par](checkpoint-first-pair.json) são checkpoints datados, não gates finais.
- [Gates finais](gates-final.json), [relatório da versão](../../../docs/reviews/relatorio-v1.7.md) e [validação independente](../../../docs/reviews/validacao-v1.7.md) fecham esta entrega parcial. Gates verdes não significam aceite da aceleração.

Os originais sanitizados e logs estão em `C:\harness-dast-artefatos\v1.7-velocidade`. Cada `v17-*.json` fica em `lab/`; a pasta `lab/lifecycle/` contém a verificação independente de contêineres apenas a partir de T4. Estado privado do suporte e arquivos de segredo não fazem parte da evidência pública. Os hashes vinculam os resumos aos originais; não comprovam, isoladamente, a hora de produção.

Reprodução da análise, sem tocar alvos:

```powershell
uv run python evals/measurements/v1.7/summarize.py C:\harness-dast-artefatos\v1.7-velocidade\lab --output C:\caminho\novo-resumo.json --prediction-output C:\caminho\nova-previsao.json --frozen-prediction evals/measurements/v1.7/prediction-frozen.json
```

Os destinos precisam ser novos. A saída conserva o resultado inconclusivo: DOM XSS 40026 ficou `skipped` por operação. Não altere o estimador, exclua a regra nem interprete falta de execução como zero para obter aceite. Consultas esparsas ao ZAP comprovam configuração somente nos instantes observados; `zap_delay_seconds: null` conserva a ausência de tempo efetivo medido. Picos de CPU e memória de contêineres são amostrais.

Incidentes preservados: uma T2 inicial parou no probe após 429/timeout, antes da correção do recuo; um preparo T3 VAmPI retornou 500 em `/createdb`, antes do scan, com causa desconhecida. Houve uma repetição em pilha nova após esse preparo; os resultados anteriores e o custo não foram apagados. O relatório da versão apresenta as consequências e os limites do aceite.

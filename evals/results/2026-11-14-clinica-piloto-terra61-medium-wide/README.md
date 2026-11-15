# Clínica Piloto: Terra 6.1 medium, modo amplo

O agente concluiu a varredura e a triagem **depois de receber assistência do coordenador**. A parte autônoma parou antes da varredura, seguindo a skill diante de erros persistentes de autenticação. Esse limite está preservado separadamente e continua sendo um resultado da avaliação.

Este estudo fornece uma referência anterior às melhorias da V1.7. **Não demonstra ganho de qualidade ou autonomia:** houve menos operações varridas que na avaliação cega da V1.1, além de diferenças de modelo, modo e intervenção.

## Resultado registrado

| Medida | Valor |
| --- | --- |
| Ambiente | Clínica Piloto local, dados sintéticos, modo vulnerável revelado somente após o agente terminar |
| Execução | 2026-11-14 no fuso de São Paulo; os registros UTC avançam para 2026-11-15 |
| Modelo / esforço | `gpt-6.1-terra` / `medium` |
| Código testado | `abc4f3aea945cd3edf7e90b64f945fc1971785a7`, versão declarada 1.5.0; não é o complemento atual da V1.5 |
| Modo de caminhos | `wide`, autorizado pelo dono do laboratório |
| Operações do contrato / elegíveis | 40 / 30 |
| Probe final | 18 sucessos em 23 pedidos enviados: 78,26%; 18/30 elegíveis: 60% |
| Operações varridas | 17/30 elegíveis: 56,67%; 17/40 do contrato: 42,5% |
| Achados / ocorrências | 71 / 74: 6 altos, 0 médios, 41 baixos, 24 informativos |
| Triagem | 71 anotações; 23 suspeitas de falso positivo, sem apagar ou rebaixar achados |
| Autorização entre contas | 64 pedidos, 8 tipos de verificação, 0 achados; BOLA horizontal e BFLA vertical ficaram sem cobertura efetiva |
| Nota automática | 6,17 no limite autônomo; 7,18 após assistência |
| Segurança do escopo | Avaliador sem violação; 0 pedidos liberados fora do escopo auditado |

Os 6 alertas altos não equivalem a 6 vulnerabilidades confirmadas. Dois sinais de erro SQL são mais fortes; quatro alertas temporais exigem validação adicional. O zero em autorização entre contas também não comprova ausência de falhas nas verificações que ficaram sem cobertura.

## Tempo e tokens

| Segmento | Tempo medido | Tokens, incluindo leitura de cache |
| --- | --- | --- |
| Tentativa 01, falha de infraestrutura | 3 min 42,319 s | 1.449.551 |
| Tentativa 02, parte autônoma | 6 min 37,279 s | 2.959.099 |
| Tentativa 02, continuação assistida | 15 min 59,282 s | 5.064.845 |
| Tentativa 02, tempo ativo somado | 22 min 36,561 s | 8.023.944 |
| Tentativa 02, pausa entre os segmentos | 7 min 0,139 s | Sem consumo adicional atribuído ao agente nessa pausa |
| Tentativa 02, relógio total | 29 min 36,700 s | Os mesmos 8.023.944; não somar novamente |
| Dois agentes independentes, somados | Tempos e preparação discriminados nos registros | 9.473.495 |

No agente principal: **108.900 tokens de entrada nova + 7.901.952 de leitura de cache + 13.092 de saída**. Os 529 tokens classificados como raciocínio são um subconjunto da saída. Tokens em cache continuam sendo tokens processados, mas não devem ser interpretados como entrada nova nem convertidos em custo financeiro sem as tarifas aplicáveis. Não foi medido o valor cobrado.

O coordenador tem uma fotografia **parcial** separada: 28.058.098 tokens até `2026-11-15T01:56:13.639Z`. Ela inclui preparação, diagnóstico e coleta e exclui trabalho posterior. Não é o custo total desta conversa nem o custo apenas do agente avaliado.

O pipeline final `hdast run` levou **14 min 28,002 s**: preflight 0,677 s; probe 4,935 s; scan 856,246 s; authz 5,682 s; report 0,351 s. O `run.json` mede o pipeline; o `metrics.json` mede etapas internas e uma renderização anterior do relatório. Os valores podem diferir por essas fronteiras. Há também preparação, leitura, ajustes, triagem e esperas fora do pipeline.

## Por onde começar a análise

| Pergunta | Material |
| --- | --- |
| Como se compara ao teste cego existente? | [Comparação com a V1.1](comparison.md) |
| O que parece ter prejudicado o resultado? | [Observações e hipóteses verificáveis](observations.md) |
| Quais números podem ser processados? | [Resumo completo](summary.json), [tempos do agente](analysis/agent-stages.csv), [etapas do pipeline](analysis/pipeline-stages.csv), [tokens por resposta](analysis/tokens-by-response.csv), [operações sem teste](analysis/not-tested.csv) |
| O que o agente entregou? | [Relatório HTML final](attempts/02-main/trace/executions/2026-11-15T01-31-02Z-clinica-piloto-3c63/report.html), [relatório Markdown arquivado](attempts/02-main/trace/executions/2026-11-15T01-31-02Z-clinica-piloto-3c63/report.md.txt), [resposta final pública](attempts/02-main/coordinator/agent-final-03.md.txt) |
| Onde ele parou sozinho? | [Snapshot autônomo](autonomous-boundary/agent-metrics.json), [nota nesse ponto](autonomous-boundary/score.json), [resposta pedindo orientação](attempts/02-main/coordinator/agent-final-02.md.txt) |
| O que foi executado e explicado publicamente? | [Transcript público normalizado](attempts/02-main/transcript.jsonl), [eventos com horário](attempts/02-main/coordinator/timed-events.jsonl), [diário de decisões do perfil](attempts/02-main/trace/profile/final/clinica-piloto/decision-log.md.txt) |
| Quais dados sustentam cobertura e achados? | [Probe](attempts/02-main/trace/executions/2026-11-15T01-31-02Z-clinica-piloto-3c63/probe.json), [scan](attempts/02-main/trace/executions/2026-11-15T01-31-02Z-clinica-piloto-3c63/scan.json), [achados](attempts/02-main/trace/executions/2026-11-15T01-31-02Z-clinica-piloto-3c63/findings.json), [triagem](attempts/02-main/trace/executions/2026-11-15T01-31-02Z-clinica-piloto-3c63/triage.json), [authz](attempts/02-main/trace/executions/2026-11-15T01-31-02Z-clinica-piloto-3c63/authz.json) |
| Quais regras e recursos consumiram tempo? | [Métricas detalhadas](attempts/02-main/trace/executions/2026-11-15T01-31-02Z-clinica-piloto-3c63/metrics.json), [regras do ZAP](attempts/02-main/trace/executions/2026-11-15T01-31-02Z-clinica-piloto-3c63/rule-stats.json), [amostras de recursos](attempts/02-main/coordinator/resources.jsonl) |
| Qual era o pedido e quais eram as instruções? | [Briefing cego](protocol/workspace/EVAL-BRIEFING.md.txt), [carta do caso](protocol/case/authorization.md.txt), [caso](protocol/case/case.yml), [regras e skills arquivadas](protocol/workspace) |
| Como conferir origem e integridade? | [Manifesto SHA-256](manifest.json), [política de retenção](protocol/retention.json), [verificação](validation.json) |

## Tentativas e intervenções

1. A tentativa 01 iniciou um agente novo. O ZAP na porta alternativa 38081 recusou comandos de controle ao encaminhá-los ao proxy de escopo. A tentativa parou no preflight; não foi descartada dos registros. O coordenador corrigiu a porta do ZAP para 8080.
2. A tentativa 02 iniciou outro agente novo, sem histórico da tentativa anterior. A aprovação do perfil usou o mecanismo próprio do avaliador de laboratório, pelo coordenador; o agente não executou a aprovação humana da CLI.
3. O preflight autenticou as quatro contas, mas o probe manteve um erro de autenticação no login do contrato. Depois de dois probes reais, o agente parou conforme a skill e pediu orientação. Não houve varredura no segmento autônomo.
4. O dono do laboratório escolheu **“Preservar e concluir com assistência”**. A mesma conversa do agente foi retomada, com orientação para encerrar ajustes de alcance e concluir o que estava autorizado, registrando lacunas. O coordenador não forneceu pistas do gabarito, nomes de arquivos válidos nem credenciais novas.
5. O agente executou o pipeline e anotou todos os achados; o coordenador coletou e mediu. As duas pilhas próprias foram encerradas. A pilha da outra sessão foi preservada.

As portas API 38080, gerenciamento 39091 e proxy 33128 e os nomes de imagens/redes isolaram esta rodada da sessão que ocupava 28080. A alteração está no [patch de infraestrutura e autorização ampla](attempts/02-main/coordinator/isolation-and-wide.patch). Esse patch foi aplicado à cópia de avaliação, sem integrar essa configuração ao produto.

## Retenção e limites

Os originais em `C:\harness-dast-artefatos\v1.7` foram preservados. Esta cópia contém evidências sanitizadas, resumos, instruções usadas, scripts de medição como texto, perfis finais e patches de seu histórico. O snapshot autônomo mantém o estado anterior à assistência; o segmento assistido tem sua própria medição. A referência V1.1 tem cópias de suas métricas e da execução histórica disponível.

Foram guardadas **decisões declaradas, comentários e respostas públicos, comandos e resultados de ferramentas**. Não foi exportado raciocínio interno privado do modelo nem o rollout nativo completo. A contagem de tokens de raciocínio é preservada como métrica, sem seu conteúdo. Nomes históricos como `thinking_seconds` são tempo decorrido fora de ferramentas; no total que inclui a pausa, incluem espera de coordenação, e não medem pensamento interno.

Não entram `sealed/`, `state/`, `.env`, arquivos de aprovação ou valores de credenciais. JWTs, cabeçalhos de sessão e segredos conhecidos são sanitizados quando encontrados. O manifesto identifica arquivos transformados e suas origens. Detalhes dos contêineres da outra sessão foram substituídos por uma contagem por amostra.

Nos cookies, os valores de sessão são mascarados e os atributos, como `HttpOnly` e `SameSite`, são preservados para permitir revisar os alertas. Alguns textos de saída de ferramenta já chegaram com caracteres substituídos por problemas de codificação; a [verificação](validation.json) lista esses arquivos, sem reconstruir conteúdo por suposição.

Uma única amostra assistida, modelos e modos diferentes e outra pilha no mesmo Docker impedem atribuir diferenças isoladamente à versão ou às novas diretrizes. As mesmas classes do gabarito apareceram, mas isso não assegura qualidade igual: 13 das 30 operações elegíveis ficaram sem varredura. O avaliador ainda pontua classes que dependem de autorização/dados ausentes; a nota original foi mantida, com essa limitação explícita.

Os resumos compatíveis com o comparador estão em [medição autônoma](../../measurements/2026-11-14-clinica-piloto-terra61-medium-wide-autonomo) e [medição assistida](../../measurements/2026-11-14-clinica-piloto-terra61-medium-wide-assistido). O comparador usa o relógio total da segunda, incluindo a pausa; consulte as duas durações antes de interpretar. Todo `evals/` é excluído da cópia preparada para futuros testes cegos.

O arquivamento passou por verificação de hashes, segredos conhecidos, JSON/JSONL, schema das métricas e reconciliação de tempos/tokens. Os checks do repositório também passaram: Ruff, formatação, mypy, import-linter, Vulture e pytest, com 8.330 testes aprovados, 5 ignorados e 113 fora da seleção padrão. Os [logs da verificação](analysis/checks/results.json) estão preservados; essa validação foi offline, sem nova varredura do laboratório.

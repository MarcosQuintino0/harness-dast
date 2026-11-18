# Comparação com a avaliação cega existente

A referência principal é `cega-piloto-003`, descrita no [relatório da V1.1](../../../docs/arquivo/reviews/2026-11-13-rodada-cega-v1-1.md). A rodada atual usa o commit `abc4f3a`, que declara versão 1.5.0, antes do complemento atual. Esta tabela descreve duas observações; não é um experimento controlado de melhoria entre versões.

| Medida | Cega V1.1: Sonnet | Atual: Terra 6.1 medium |
| --- | --- | --- |
| Modo | Estrito | Amplo |
| Término | Pipeline e triagem concluídos; authz pendente | Parou antes do scan; pipeline e triagem concluídos após assistência |
| Tempo total do agente | 27 min 48,701 s | 29 min 36,700 s com pausa; 22 min 36,561 s de segmentos ativos |
| Pausa registrada de coordenação | Sem segmentação equivalente disponível | 7 min 0,139 s |
| Pipeline final | 18 min 47,374 s | 14 min 28,002 s |
| Scan | 17 min 40,703 s | 14 min 16,246 s |
| Probes reais antes do pipeline | 4 | 2 |
| Alcance: sucessos / enviados | 27/30: 90% | 18/23: 78,26% |
| Alcance: sucessos / elegíveis | 27/30: 90% | 18/30: 60% |
| Operações varridas / elegíveis | 26/30: 86,67% | 17/30: 56,67% |
| Operações varridas / contrato | 26/40: 65% | 17/40: 42,5% |
| Achados normalizados / ocorrências | 91 / 92 | 71 / 74 |
| Altos / médios / baixos / informativos | 3 / 0 / 57 / 31 | 6 / 0 / 41 / 24 |
| Classes achadas na régua | H1, H8, H10; H3 parcial | H1, H8, H10; H3 parcial |
| Componente ponderado de achados | 40,48% | 40,48% |
| Nota automática | 8,51 | 6,17 autônoma; 7,18 assistida |
| Tráfego do scan: permitido / negado | 8.203 / 8.651 | 7.804 / 2.538 |
| Negados pela forma do caminho | 7.538 | 576 |
| RPS médio / pico do scan | 7,74 / 19 | 9,13 / 18 |
| Autorização entre contas | Não executada | 64 pedidos, 0 achados, com lacunas declaradas |
| Segurança do escopo | Avaliador sem violação | Avaliador sem violação |
| Chamadas de ferramentas | 41 | 109, incluindo 64 esperas |

O pipeline atual foi 259,372 s mais curto, mas varreu **9 operações a menos**. Esses tempos não demonstram aceleração mantendo qualidade. O modo amplo diminuiu os bloqueios por forma de caminho; isso não compensou os pedidos válidos ausentes na preparação.

## Tokens com a mesma convenção

| Contagem | V1.1 | Atual, tentativa principal |
| --- | --- | --- |
| Entrada nova, incluindo criação de cache quando separada | 148.923 | 108.900 |
| Leitura de cache | 4.469.981 | 7.901.952 |
| Saída | 19.038 | 13.092 |
| Total, incluindo leitura de cache | 4.637.942 | 8.023.944 |
| Entrada nova + saída | 167.961 | 121.992 |

A métrica antiga separa `input=82`, `cache_creation=148841` e `cache_read=4469981`. A telemetria nativa nova inclui cache em `input`; o exportador o separa nos arquivos do comparador. A tabela evita somar cache duas vezes. Os “151 mil” citados no relato antigo são um resumo histórico, não o total segundo esta convenção. Os dados brutos foram preservados sem corrigir o relatório antigo retroativamente.

O total atual acima não inclui a tentativa técnica de 1.449.551 tokens nem o coordenador. Mais tokens de leitura de cache podem refletir contexto crescente e esperas frequentes; não significam, por si, mais testes de segurança. O custo cobrado não foi apurado e não é comparável apenas pela soma de tokens de provedores diferentes.

## Tempo do agente por categoria

| Categoria do avaliador | V1.1, segundos | Atual ativa, segundos | Atual com pausa, segundos |
| --- | --- | --- | --- |
| Leitura | 5,112 | 15,291 | 15,291 |
| Cadastro | 82,323 | 115,119 | 115,119 |
| Alcance | 292,365 | 197,276 | 617,415 |
| Varredura | 1.234,996 | 988,602 | 988,602 |
| Triagem | 41,197 | 34,757 | 34,757 |
| Outro | 12,708 | 5,516 | 5,516 |

As categorias seguem a regra do avaliador aplicada aos comandos. Não são as etapas internas da CLI. A pausa caiu em “alcance”; não deve ser interpretada como trabalho de autenticação nem tempo de raciocínio do modelo.

## Limites da referência

O relatório V1.1 identifica a versão funcional pelo rótulo; alguns artefatos e metadados antigos ainda declaram `0.1.0`, anterior à atualização de versão. O modelo é `claude-sonnet-5-5`, sem esforço equivalente registrado. A carta, a cobertura de authz, o modelo, o modo de caminhos, a carga do Docker e a intervenção diferem.

As classes H2, H4, H5, H6 e H7 continuaram ausentes na régua. Parte depende de dados ou autorização que a entrada não oferece; o gabarito bruto não foi alterado depois do resultado. A igualdade desse componente não estabelece não inferioridade: uma operação que não foi alcançada pode conter uma falha não observada.

Existe também uma [referência histórica em modo amplo, não cega](historical/non-blind-wide-reference.md.txt), com 28 operações varridas. Ela serve como contexto técnico adicional e não substitui `cega-piloto-003` nesta comparação. Os “28” do relatório original da rodada atual referem-se a essa outra referência.

Fontes preservadas: [métricas V1.1](historical/v1-1/measurement/agent-metrics.json), [execução V1.1](historical/v1-1/execution/run.json), [scan V1.1](historical/v1-1/execution/scan.json), [resumo atual](summary.json), [métricas atuais](attempts/02-main/agent-metrics.json) e [comparação estruturada](analysis/comparison.json).

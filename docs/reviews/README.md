# Revisões

Esta pasta guarda relatórios de revisão independente do projeto (por exemplo, revisão de QA) e a resposta a cada um.

## Regra: relatório é registro datado

Um relatório de revisão descreve o estado do projeto **no dia em que foi escrito**. Por isso ele **não é editado depois**, nem para corrigir uma constatação que já foi resolvida. Se o código mudar, o relatório continua dizendo o que o revisor viu.

O que muda com o tempo é a **resposta**: um documento à parte, com uma linha por constatação (decisão e onde está o resultado). Revisão nova gera relatório novo.

Nome dos arquivos: `AAAA-MM-DD-assunto.md` para o relatório e `AAAA-MM-DD-assunto-resposta.md` para a resposta.

## Índice

| Relatório | Resposta | Escopo | Parecer |
| --- | --- | --- | --- |
| [Fechamento V1.8](relatorio-v1.8-fechamento.md) | [Validação nova](2026-11-16-v1-8-validacao-fechamento.md), [QA](2026-11-16-v1-8-qa-fechamento.md) e [matrizes](../../evals/measurements/v1-8/closure/t4-summary.md) | Envelope/estratégia, revalidação por concessão, captura real e T2/T4 B após rebase V1.7 | Continuar condicionado aos gates finais; promoção B recusada por erro da previsão; modelo e init continuam legacy |
| [Registro inicial V1.8](relatorio-v1.8.md) | [Fechamento posterior](relatorio-v1.8-fechamento.md) | Estado anterior ao rebase e à liberação da área do proxy | Registro histórico parcial; suas pendências são respondidas no fechamento, sem reescrever o original |
| [relatorio-v1.7.md](relatorio-v1.7.md) | [Validação independente](validacao-v1.7.md), [QA inicial](qa-v1.7.md) e [matriz final](../../evals/measurements/v1.7/quality-evidence.md) | Ritmo serial opcional, métricas, tecnologias consultivas e T1–T4 | Gates verdes; corrigir para aceite integral, com `legacy` padrão e qualidade/previsão inconclusivas |
| [relatorio-v1.5.5.md](relatorio-v1.5.5.md) | [QA inicial](qa-v1.5.5.md), [encadeamento](qa-v1.5.5-encadeamento.md) e [suíte](qa-v1.5.5-suite.md) | Espera, massa, CORS, par novo, triagem e avaliação | Gates verdes e oito provas nas duas APIs; aceites B/D/F parciais no VAmPI; sem crAPI ou rodada cega |
| [2026-11-13-qa-m1-m2.md](2026-11-13-qa-m1-m2.md) | [2026-11-13-qa-m1-m2-resposta.md](2026-11-13-qa-m1-m2-resposta.md) | M1 (fundação) e primeira metade do M2 (domínio) | Reprovado para fechar o M2 como estava; aprovado com ressalvas para o M1. 19 constatações (A-01 a A-19) |
| [2026-11-13-qa-m2-m5.md](2026-11-13-qa-m2-m5.md) | [2026-11-13-qa-m2-m5-resposta.md](2026-11-13-qa-m2-m5-resposta.md) | M2 a M5: perfil, OpenAPI, probe, scan, report, limpeza e run | Reprovado para fechar o M5 como estava; aprovado com ressalvas para escopo, proxy, `scan`/`report` e leitores de entrada. 19 achados (Q-01 a Q-19) |
| [2026-11-13-rodadas-cegas.md](2026-11-13-rodadas-cegas.md) | (sem resposta: relatório factual de medição) | Primeira avaliação cega: cinco rodadas com agente novo contra Clínica Piloto, VAmPI e crAPI | Notas 9,53, 10,0, 4,5, 10,0 e 8,17; nenhuma violação de segurança; defeitos da régua e lacuna de documentação corrigidos |
| [2026-11-13-rodada-cega-v1-1.md](2026-11-13-rodada-cega-v1-1.md) | (sem resposta: relatório factual de medição) | Rodada cega da V1.1 (1.1.0) contra a Clínica Piloto, modo vulnerável, carta com modo estrito | Nota 8,51; nenhuma violação de segurança; perfil fiel à carta; H5 a H7 não achadas porque o agente não rodou o teste entre contas sem a concordância de uma pessoa |
| [2026-11-13-e2e-lab.md](2026-11-13-e2e-lab.md) | (sem resposta: relatório factual de medição) | `scan`, `report`, `run`, `stop` e `cleanup` contra o ZAP 2.17 real, VAmPI e Clínica Piloto | Medições, defeitos corrigidos e o que a V1 não achou (H2, H5 a H7 e outras) |
| [2026-11-13-lab-v1-1-cerca.md](2026-11-13-lab-v1-1-cerca.md) | (sem resposta: relatório factual de medição) | Cerca da V1.1 contra o lab: modo estrito x amplo, isca por todas as formas, diferencial cerca x servidor, `doctor`, `setup_path`, prazo da pilha e `report.html` | O amplo achou 1 falha plantada a mais (H9) na Clínica Piloto e nada a mais no VAmPI; divergência grave: coerção numérica do parâmetro fora do modelo |
| [2026-11-13-lab-v1-1-authz.md](2026-11-13-lab-v1-1-authz.md) | (sem resposta: relatório factual de medição) | `hdast authz` contra a Clínica Piloto nos modos vulnerável e seguro | H5, H6 e H7 achados no vulnerável, zero achado no seguro; defeito de falso seguro em página vazia corrigido; `report` e BFLA não verificados |
| [relatorio-v1.3.md](relatorio-v1.3.md) | (sem resposta: relatório da versão) | Versão 1.3.0: trava por pilha, carta estruturada, aprovação do escopo, entrevista nas skills e documentos | Aprovado com ressalvas pelo QA; só a trava provada com Docker |

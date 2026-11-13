# Revisões

Esta pasta guarda relatórios de revisão independente do projeto (por exemplo, revisão de QA) e a resposta a cada um.

## Regra: relatório é registro datado

Um relatório de revisão descreve o estado do projeto **no dia em que foi escrito**. Por isso ele **não é editado depois**, nem para corrigir uma constatação que já foi resolvida. Se o código mudar, o relatório continua dizendo o que o revisor viu.

O que muda com o tempo é a **resposta**: um documento à parte, com uma linha por constatação (decisão e onde está o resultado). Revisão nova gera relatório novo.

Nome dos arquivos: `AAAA-MM-DD-assunto.md` para o relatório e `AAAA-MM-DD-assunto-resposta.md` para a resposta.

## Índice

| Relatório | Resposta | Escopo | Parecer |
| --- | --- | --- | --- |
| [2026-11-13-qa-m1-m2.md](2026-11-13-qa-m1-m2.md) | [2026-11-13-qa-m1-m2-resposta.md](2026-11-13-qa-m1-m2-resposta.md) | M1 (fundação) e primeira metade do M2 (domínio) | Reprovado para fechar o M2 como estava; aprovado com ressalvas para o M1. 19 constatações (A-01 a A-19) |
| [2026-11-13-e2e-lab.md](2026-11-13-e2e-lab.md) | (sem resposta: relatório factual de medição) | `scan`, `report`, `run`, `stop` e `cleanup` contra o ZAP 2.17 real, VAmPI e Clínica Piloto | Medições, defeitos corrigidos e o que a V1 não achou (H2, H5 a H7 e outras) |

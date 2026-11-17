# Painel: olhar de usuário na preparação da V1.11

Data: 2026-11-17. Base de código: `develop` `44ef387`, conferida por fetch, em worktree destacada. Este registro distingue preparação e provas executadas.

## Linha de base operacional

Executadas na retomada pelo Claude Code, sobre `44ef387`, com aprovações descartáveis do suporte de integração no estado do teste (sem `profile approve`). Resumos em `C:\harness-dast-artefatos\v1-11\lab-followup\baseline\validation-index.json`.

| Alvo e modo | run_id | ZAP | Autorização | Sinais do proxy | Situação |
| --- | --- | --- | --- | --- | --- |
| Clínica Piloto vulnerável | `2026-11-17T05-02-42Z-clinica-piloto-80a9` | 98 (5 altos) | 4 | 29 | scan concluído, 28 entradas; cobertura parcial |
| Clínica Piloto segura | `2026-11-17T05-24-04Z-clinica-piloto-ab47` | 63 | 1 | 0 | scan concluído, 27 entradas; a tentativa anterior (`2142`) parou em `STACK_STALE` e ficou preservada como rejeitada |
| VAmPI vulnerável | `2026-11-17T05-35-12Z-vampi-1fd0` | 30 | 3 | 4 | scan concluído, 10 entradas |

A inspeção visual dos painéis por uma pessoa continua pendente. O caminho do painel de uma execução com `verification.json` está no [relatório da V1.11](relatorio-v1.11.md).

## Preparação da revisão de interface

Uma fixture sintética dos testes gerou as sete páginas por `hdast panel`, usando o código `44ef387`, em `C:\harness-dast-artefatos\v1-11\ui-fixture-baseline`. Ela não constitui execução do laboratório nem amostra de calibração. A inspeção visual foi bloqueada pelo computer use, que não conseguiu determinar a URL do Edge com confiança suficiente para aplicar sua política e encerrou a interação. Não houve navegação posterior nem inspeção visual concluída.

As lacunas abaixo foram identificadas pela leitura do contrato e da renderização original, **não por abertura dos três painéis da fase 0**:

| Pergunta de QA | O que havia na base | O que falta para julgar |
| --- | --- | --- |
| A falha se repetiu? | Evidência do ZAP e degraus de confiança | Resultado medido de receita com controle e motivo independente da opinião do agente |
| Qual pedido causou o efeito? | Pedido e reprodução manual com marcadores | Associação inequívoca à operação autorizada e ao pedido usado na mini prova |
| Como a resposta difere de uma entrada válida? | Resposta da melhor ocorrência | Ataque e controle lado a lado; status, tempo e trecho redigido suficientes |
| O detalhe realmente sustenta a falha? | Explicação e trecho apontado pelo ZAP | Limites do oráculo e indicação explícita de comparação inconclusiva ou indisponível |
| Uma pessoa já verificou? | Terceiro degrau previsto, sem gravador na CLI | Declaração humana aditiva com quem, quando e o que viu, separada do resultado automático |
| O que devo revisar primeiro? | Severidade e agrupamento | Filtro de inconclusivos e altos sem reprodução, sem mudar severidade |
| Qual é o acerto dessa verificação? | Sem calibração medida | Matriz por tipo, proveniência, tamanho da amostra e ausência de porcentagem com amostra pequena |

## Limite desta preparação

A fase 0 permanece pendente: faltam as três varreduras completas e a inspeção de seus painéis. Os testes offline de interface e o roteiro preparado não substituem esses aceites. Uma futura execução deve registrar seus próprios identificadores e contagens, preservando este registro datado.

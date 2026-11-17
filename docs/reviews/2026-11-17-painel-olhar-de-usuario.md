# Painel: olhar de usuário na preparação da V1.11

Data: 2026-11-17. Base de código: `develop` `44ef387`, conferida por fetch, em worktree destacada. Este registro distingue preparação e provas executadas.

## Linha de base operacional pendente

| Alvo e modo previstos | run_id operacional | Achados | Situação |
| --- | --- | --- | --- |
| Clínica Piloto vulnerável | Não iniciado | Não medidos | Perfil local `not_approved` |
| Clínica Piloto seguro | Não iniciado | Não medidos | Perfil local `not_approved` |
| VAmPI vulnerável | Não iniciado | Não medidos | Perfil local `not_approved` |

O Docker respondeu e não havia pilhas em `docker compose ls -a`. Os perfis foram copiados do laboratório sem alteração de blocos protegidos; `hdast profile approval` informou falta de aprovação por pessoa para ambos. O coordenador preparou o roteiro de aprovação em `C:\harness-dast-artefatos\v1-11\aprovar-laboratorio.ps1` e solicitou a intervenção humana. Não executou `profile approve`, não gravou aprovações por dublê e não iniciou tráfego contra os alvos. Nenhuma contagem de falso positivo do modo seguro foi obtida. Ausência de execução não é zero achados.

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

# Observações para melhorar a próxima avaliação

Este registro distingue fatos medidos de hipóteses. Nenhuma melhoria de produto foi implementada durante o arquivamento. Os identificadores abaixo permitem ligar uma proposta futura à evidência original.

| ID | Observação e evidência | Consequência | O que investigar ou medir |
| --- | --- | --- | --- |
| O01 | Preflight autenticou as quatro contas; o probe terminou com um `auth_error` no login do contrato. Veja [probes](summary.json) e [decisões do perfil](attempts/02-main/trace/profile/final/clinica-piloto/decision-log.md.txt). | O agente seguiu a skill e parou antes da varredura. | Hipótese: dados do pedido de login não reutilizam o vínculo de conta usado no preflight. Reproduzir e comparar os caminhos, sem expor valores de credenciais. |
| O02 | O probe passou de 17/22 a 18/23 sucessos; ainda deixou 7 dependências, 2 conflitos, 2 ausências e 1 erro de autenticação. | A preparação deixou menos requisições válidas disponíveis ao scanner. | Melhorar dados/encadeamento e mensagens de diagnóstico; medir sucessos por operação elegível, e não apenas por pedido enviado. |
| O03 | Downloads ficaram em 404 e a carta não fornecia arquivos válidos. [Operações sem teste](analysis/not-tested.csv). | Essas rotas não foram varridas nesta versão testada. | Definir fixtures sintéticas na entrada do caso e uma política explícita para operações 404. Comparar preservando a mesma carta nos braços do experimento. |
| O04 | Atual: 17 operações varridas; cega V1.1: 26. | Scan menor pode dar menos achados e gastar menos tempo sem melhorar eficiência. | Usar cobertura e detecção como critérios de aceite antes de otimizar tempo. Relatar exclusões autorizadas separadamente de falhas de preparação. |
| O05 | O scan levou 856,246 s; foram registradas 64 chamadas de espera no agente principal e 12 leituras do mesmo arquivo de progresso. | Há custo de coordenação em torno de um trabalho longo da CLI. | Hipótese: acompanhamento menos frequente e retorno mais compacto podem reduzir tokens sem mudar ataques ou cobertura. Medir a mesma execução com políticas de acompanhamento diferentes. |
| O06 | Entrada nova: 108.900 tokens; leitura de cache: 7.901.952. [Por resposta](analysis/tokens-by-response.csv). | Contexto relido domina o volume contado. | Medir tamanho das saídas de ferramenta e crescimento do contexto por etapa; testar resumos operacionais que preservem lacunas e evidências. Não confundir essa hipótese com redução de testes. |
| O07 | Scan completo para os 17 pedidos planejados; `partial=false`, mas só 56,67% das 30 operações elegíveis foram varridas. | “Completo” no scanner não significa contrato coberto. | Dar destaque conjunto à conclusão da etapa e à cobertura do contrato no relatório e na aceitação da execução. |
| O08 | Authz: 64 pedidos, 0 achados; BOLA horizontal e BFLA vertical não tiveram cobertura efetiva. Escritas não foram autorizadas. | O zero não confirma segurança dessas classes. | Rever pares de contas/recursos e matriz de acesso da entrada; alinhar as classes pontuadas à autorização. Congelar a régua antes das novas rodadas. |
| O09 | 23 anotações suspeitam de falso positivo de HttpOnly em cookie XSRF. | A contagem de alertas mistura sinais com pesos diferentes. | Medir precisão da triagem e tempo de revisão, preservando severidade original e todas as evidências. Não ensinar descarte automático apenas a partir desta amostra. |
| O10 | Dois sinais SQL por erro e quatro alertas temporais receberam cautelas de triagem. | Mais alertas altos não provam mais falhas distintas. | Separar alertas, ocorrências, classes da régua e reproduções confirmadas. Para temporização, medir ruído e repetibilidade sob carga equivalente. |
| O11 | Modo amplo: 576 bloqueios por forma, contra 7.538 no estrito antigo. Continuaram 1.945 bloqueios por caminho e 17 por origem. | O modo amplo altera a superfície testável e invalida uma comparação isolada de versão. | Manter modo, carta e escopo iguais no teste de uma melhoria; tratar bloqueios de escopo como dados, sem relaxar a cerca para melhorar a nota. |
| O12 | Houve 8 lacunas de tráfego maiores que 10 s, somando 110,488 s. Regras SQL temporais, SSTI e comando concentram tempo acumulado. | Há candidatos para investigação de ociosidade e custo de regras. | Correlacionar progresso, regras, CPU e tráfego; não remover regras nem somar tempos concorrentes como se fossem o relógio total. |
| O13 | Pico de memória combinado amostrado: 1.747,83 MiB; ZAP 1.428,48 MiB. Outra pilha estava no mesmo Docker. | Os recursos registrados não representam ambiente exclusivo nem pico contínuo. | Repetir sob carga controlada, guardar limites/versões e aumentar resolução da amostragem se necessário. |
| O14 | A tentativa inicial falhou por controle do ZAP na porta alternativa. O agente seguinte foi novo. | O custo técnico não deve desaparecer nem contaminar a medição de autonomia da tentativa principal. | Parametrizar e verificar previamente isolamento de portas; registrar falhas técnicas como tentativas separadas. |
| O15 | Aprovação do avaliador e assistência para prosseguir foram intervenções distintas. | A rodada final é assistida, mesmo que todos os comandos de teste tenham sido conduzidos pelo agente. | Avaliar separadamente autorização inicial, parada operacional, conclusão autônoma e conclusão assistida. |

## Critérios para uma comparação futura útil

- Fixar commit, alvo, carta, fixtures, contas, modo, força, limite de tráfego, versões do ZAP/imagens, modelo e esforço; registrar as diferenças intencionais.
- Usar agentes novos sem gabarito e múltiplas rodadas. As evidências desta pasta ficam fora da cópia cega.
- Definir antes a cobertura mínima por operação e classe autorizada, a precisão de triagem e os limites aceitáveis de regressão. Tempo menor só conta como ganho se esses critérios forem atendidos.
- Medir relógio total, tempo ativo, pausas, preparação, pipeline e cada etapa; registrar tentativas técnicas, intervenção e motivo da parada.
- Contar entrada nova, cache e saída separadamente. Comparar custo financeiro apenas com preços e consumo cobrados conhecidos.
- Se houver paralelismo futuro, medir isolamento de recursos/contas e efeitos colaterais entre testes. Dividir por categoria ou por conta é uma hipótese a avaliar, não uma melhoria demonstrada por esta rodada.

## O que esta amostra permite dizer

O agente configurou o produto e usou a CLI/ZAP dentro do escopo auditado, mas não concluiu sozinho e deixou lacunas de alcance. O pipeline assistido foi mais curto e produziu menos achados normalizados, com menos operações varridas. A menor cobertura é um problema concreto para investigar; a contagem de achados, sozinha, não mede qualidade.

Não houve uma recusa de segurança do provedor registrada como motivo da parada desta rodada. O motivo observado foi a instrução da skill diante de autenticação persistente. O efeito isolado das novas diretrizes sobre recusas não foi medido por um A/B e não deve ser atribuído a este resultado.

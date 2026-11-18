# 0106. Vigia do proxy reverifica o retrato velho em vez de travar

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** rodada cega de 2026-11-18: `{"event": "gate_watch_latch", "category": "age"}` numa rajada do ZAP, com aprovação intacta (`stack status` com `stale_parts: []`); a varredura morreu três vezes

## Contexto

Uma thread relê aprovação, perfil e kill switch a cada 50 ms e publica um retrato com a hora em que a leitura começou. `check()` exigia retrato com no máximo 200 ms e, se passasse disso, gravava a falha de forma permanente (categoria `age`), negando todo pedido até a pilha ser recriada (ADRs 0072, 0081 e 0093). Sob carga (rajada do ZAP, GIL, disco lento) a thread pode simplesmente atrasar: o retrato fica velho sem que nada tenha mudado. Tratar atraso como alteração derrubava a varredura inteira por um falso alarme. Se nada for decidido, a rodada cega repete o defeito.

## Decisão

Vamos separar atraso de alteração. Retrato velho continua sem poder conceder, mas lentidão passa a negar só o pedido, sem trava permanente:

1. A regra de decisão é a função pura `judge_snapshot` (`adapters/scope_proxy/gate_watch_rule.py`): encerramento, retrato ausente e relógio para trás dão `LATCH`; idade acima de 200 ms dá `REVERIFY`; idade entre 0 e 200 ms dá `GRANT`. Fica no adaptador, e não em `domain`, porque devolve `WatchCause`, categoria de diagnóstico que pertence ao adaptador; não faz E/S nem lê relógio.
2. Em `REVERIFY`, `check()` dispara uma verificação síncrona (`run_once` numa thread auxiliar) sem segurar o lock da concessão durante a E/S, e espera até 150 ms reais. Só uma reverificação existe por vez: chamadas concorrentes esperam a mesma. Terminada, a decisão é refeita com o relógio atual e o retrato novo.
3. **Lentidão nega, não trava.** Se o retrato ainda estiver acima de 200 ms depois da reverificação, ou se o tempo-limite estourar, só aquele pedido é negado (`approval_changed`, como hoje) e nada é gravado em `_failure`; o pedido seguinte tenta reverificar de novo. Sob rajada, a própria reverificação pode demorar mais que 200 ms, e travar nesse caso repetiria o defeito com menos frequência.
4. **Trava permanente só para** mudança real detectada, erro de leitura ou detecção, `close()`, relógio para trás e falha ao iniciar a thread de reverificação.
5. O retrato nunca recua: uma leitura lenta e antiga que termina depois de uma nova não sobrescreve a hora mais recente. Nenhum pedido é concedido sem leitura bem-sucedida iniciada há no máximo 200 ms no instante da decisão.
6. Diagnóstico: cada negação por lentidão emite, no máximo uma vez por segundo (relógio da vigia), a linha `{"event": "gate_watch_slow_deny", "category": "slow_deny"}`, sanitizada como a do 0093, para a rodada mostrar quantas vezes ocorreu. A categoria `age` deixa de existir no catálogo; `slow_deny` a substitui.

## Alternativas consideradas

- Subir o limite de 200 ms: só adia o falso alarme e alarga a janela de revogação sem fechar a causa.
- Renovar o retrato quando a leitura termina: mudaria a garantia do ADR 0072 (a leitura lenta pareceria recente).
- Reverificar dentro do lock: E/S bloqueada prenderia concessões e o encerramento.
- Travar permanentemente em reverificação lenta ou tempo-limite: foi a primeira versão deste ADR; descartada porque, sob a carga que causou o defeito, a reverificação também pode passar de 200 ms e a pilha morreria de novo.
- Reverificar sem tempo-limite ou várias em paralelo: leitura presa bloquearia a fila; paralelas multiplicam a carga que causou o atraso.
- Deixar a regra dentro de `GateWatch`: mistura decisão e mecânica de threads e dificulta testar a tabela de casos.

## Consequências

Relação com os ADRs anteriores: substitui parcialmente o 0081 e o 0093 no tratamento do atraso. O 0081 segue valendo para `STACK_STALE` e `stack status`; o 0093 segue valendo para o diagnóstico de trava, cujo catálogo perde `age` e ganha `slow_deny`, usada só no evento separado de negação por lentidão.

Rajadas deixam de matar a varredura; o custo é uma leitura extra (alguns milissegundos) no primeiro pedido depois de um atraso, e até 150 ms de espera nele; pedidos negados por lentidão podem ser reenviados pelo cliente, e o contador `slow_deny` indica se a carga exige ajustar o tempo-limite. Falta de prova real: a correção foi exercitada só em unidade e contrato (relógio e leitura falsos); a prova na rodada cega e com o ZAP real fica para o coordenador.

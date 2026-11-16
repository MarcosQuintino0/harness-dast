# ADR 0061: espera local por execução

Status: Proposto. Data: 2026-11-15.

## Contexto e decisão

O `run` passa por pastas diferentes de preflight e probe; escolher a pasta mais recente não identifica a execução de forma confiável. `hdast wait --product PRODUTO --timeout SEGUNDOS` espera pela tomada ativa da trava exclusiva do `run`. O processo publica um marcador atômico na pasta de execuções identificado pelo `lock_id`, com fase e, quando disponível, o identificador da pasta final. O marcador não contém segredos nem é apagado automaticamente. A consulta não toca o alvo. O padrão de timeout é 600 segundos, com limites de 1 a 28800.

O envelope de sucesso contém `data.state`, `status`, `exit_code`, `phase`, `progress`, `run_id` e `lock_id`; o `run_id` do envelope fica presente quando conhecido. `finished` exige `run.json`; status e exit_code são do run. `running` indica que a tomada capturada continua ativa. `stopped` indica que a tomada capturada deixou de estar ativa sem resultado final. `unknown` indica que nenhuma tomada foi capturada ou que a trava está ilegível. O percentual, quando disponível, é da operação atual do scan. Antes de acabar o probe, run_id pode ser nulo. A falha de gravação do marcador é registrada em log e não interrompe o run; neste caso a consulta pode não encontrar o resultado.

Ao expirar com lock_id, repita com `--product PRODUTO --lock LOCK_ID` para continuar seguindo a mesma tomada, inclusive se terminou entre duas chamadas. Sem lock_id, confira a saída do processo antes de repetir: uma execução rápida pode terminar antes da primeira observação. `--run ID` é alternativa para uma pasta já conhecida; não combina com `--product` ou `--lock` e só considera o processo ativo se o marcador da trava o associa à pasta. Uma chamada de espera não interrompe o run.

O comando sai 0 ao devolver uma observação, inclusive ao expirar; `state` diz o resultado. Entrada inválida, execução inexistente ou artefato ilegível saem 2 no envelope usual; erro interno sai 10. O código do run é dado separado, não o código de `wait`.

## Alternativas e consequências

Laços do agente produzem muitas chamadas e custos; o progresso sozinho pode ser antigo. A trava dá identidade à execução e o marcador acompanha a troca de pasta. O processo pode terminar antes de ser observado: sua saída continua a fonte de resultado nesse caso. Um processo morto abruptamente pode deixar marcador sem resumo; isso é `stopped`, sem atribuir código de saída.

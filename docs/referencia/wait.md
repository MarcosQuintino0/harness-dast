# `hdast wait`: espera por uma execução

O `wait` aguarda o resultado de um `hdast run` ou o fim de um prazo. Ele consulta arquivos locais e a trava da pilha; **não envia pedidos ao alvo** nem interrompe a execução. A decisão de contrato está no [ADR 0061](../decisoes/0061-espera-de-execucao.md). O comando foi verificado com testes de contrato locais; a execução integrada é verificada no fechamento da versão.

## Como usar

Depois de iniciar o `run` em segundo plano, aguarde a execução ativa do produto:

```text
uv run hdast --json wait --product <produto> --timeout 600
```

O comando captura a identidade da trava do `run`, sem escolher uma pasta por ser a mais recente. Se o prazo terminar com `running` ou `unknown` e houver `data.lock_id`, repita para acompanhar **a mesma execução**, inclusive se ela terminar entre as chamadas:

```text
uv run hdast --json wait --product <produto> --lock <lock_id> --timeout 600
```

Se o identificador da pasta da execução já é conhecido, também é possível consultá-la diretamente:

```text
uv run hdast --json wait --run <run_id> --timeout 600
```

Informe exatamente um entre `--product` e `--run`. A opção `--lock` exige `--product`. O prazo padrão é 600 segundos; `--timeout` aceita um inteiro de 1 a 28800 segundos. Em shells com limite de duração, escolha um prazo compatível que cubra minutos e repita quando necessário.

## Resultado

No modo JSON, a consulta bem-sucedida usa o envelope usual: `schema_version`, `ok`, `data` e, quando conhecido, `run_id` no nível superior. `ok: true` significa que a **consulta** funcionou; examine `data.state` para saber o estado observado.

| Campo em `data` | Significado |
| --- | --- |
| `state` | Estado observado: `finished`, `running`, `stopped` ou `unknown`. |
| `status` | Estado final do `run`, obtido de `run.json`; `null` sem resultado final. |
| `exit_code` | Código de saída registrado pelo `run`; `null` sem resultado final. É separado do código de saída do `wait`. |
| `phase` | Última fase publicada no marcador, quando disponível. Com `--run`, é a última fase do progresso do scan. |
| `progress` | Percentual da operação atual do scan, quando disponível; não é o percentual do `run` inteiro. |
| `run_id` | Identificador da pasta final quando conhecido pelo modo `--product`; pode ser `null` durante preflight ou probe. Com `--run`, consulte o identificador no envelope superior. |
| `lock_id` | Identidade da tomada da trava capturada no modo `--product`; use-a para retomar a mesma espera. Pode ser `null` antes da captura e no modo `--run`. |

`finished` significa que existe `run.json`; leia `status` e `exit_code` e, em seguida, o relatório. `running` indica que a tomada identificada ainda está ativa. `stopped` indica que ela deixou de estar ativa sem resultado final: não presumir o código de saída nem que a interrupção foi voluntária. `unknown` indica que não foi possível identificar a tomada ou ler a trava; não é confirmação de término. Na consulta por `--run`, uma trava ativa só confirma `running` quando seu marcador associa aquela pasta à execução.

| Saída do `wait` | Significado |
| --- | --- |
| `0` | Observação devolvida, inclusive quando o prazo expira; confira `data.state`. |
| `2` | Uso inválido, identificador ou execução inválida/inexistente, ou artefato ilegível. Confira `error.message` e `error.hint`. |
| `10` | Erro interno; guarde a mensagem para o mantenedor. |
| `130` | A espera foi interrompida. A interrupção da espera não para o `run`. |

## Limites

O preflight e o probe podem usar pastas distintas, por isso o `run_id` final não está necessariamente disponível no início. Se o `run` terminar **antes de a primeira espera capturar a trava**, `lock_id` fica nulo e não se deve selecionar uma pasta antiga: confira a saída do processo iniciado. Enquanto nenhuma trava for capturada, o comando pode aguardar até o prazo e retornar `unknown`.

O `run` publica um marcador local por identidade de trava, sem segredos. Se não conseguir gravá-lo, registra o problema em log e continua a execução; nesse caso a espera pode não recuperar o resultado. Um processo encerrado abruptamente pode deixar marcador sem `run.json`: o resultado é `stopped`, sem código final. O marcador não é removido automaticamente.

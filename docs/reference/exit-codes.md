# Códigos de saída

Decisão: [ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md). Os códigos são contrato público: mudança exige ADR e atualização do teste de contrato.

| Código | Nome no código | Significado | Erro associado | Quem produz |
| --- | --- | --- | --- | --- |
| `0` | `OK` | Sucesso | Nenhum | Implementado (M1). Também `hdast` sem argumentos (mostra a ajuda) |
| `1` | `FINDINGS` | Achados acima do limiar configurado | Não é erro; é resultado do `report` (e do `run`, que o repassa) | Implementado (M4, M5). **Só o `report` produz o `1`** (`--fail-on` ou `scan.fail_on`; envelope com `ok: true`). O `scan` nunca sai com `1`; o `run` sai com `1` quando o `report` dele sai |
| `2` | `USAGE` | Erro de uso ou de configuração | `ConfigError` (`CONFIG_ERROR`); também `LetterRejected` (`LETTER_REJECTED`) e `AuthzConfigError` (`AUTHZ_CONFIG_INVALID`, V1.4, [ADR 0041](../adr/0041-tabela-quem-pode-o-que.md): a tabela `authz.access_matrix` cita operação ou papel que não existe) | Implementado (M1). `hdast init`, `hdast profile validate` e o `doctor` (pasta de produtos, perfil ou porta configurada inválidos) o produzem para nome, pasta, YAML ou perfil inválidos (M2). Perfil válido porém ainda não executável sai com `0`, com `runnable: false` no `data` |
| `3` | `SCOPE` | Violação de escopo ou janela fechada | `ScopeViolation` (`SCOPE_VIOLATION`); também `ScopeNotApproved` (`SCOPE_NOT_APPROVED`) | Implementado (M3). `preflight` e `doctor` (autorização vencida ou janela fechada) e `probe` (os mesmos, na partida e no meio da execução, ou prazo `limits.max_duration_minutes` esgotado) e `scan` (os mesmos, no meio da varredura, com o resultado parcial em `data`) e `authz` (os mesmos, na partida e no meio, com o resultado parcial em `data`). Uma requisição concreta fora do escopo NÃO sai com 3: a operação é `skipped_scope` ou `skipped_denied` e o `probe` continua | V1.3 ([ADR 0037](../adr/0037-aprovacao-humana-do-escopo.md)): `SCOPE_NOT_APPROVED` (saída 3, sem código novo) em `preflight`, `probe`, `scan`, `authz`, `run`, `cleanup` e `stack up` quando nenhuma pessoa aprovou os blocos de proteção do perfil ou eles mudaram depois da aprovação.
| `4` | `PREFLIGHT` | Preflight falhou (ambiente ou login) | `PreflightError` (`PREFLIGHT_FAILED`) | Implementado (M3). `preflight` com qualquer verificação que não seja de escopo falhando; `doctor` com uma conferência de ambiente reprovada (Docker, porta, Python, segredo ausente); `probe` que não consegue começar (ZAP inacessível, segredo ausente, login recusado). `SECRET_BACKEND_ERROR`: referência `keyring:` sem cofre do sistema utilizável (a mesma saída 4, [ADR 0030](../adr/0030-cofre-de-credenciais-do-sistema-keyring.md)). M4: `scan` que não consegue começar (ZAP sem o contexto do `probe`, política de varredura recusada, login recusado, inclusive no meio: `stopped_auth`) |
| `5` | `EXTERNAL_TOOL` | Falha de ferramenta externa (ZAP, Docker) | `ExternalToolError` (`EXTERNAL_TOOL_ERROR`) | Implementado (M3): o proxy do ZAP deixa de responder no meio do `probe` (`stopped_zap`). Falha de API do ZAP na partida sai com 4. M4: o ZAP falha no meio do `scan` ou do `authz` (`stopped_zap`), ou as regras do Replacer não puderam ser removidas ao fim |
| `6` | `TARGET` | O alvo respondeu de forma que impede o prosseguimento | `TargetError` (`TARGET_ERROR`) | Implementado (M3): cinco falhas de transporte seguidas no `probe` (`stopped_target_unresponsive`). M4: três falhas seguidas da guarda de saúde durante o `scan`; `authz`: cinco falhas de transporte seguidas (`stopped_target_unresponsive`) |
| `7` | `CLEANUP` | A limpeza do ambiente falhou | `CleanupError` (`CLEANUP_FAILED`) | Implementado (M5): `hdast cleanup` com falha no banco, teto de linhas excedido ou erro ao confirmar (a transação sofre `ROLLBACK`). Execução, perfil, script, segredo ou confirmação inválidos saem com `2` |
| `8` | `BUSY` | A pilha (ZAP e proxy) já está ocupada por outra execução, ou o arquivo de trava não pôde ser lido | `StackBusy` (`STACK_BUSY`) | Implementado (V1.3, [ADR 0035](../adr/0035-trava-por-pilha.md)). `probe`, `scan`, `authz` e `run` (fora do `--dry-run`) e `stack up` e `stack down`, na partida, antes de tocar o alvo. A mensagem diz quem ocupa (comando, produto, id, processo e início). `hdast stop` e `stack status` nunca saem com `8` |
| `10` | `INTERNAL` | Erro interno inesperado | `HarnessError` genérico (`INTERNAL`) | Implementado (M1) |
| `130` | (interrupção) | Interrompido pelo usuário (Ctrl+C) ou pela trava de emergência durante o `run` | `INTERRUPTED` | Implementado. `hdast run` grava `run.json` com `status: interrupted` e, se foi `hdast stop`, `stop_requested: true` |

Os códigos `6`, `7` e `130` foram acrescentados na rodada de correção de 2026-11-13 ([ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md), seção Histórico). O `130` segue a convenção de shells (128 mais o sinal 2).

## Como usar em scripts e no CI

```bash
uv run hdast --json version
echo $?
```

Tratamento sugerido: `0` segue; `1` é um resultado de segurança que o time precisa avaliar (não é falha da ferramenta); `2` a `7` são falhas que pedem correção do uso, da configuração, do ambiente, do alvo ou da limpeza; `8` pede esperar a outra execução terminar (ou `hdast stop`) e tentar de novo, sem mudar nada; `130` é interrupção deliberada; `10` deve ser reportado ao mantenedor.

## `hdast run`

O `run` sai com o código do estágio que falhou (preflight: 3 ou 4; probe: 3, 5 ou 6; scan: 3 a 6; authz, se pedido: 3, 5 ou 6; report: 1 com achado no limiar, 2 em erro), `0` se tudo passou e `130` se foi interrompido. O `run.json` traz o código de cada estágio. A trava de emergência (`hdast stop`) durante um `scan` solto sai com `3` (como janela fechada); durante o `run`, com `130`.

## `hdast wait`

A espera sai com `0` ao consultar com êxito, inclusive quando o prazo termina. Isso não significa que a execução terminou nem que ela teve sucesso: consulte `data.state`, `data.status` e `data.exit_code`; o código da execução só aparece quando terminada. Identificador ou configuração inválida ou execução inexistente sai com `2`; erro interno sai com `10`. Veja [wait.md](wait.md).

## Resultado parcial

`preflight` não pronto, `probe` e `scan` interrompidos depois de começar (códigos 3 a 6) devolvem `ok: false` com `error` E `data`: o agente lê o que foi feito até ali. O `probe` sai com 0 mesmo quando operações falham: falha de operação é dado, não erro do comando.

## Regras

- Todo erro esperado herda de `HarnessError` e é convertido em código de saída por um único tratador na CLI.
- Qualquer exceção que não seja `HarnessError` ou erro de uso vira `INTERNAL` (código `10`), com envelope válido e sem traceback em `stdout`.
- Escopo e janela falham fechados: na dúvida, o código é `3` e a execução para.
- O código `1` depende de um limiar de severidade proposta (`none`, `low`, `medium`, `high`), em `report --fail-on` ou `scan.fail_on` do perfil (padrão `none`), e é aplicado só pelo `report`, sobre todos os achados ([relatorio.md](relatorio.md#código-de-saída-1)).

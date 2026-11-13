# Códigos de saída

Decisão: [ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md). Os códigos são contrato público: mudança exige ADR e atualização do teste de contrato.

| Código | Nome no código | Significado | Erro associado | Quem produz |
| --- | --- | --- | --- | --- |
| `0` | `OK` | Sucesso | Nenhum | Implementado (M1). Também `hdast` sem argumentos (mostra a ajuda) |
| `1` | `FINDINGS` | Achados acima do limiar configurado | Não é erro; é resultado de `scan`, `report` ou `run` | Planejado (M4) |
| `2` | `USAGE` | Erro de uso ou de configuração | `ConfigError` (`CONFIG_ERROR`) | Implementado (M1). `hdast init` e `hdast profile validate` o produzem para nome, pasta, YAML ou perfil inválidos (M2). Perfil válido porém ainda não executável sai com `0`, com `runnable: false` no `data` |
| `3` | `SCOPE` | Violação de escopo ou janela fechada | `ScopeViolation` (`SCOPE_VIOLATION`) | Implementado (M3). `preflight` (autorização vencida ou janela fechada) e `probe` (os mesmos, na partida e no meio da execução, ou prazo `limits.max_duration_minutes` esgotado). Uma requisição concreta fora do escopo NÃO sai com 3: a operação é `skipped_scope` ou `skipped_denied` e o `probe` continua |
| `4` | `PREFLIGHT` | Preflight falhou (ambiente ou login) | `PreflightError` (`PREFLIGHT_FAILED`) | Implementado (M3). `preflight` com qualquer verificação que não seja de escopo falhando; `probe` que não consegue começar (ZAP inacessível, segredo ausente, login recusado) |
| `5` | `EXTERNAL_TOOL` | Falha de ferramenta externa (ZAP, Docker) | `ExternalToolError` (`EXTERNAL_TOOL_ERROR`) | Implementado (M3): o proxy do ZAP deixa de responder no meio do `probe` (`stopped_zap`). Falha de API do ZAP na partida sai com 4. M4 acrescenta a varredura |
| `6` | `TARGET` | O alvo respondeu de forma que impede o prosseguimento | `TargetError` (`TARGET_ERROR`) | Implementado (M3): cinco falhas de transporte seguidas no `probe` (`stopped_target_unresponsive`) |
| `7` | `CLEANUP` | A limpeza do ambiente falhou | `CleanupError` (`CLEANUP_FAILED`) | Erro definido; produzido no M5 |
| `10` | `INTERNAL` | Erro interno inesperado | `HarnessError` genérico (`INTERNAL`) | Implementado (M1) |
| `130` | (interrupção) | Interrompido pelo usuário (Ctrl+C) | `INTERRUPTED` | Implementado |

Os códigos `6`, `7` e `130` foram acrescentados na rodada de correção de 2026-11-13 ([ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md), seção Histórico). O `130` segue a convenção de shells (128 mais o sinal 2).

## Como usar em scripts e no CI

```bash
uv run hdast --json version
echo $?
```

Tratamento sugerido: `0` segue; `1` é um resultado de segurança que o time precisa avaliar (não é falha da ferramenta); `2` a `7` são falhas que pedem correção do uso, da configuração, do ambiente, do alvo ou da limpeza; `130` é interrupção deliberada; `10` deve ser reportado ao mantenedor.

## Resultado parcial

`preflight` não pronto e `probe` interrompido depois de começar (códigos 3, 5 e 6) devolvem `ok: false` com `error` E `data`: o agente lê o que foi feito até ali. O `probe` sai com 0 mesmo quando operações falham: falha de operação é dado, não erro do comando.

## Regras

- Todo erro esperado herda de `HarnessError` e é convertido em código de saída por um único tratador na CLI.
- Qualquer exceção que não seja `HarnessError` ou erro de uso vira `INTERNAL` (código `10`), com envelope válido e sem traceback em `stdout`.
- Escopo e janela falham fechados: na dúvida, o código é `3` e a execução para.
- O código `1` depende de um limiar de severidade configurável. O limiar e o comando que o aplica ainda não estão definidos em detalhe; fecham no M4.

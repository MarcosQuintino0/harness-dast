# Referência da CLI `hdast`

Decisão: [ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md). Códigos de saída: [exit-codes.md](exit-codes.md). A tabela de status por componente fica em [../roadmap.md](../roadmap.md#tabela-de-status).

## Comandos

Apenas `version` existe hoje. Todos os outros são desenho aprovado e **não funcionam**.

| Comando | O que faz | Toca o alvo? | Status |
| --- | --- | --- | --- |
| `hdast version` | Mostra a versão instalada do harness | Não | Implementado (M1) |
| `hdast init` | Cria a pasta do produto a partir do modelo | Não | Planejado (M2) |
| `hdast profile validate` | Valida `target.yml` e os arquivos de regras contra o schema | Não | Planejado (M2) |
| `hdast spec inspect` | Valida o OpenAPI e devolve um resumo compacto para o agente | Não | Planejado (M3) |
| `hdast preflight` | Confere autorização, janela, ZAP no ar e login de cada conta | Sim, mínimo | Planejado (M3) |
| `hdast probe` | Envia requisições válidas pelo ZAP e mede a alcançabilidade | Sim | Planejado (M3); mecanismo depende do spike do M0 |
| `hdast scan` | Executa a varredura do ZAP com limites fixados | Sim | Planejado (M4) |
| `hdast report` | Normaliza os alertas em achados e gera JSON e Markdown | Não | Planejado (M4) |
| `hdast cleanup` | Roda o hook de limpeza do produto para uma execução, com confirmação humana | Sim | Planejado (M5) |
| `hdast run` | Encadeia preflight, probe, scan e report sem interação | Sim | Planejado (M5) |
| Comando de parada de emergência | Interrompe a varredura e derruba os contêineres | Sim | Planejado (M5). O nome do comando ainda não foi definido |

Os marcos acima seguem o roadmap: `init` e `profile validate` no M2; `spec inspect`, `preflight` e `probe` no M3; `scan` e `report` no M4; `cleanup`, `run` e a parada de emergência no M5.

## Uso

```bash
uv run hdast --help
uv run hdast version
uv run hdast --json version
```

`--json` pode vir **antes ou depois** do nome do comando: `hdast --json version` e `hdast version --json` fazem a mesma coisa. Mesmo um erro de uso (comando inexistente, opção desconhecida) sai como envelope JSON quando a flag está na linha. `hdast` sem argumentos mostra a ajuda e sai com `0`; com `--json` e sem comando, o resultado é um erro de uso em JSON (`CONFIG_ERROR`, saída 2), para não sujar o `stdout` com texto de ajuda. Ctrl+C encerra com o código `130` e `error.code` `INTERRUPTED`. (Antes da rodada de correção de 2026-11-13, `--json` depois do subcomando falhava em texto; achado A-03.)

## Envelope JSON

Com `--json`, o resultado vai para `stdout` como uma linha JSON. Campos sem valor são omitidos.

| Campo | Tipo | Quando aparece | Descrição |
| --- | --- | --- | --- |
| `schema_version` | inteiro | Sempre | Versão do formato do envelope. Hoje `1` |
| `ok` | booleano | Sempre | `true` em sucesso, `false` em falha |
| `run_id` | texto | Quando houver execução | Identificador da execução |
| `data` | objeto | Em sucesso | Resultado do comando |
| `error` | objeto | Em falha | Veja abaixo |

Objeto `error`:

| Campo | Descrição |
| --- | --- |
| `code` | Identificador estável do erro, em MAIUSCULAS |
| `message` | O que aconteceu |
| `hint` | O que fazer a respeito (omitido quando não há) |

Exemplo de sucesso:

```json
{"schema_version":1,"ok":true,"data":{"version":"0.1.0"}}
```

O valor de `version` acima é ilustrativo; ele vem do pacote instalado.

Exemplo de falha (ilustrativo; o cenário de escopo ainda não existe em código):

```json
{
  "schema_version": 1,
  "ok": false,
  "run_id": "2026-11-12T21-04-11Z-agenda-7f3a",
  "error": {
    "code": "SCOPE_VIOLATION",
    "message": "POST https://api.parceiro.com/v1/sms não está na lista permitida do produto agenda.",
    "hint": "Verifique scope.allow em products/agenda/target.yml. Flags não ampliam o escopo."
  }
}
```

Sem `--json`, o sucesso sai em texto no `stdout` e a falha, em texto no `stderr`.

## Valores de `error.code`

Os valores abaixo existem na hierarquia de erros do código. Novos valores entram por marco; remover ou renomear um é mudança de contrato.

| `code` | Erro | Código de saída |
| --- | --- | --- |
| `CONFIG_ERROR` | `ConfigError`: configuração, perfil ou argumento inválido (inclui erro de uso da linha de comando) | 2 |
| `SCOPE_VIOLATION` | `ScopeViolation`: ação fora do escopo, dos limites ou da janela | 3 |
| `PREFLIGHT_FAILED` | `PreflightError`: verificação anterior à execução falhou | 4 |
| `EXTERNAL_TOOL_ERROR` | `ExternalToolError`: ferramenta externa (ZAP, Docker) indisponível ou com resposta inválida | 5 |
| `TARGET_ERROR` | `TargetError`: o alvo respondeu de forma que impede o prosseguimento | 6 |
| `CLEANUP_FAILED` | `CleanupError`: a limpeza falhou | 7 |
| `INTERNAL` | Erro interno inesperado | 10 |
| `INTERRUPTED` | Interrompido pelo usuário (Ctrl+C) | 130 |

Os códigos 6 e 7 e o 130 vieram da rodada de correção de 2026-11-13 (achados A-06 e A-19), registrada no [ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md). Até então `TargetError` e `CleanupError` usavam o 5, que o desenho reserva à falha de ferramenta externa.

Hoje só `CONFIG_ERROR` e `INTERNAL` podem ser produzidos por um comando que existe (`hdast version` e erro de uso). Os demais são levantados pelo domínio, mas nenhum comando os alcança ainda.

## Regras do contrato

- `stdout` carrega só o resultado. Logs vão para `stderr`.
- Mudança incompatível no envelope exige ADR, atualização do teste de contrato e sobe a versão maior do projeto.
- Flags só reduzem escopo e limites, nunca ampliam.

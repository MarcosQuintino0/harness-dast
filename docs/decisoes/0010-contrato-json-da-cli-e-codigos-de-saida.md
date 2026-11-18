# 0010. Contrato JSON da CLI e códigos de saída

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** AD-08

## Contexto

As skills do agente dependem do formato de saída da CLI. Sem contrato, qualquer mudança de texto quebra o agente em silêncio. O uso no CI exige códigos de saída estáveis.

## Decisão

Vamos fixar o contrato da CLI.

- Todo comando aceita `--json` e escreve **um envelope** com `schema_version` em `stdout`. A opção vale **antes ou depois** do subcomando (`hdast --json version` e `hdast version --json`); a CLI pré-detecta a flag, de modo que um erro de uso também sai em JSON. Campos comuns: `schema_version`, `ok`, `run_id` e, em falha, `error` com `code`, `message` e `hint`.
- Logs vão para `stderr` e para arquivo; `stdout` é reservado ao resultado.
- Um único tratador em `cli/app.py` converte `HarnessError` em envelope e código de saída.
- Códigos de saída: `0` sucesso; `1` achados acima do limiar; `2` erro de uso ou configuração; `3` violação de escopo ou janela fechada; `4` preflight falhou; `5` falha de ferramenta externa (`ExternalToolError`); `6` falha do alvo (`TargetError`); `7` falha de limpeza (`CleanupError`); `10` erro interno inesperado; `130` interrompido pelo usuário (Ctrl+C), com `error.code` `INTERRUPTED`.
- `hdast` sem argumentos imprime a ajuda e sai com `0`; com `--json` e sem comando, devolve um envelope de erro de uso (`CONFIG_ERROR`, saída `2`), porque a ajuda em texto sujaria o `stdout` do modo JSON.

## Alternativas consideradas

- **Servidor MCP próprio.** Mais integrado ao agente, mais uma peça para manter. Pode vir depois, sobre os mesmos casos de uso.
- **Saída só em texto.** Frágil para o agente e para o CI.

## Consequências

- Exige testes de contrato (envelope e códigos de saída).
- Mudança incompatível no envelope sobe a versão maior do projeto, exige ADR novo e atualização do teste de contrato.
- Os campos de sucesso de cada comando são definidos por marco. Novos valores de `error.code` são acrescentados por marco.
- Habilita o uso no CI sem mudança.
- A lista de valores de `error.code` está em [../reference/cli.md](../reference/cli.md#valores-de-errorcode).
- Detalhes: [../reference/exit-codes.md](../reference/exit-codes.md) e [../reference/cli.md](../reference/cli.md).

## Histórico

- **2026-11-13, emenda antes do primeiro commit.** Este ADR foi aceito em 2026-11-13, mas nada do repositório havia sido commitado; por isso ele foi emendado no lugar, em vez de substituído por um ADR novo. A revisão de QA independente ([../reviews/2026-11-13-qa-m1-m2.md](../reviews/2026-11-13-qa-m1-m2.md), achados A-03, A-06, A-12 e A-19) levou a quatro mudanças: (1) `--json` aceito também depois do subcomando; (2) `TargetError` e `CleanupError` deixam de usar o código `5` e ganham `6` e `7`, para que `5` signifique só falha de ferramenta externa; (3) novo código `130` com `INTERRUPTED`; (4) `hdast` sem argumentos sai com `0`. A partir do primeiro commit com este ADR, qualquer mudança de rumo exige ADR novo.

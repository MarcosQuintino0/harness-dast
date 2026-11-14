# Limpeza de dados: quem faz o quê

O `probe` e a varredura criam registros sintéticos no ambiente de teste. Apagá-los é a única ação **destrutiva** do harness, e por isso é uma tarefa **humana**. Referência técnica completa: [operations/cleanup.md](../operations/cleanup.md), [reference/cleanup.md](../reference/cleanup.md) e [ADR 0025](../adr/0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md).

## Quem faz cada coisa

| Quem | O que |
| --- | --- |
| Pessoa do time do produto | Escreve e revisa o script SQL (`DELETE` amarrado ao que a execução criou). Define `allowed_tables` e `max_rows`. Cria o usuário de banco só da limpeza (`SELECT` e `DELETE` nas tabelas permitidas) |
| QA (você) | Roda `hdast cleanup --dry-run`, confere as contagens e, se estiverem certas, roda sem `--dry-run` e confirma digitando |
| Agente de IA | **Nada.** Não escreve, não altera, não executa. No máximo sugere que você rode a limpeza. As permissões do Claude Code negam `hdast cleanup` ao agente (camada de conveniência) e a CLI recusa confirmar sem terminal interativo (camada de verdade) |
| CLI | Confere execução e autorização, passa o script por um portão de SQL, abre uma transação, mostra as contagens e só faz `COMMIT` com a sua confirmação |

## Preparar a pasta `cleanup/`

O `hdast init <produto>` **não** cria a pasta `cleanup/`: a limpeza é opcional. Se a carta prevê limpeza, crie o produto com `hdast init <produto> --with-cleanup` (README e exemplo do script, para a pessoa do time do produto escrever o `cleanup.sql`). Se o produto já existe, copie `products/_template/cleanup/` à mão. Sem limpeza, remova também o bloco `cleanup` do `target.yml`.

## Passo a passo

1. A varredura termina e o `run.json` traz o `cleanup_command`.
2. Defina as variáveis de ambiente dos segredos da limpeza (DSN, usuário e senha de banco: os nomes estão no bloco `cleanup` do `target.yml`).
3. **Simule.** Não apaga nada: roda os comandos, mostra as contagens e desfaz tudo (`ROLLBACK`). Pode rodar sem terminal interativo.

   ```bash
   uv run hdast cleanup <produto> --run <run_id> --dry-run
   ```

4. Confira: tabelas, contagens por comando e total contra o teto `max_rows`. Número muito acima do esperado: **pare** e chame quem escreveu o script.
5. **Apague de verdade**, em um terminal interativo:

   ```bash
   uv run hdast cleanup <produto> --run <run_id>
   ```

   A CLI mostra o plano e pede que você **digite o nome do produto**. Só então confirma.
6. Guarde `runs/<run_id>/cleanup.json` e `cleanup-audit.jsonl`.

## Por que a confirmação é só no terminal

Qualquer coisa que um agente consiga passar (flag, arquivo, variável de ambiente, token no `stderr`) o agente também consegue passar sem que ninguém decida. Por isso não existe atalho: sem terminal interativo, `hdast cleanup` sem `--dry-run` se recusa (saída `2`). O limite honesto: um pseudoterminal ainda cumpriria; o que fecha isso são as permissões do Claude Code e os privilégios do usuário de banco (só `SELECT` e `DELETE`, só nas tabelas de teste).

## Sem limpeza

Se o ambiente é descartável ou recriado depois de cada execução, a carta de autorização diz isso, o perfil fica **sem** bloco `cleanup` e o `run` não mostra comando de limpeza.

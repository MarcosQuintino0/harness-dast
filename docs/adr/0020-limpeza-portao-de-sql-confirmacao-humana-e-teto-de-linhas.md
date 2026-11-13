# 0020. Limpeza: portão de SQL, confirmação humana e teto de linhas

- **Status:** Proposto
- **Data:** 2026-11-13
- **Origem:** M5 (`hdast cleanup`); detalha os ADR [0009](0009-segredos-por-referencia.md), [0010](0010-contrato-json-da-cli-e-codigos-de-saida.md) e [0011](0011-limpeza-por-sql-oracle-com-python-oracledb.md)

## Contexto

A limpeza é a única parte do sistema que apaga dados de propósito, em ambiente de teste que outros times dividem. O [ADR 0011](0011-limpeza-por-sql-oracle-com-python-oracledb.md) decidiu que o SQL é escrito por pessoa, roda em transação e só confirma com aceite humano, mas deixou em aberto: o que a CLI confere no SQL, como a confirmação é dada quando não há terminal, como a conexão é guardada e o que impede um script errado de apagar demais.

## Decisão

Vamos implementar `hdast cleanup <produto> --run <run_id> [--dry-run] [--confirm <token>]` com estas travas, todas em código testado (`domain/cleanup_*.py`, `application/cleanup.py`).

**Portão de SQL (defesa em profundidade, não prova).** O script é lido, nunca gerado. Um analisador léxico conservador (comentários, textos, `q'[...]'`, `;`) e uma verificação sintática aceitam SÓ `DELETE FROM <tabela> WHERE <condição>`, e recusam todo o resto (TRUNCATE, DROP, DDL, MERGE, INSERT, UPDATE, PL/SQL, COMMIT/ROLLBACK, `@`, `&`, aspas duplas, Unicode fora de texto). Além disso:

- a tabela do `DELETE` e as de subconsultas precisam estar em `cleanup.allowed_tables`;
- o `WHERE` precisa ter, ligada por `AND` no nível de cima e sem `OR`, `NOT` nem subconsulta, uma condição de amarração (`coluna = | >= | > <variáveis>`, `LIKE` ou `IN (:a, ...)`) que use variáveis do contrato (`:run_start`, `:run_id`, `:run_tag`, `:account_N`). Assim nenhuma combinação de `OR` com condições extras alarga o `DELETE` para além do que a execução delimita;
- só funções de uma lista fechada, sem efeito colateral; só variáveis do contrato; constantes comparadas entre si (`1 = 1`) são recusadas;
- `UPDATE` fica FORA da V1: um teto de "linhas apagadas" não descreve um `UPDATE`, e ele não tem como ser conferido contra o contrato. Se um produto precisar, é ADR novo.

O texto executado é a lista de fichas aprovadas unidas por espaço, sem comentários: o que roda é exatamente o que foi analisado.

**Transação e tetos.** Uma conexão, uma transação (`SET TRANSACTION READ WRITE NAME 'hdast_cleanup'`, isolamento padrão READ COMMITTED), prazos de conexão (15 s) e de chamada (120 s). `cleanup.max_rows` (obrigatório) limita o total de linhas; passar do teto desfaz e sai com 7. Qualquer erro desfaz e sai com 7, citando o índice e a tabela do comando, nunca os valores de ligação nem o texto do driver (só o código `ORA-nnnnn`).

**Confirmação.** Sempre humana: no terminal, a pessoa digita o nome do produto depois de ver o plano (hash do script, tabelas, contagens). Sem terminal, `--confirm <token>`, onde o token vem de um `--dry-run` anterior da mesma execução: vale 10 minutos, uma vez, e se amarra a produto, execução, hash do script e ao total de linhas visto (apagar mais que isso desfaz). O token é escrito só no stderr de quem operou; não entra no JSON, no `cleanup.json` nem na auditoria, e em disco fica só o SHA-256 dele. Recusa da pessoa (ou ausência de confirmação) desfaz e sai com 0 e `status: declined`.

**Limite honesto.** O token é controle PROCEDIMENTAL: quem tem o shell da pessoa (um agente, por exemplo) pode rodar o próprio `--dry-run` e ler o stderr. A proteção real é a soma de: a regra de skill que proíbe o agente de rodar `cleanup`, o usuário de banco só com `SELECT` e `DELETE` nas tabelas de teste, e o portão.

**Pré-condições.** A execução existe, é do produto e terminou (`finished_at` no manifesto, ou passado o `limits.max_duration_minutes` dela, para o caso de uma execução interrompida que nunca gravou o fim). A autorização do perfil precisa estar válida; a janela de execução NÃO é exigida, porque a limpeza não envia nada ao alvo e deixar lixo até a próxima janela é pior.

**Conexão e perfil (aditivo na schema v1).** `cleanup.connection` passa a ser o DSN (`host:porta/serviço`); `cleanup.user` e `cleanup.password` são `secret_ref` próprios, sem senha embutida em URL. Novos campos opcionais no esquema, obrigatórios para a limpeza rodar: `allowed_tables`, `max_rows`, `user`, `password`; opcional: `db_schema` (`ALTER SESSION SET CURRENT_SCHEMA`, para quando o usuário da limpeza não é o dono das tabelas).

**Trilha.** `runs/<run_id>/cleanup.json` (hash, comandos, tabelas, contagens, método de confirmação, confirmado ou desfeito, tempos) e `cleanup-audit.jsonl` (linhas `started` antes de conectar e `finished`). Arquivo separado de `audit.jsonl` para não misturar linhas de formato diferente.

**Dependência.** `oracledb` (python-oracledb) 26.1.0, licença UPL-1.0 OU Apache-2.0, mantida pela Oracle, modo thin (sem cliente Oracle). Traz `cryptography` como dependência transitiva. É proibida no `domain` pelo import-linter.

## Alternativas consideradas

- **Aceitar qualquer SQL e confiar na revisão humana.** Um erro de digitação (`DELETE` sem `WHERE`) apagaria a tabela inteira; o portão custa pouco e barra o pior.
- **Analisador de SQL completo (sqlglot).** Dependência grande com dialeto Oracle imperfeito; um subconjunto conservador e recusar o que não entende é mais seguro que interpretar tudo.
- **Token HMAC sem estado.** Não dá uso único sem guardar estado; o arquivo com o hash em `runs/` resolve e é auditável.
- **`COMMIT` pelo script.** Tira da CLI o controle da transação e da confirmação.
- **URL de conexão com senha embutida.** Exporia a senha em mensagem e log.

## Consequências

- Só Oracle e só `DELETE` na V1; scripts com PL/SQL ou `UPDATE` precisam de ADR novo.
- O portão não conhece a semântica das colunas: uma amarração errada (`ID >= :run_start`) passa. Revisão humana do script e privilégios mínimos do banco continuam necessários.
- Teste de integração contra Oracle Free real (`tests/integration/test_cleanup_oracle.py`, marcador `integration`) prova a transação, o `ROLLBACK` e as contagens.
- O código de saída 7 passa a ser produzido (estava reservado).
- Quem opera passa a precisar de um terminal para confirmar, ou do fluxo `--dry-run` seguido de `--confirm`.

# Variáveis de ligação do script de limpeza

Contrato entre o script SQL de limpeza (escrito por uma pessoa do time do produto), o `hdast cleanup` e o `probe`. O código que
impõe o contrato é `src/harness_dast/domain/cleanup_binds.py`; o analisador do script está em `domain/cleanup_*.py`. Procedimento humano: [guia de limpeza](../guides/limpeza-de-dados.md); política: [operations/cleanup.md](../operations/cleanup.md) e
[ADR 0020](../adr/0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md). Modelo do script:
[`products/_template/cleanup/`](../../products/_template/cleanup/README.md). Exemplo que roda no Oracle da Clínica Piloto:
[`lab/pilot/cleanup/cleanup.sql`](../../lab/pilot/cleanup/cleanup.sql).

## Variáveis que a CLI fornece

O script usa **somente** estas variáveis, sempre como variável de ligação (`:nome`), nunca concatenadas ao texto:

| Variável | Tipo | De onde vem | Para que serve |
| --- | --- | --- | --- |
| `:run_start` | `TIMESTAMP` em UTC, sem fuso | `started_at` do `manifest.json` da execução, convertido para UTC | Amarrar o `DELETE` ao que foi criado **durante** a execução (`CREATED_AT >= :run_start`). A aplicação precisa gravar a data de criação em UTC |
| `:run_id` | texto | Identificador completo da execução (`2026-11-13T07-46-37Z-clinica-piloto-cfd4`) | Produtos que gravam o id da execução num campo próprio |
| `:run_tag` | texto (4 a 8 hex) | O sufixo do `run_id`; é a etiqueta embutida nos valores únicos que o `probe` gera (e-mail, código, CRM, CPF...) | Achar o que a execução criou quando o produto não guarda quem criou |
| `:account_1` a `:account_N` | texto | Usuário de login de cada conta de `auth.accounts`, **na ordem do perfil**, resolvido de `secret_ref` pela CLI. `N` é a quantidade de contas | Amarrar o `DELETE` às contas de teste (`CREATED_BY IN (:account_1, :account_2, ...)`) |

Regras que o analisador impõe antes de abrir a conexão:

- A condição de amarração compara uma **coluna** da tabela com uma variável: pseudo-colunas e funções sem argumento (`SYSDATE`, `SYSTIMESTAMP`, `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `LOCALTIMESTAMP`, `ROWNUM`, `USER`...) e literais não valem.
- Faixa (`>=`, `>`) só contra `:run_start`; `:run_id`, `:run_tag` e `:account_N` (texto) só com `=`, `IN` ou `LIKE`.

- Qualquer outro nome (inclusive `:account_0`, `:account_N+1` para `N` contas e variáveis posicionais como `:1`) é recusado.
- Os nomes são sem diferença de maiúsculas.
- Os **valores** nunca saem em tela, log, trilha de auditoria nem relatório: só os nomes. Os nomes dos usuários são segredos de conta.
- O comando só recebe as variáveis que usa; o driver recusa as que sobram.

`:test_account`, que o modelo antigo citava, **não existe**. Quem tem um único usuário de teste usa `:account_1`.

## Como o `probe` ajuda a limpeza

O `probe` marca o que cria de forma rastreável, e o script pode procurar a marca:

- o `:run_tag` aparece nos valores `unique: true` de `alphanumeric`, `email` e `uri` (texto `etiqueta` + contador) e, em prefixo, nos
  numéricos (`numeric`, `br.cpf`, `br.cnpj`, `br.cns`, `br.phone`, `br.cep`, `br.crm`; veja a tabela de `unique` em
  [data-rules-yml.md](data-rules-yml.md));
- `started_at` do manifesto é o `:run_start`; os registros criados pelo `probe` têm criação posterior;
- com `auth.account_map`, as contas que de fato criaram dados são as do mapa; `manifest.json` lista só as usadas (`accounts`), mas
  as variáveis `:account_N` seguem a ordem de **todas** as contas de `auth.accounts`.

## Exemplo

```sql
DELETE FROM RECEITA
 WHERE CREATED_AT >= :run_start
   AND CREATED_BY IN (:account_1, :account_2, :account_3, :account_4);
```

Sem `COMMIT`: quem confirma é a CLI, depois do aceite de uma pessoa.

## Como funciona

1. A CLI confere a execução (existe, é do produto, já terminou) e a autorização do perfil. A janela de execução **não** é exigida: a limpeza não envia nada ao alvo, e deixar lixo até a próxima janela é pior.
2. Lê o script (dentro da pasta do produto, no máximo 64 KiB, UTF-8) e calcula o SHA-256.
3. O portão de SQL aprova ou recusa o script **inteiro**, antes de qualquer conexão.
4. Resolve os segredos (`secret_ref`), conecta com `python-oracledb` em modo thin (sem cliente Oracle) e abre **uma** transação.
5. Roda os comandos na ordem, anota as linhas afetadas por comando e confere os tetos.
6. Mostra o plano (hash, tabelas, contagens) e só faz `COMMIT` depois da sua confirmação. Qualquer erro, recusa ou ausência de confirmação faz `ROLLBACK`.


## Em `--json`

`data` traz `status` (`dry_run`, `committed`, `declined`), `statements` (índice, tabela e linhas por comando), `total_rows`, `max_rows`, `script_sha256`, `tables`, `confirmation_method` (`none`, `interactive`, `token`), `committed`, `rolled_back` e os tempos. `token_expires_at` é um campo reservado que a CLI não usa (veja o ADR 0025). Os valores das variáveis de ligação e as credenciais nunca aparecem.

## O que fica gravado

Em `runs/<run_id>/`:

- `cleanup.json`: o relatório acima, atômico.
- `cleanup-audit.jsonl`: só acréscimo; uma linha `started` (antes de conectar) e uma `finished` por tentativa. Um `started` sem `finished` indica processo morto no meio.
- `cleanup-confirmation.json`: resíduo do mecanismo de token que a CLI não expõe mais (**só o SHA-256**); o `--dry-run` ainda o grava e nada o lê pela CLI.

## Códigos de saída

| Código | Quando |
| --- | --- |
| `0` | `--dry-run` feito; limpeza confirmada; ou recusada pela pessoa (`status: declined`, nada apagado) |
| `2` | Uso ou configuração: perfil sem os campos da limpeza, script recusado pelo portão, execução desconhecida ou em andamento, segredo ausente, sem terminal interativo (limpeza de verdade) |
| `3` | Autorização do perfil vencida |
| `7` | Falha na limpeza: erro do banco (a mensagem traz o **índice do comando**, a tabela e só o código `ORA-nnnnn`), teto de linhas excedido, falha ao conectar ou ao confirmar. Tudo foi desfeito, exceto uma falha *ao confirmar*, em que o estado é incerto: confira o banco |

## O que o portão garante (e o que não garante)

**É defesa em profundidade, não prova.** O que o analisador sintático (`domain/cleanup_*.py`) garante, por comando: é um `DELETE FROM <tabela> WHERE ...`, a tabela está em `allowed_tables`, só há variáveis do contrato, e o `WHERE` tem uma condição de amarração à execução ou às contas de teste (por exemplo `CREATED_AT >= :run_start` ou `CREATED_BY IN (:account_1, ...)`), ligada por `AND` no nível de cima, sem `OR`, `NOT` nem subconsulta. O texto que roda é o que foi analisado, sem comentários.

**Recusa**, entre outros: `DELETE` sem `WHERE` (inclusive com o `WHERE` dentro de comentário), `WHERE 1 = 1` e comparações de constantes, `TRUNCATE`, `DROP`, `ALTER`, `CREATE`, `GRANT`, `MERGE`, `INSERT`, `UPDATE` (não suportado na V1), blocos PL/SQL (`BEGIN`, `DECLARE`, a barra `/`), `EXECUTE IMMEDIATE`, `COMMIT`, `ROLLBACK`, `SAVEPOINT` (a transação é da CLI), link de banco (`@`), `&variável`, identificadores entre aspas, texto ou comentário sem fechar, letras que imitam ASCII (cirílico, largura total), tabela fora de `allowed_tables` (também em subconsulta e `JOIN`), esquema não listado, variável fora do contrato e função que não seja de uma lista fechada e sem efeito colateral.

**A amarração só vale se compara uma COLUNA da tabela com uma variável permitida** (ADR 0025). Pseudo-colunas e funções sem argumento que não dependem da linha (`SYSDATE`, `SYSTIMESTAMP`, `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `LOCALTIMESTAMP`, `ROWNUM`, `ROWID`, `LEVEL`, `USER`, `UID`, `SESSIONTIMEZONE`, `DBTIMEZONE`, `DUAL`...) e literais nunca contam: `SYSDATE >= :run_start` é verdadeira para toda linha e é recusada. Faixa (`>=`, `>`) só vale contra `:run_start` (data); as variáveis de texto (`:run_id`, `:run_tag`, `:account_N`) só com `=`, `IN` ou `LIKE`, porque comparar texto por ordem alfabética casaria quase toda linha. O que o portão não reconhece, recusa.

**Não garante:**

- Que a amarração faça sentido para as colunas do produto: `ID >= :run_start` passaria. Quem escreve e revisa o script é a pessoa do time do produto.
- Funções de usuário sem parênteses (uma constante de pacote, `SEQ.NEXTVAL` numa subconsulta): o portão só enxerga função quando há `(`. O usuário de banco com só `SELECT` e `DELETE` é o que limita isso.
- Nada sobre o que o banco faz por baixo: gatilhos (`TRIGGER`), visões, sinônimos, `ON DELETE CASCADE` e chaves estrangeiras podem apagar ou recusar além do que o script diz (o `max_rows` conta só as linhas dos próprios comandos).
- Que o usuário de banco não tenha privilégios demais: o portão não os vê.
- Que o ambiente seja de testes: confira o DSN do perfil.

### Confirmação: o que a CLI impede e o que não impede

A confirmação é **digitada** por uma pessoa num terminal interativo. Um agente que roda a CLI pela ferramenta de shell não tem terminal e a limpeza de verdade é recusada; a mensagem de recusa não ensina nenhum atalho, e o `--dry-run` (que o agente pode rodar) não produz nada que sirva para confirmar. Antes do ADR 0025 a confirmação "humana" era um token no stderr do `--dry-run`, que o próprio agente lia e repassava; isso acabou.

Limite honesto: um agente com poder de abrir um pseudoterminal na sua máquina e digitar o nome do produto ainda cumpriria a confirmação. O que fecha isso é o que está fora da CLI: (1) a regra de skill e a permissão do Claude Code que negam `hdast cleanup` (camada 0 de conveniência implementada no M6); (2) o usuário de banco com só `SELECT` e `DELETE` nas tabelas de teste; (3) o ambiente de testes, com dados sintéticos.

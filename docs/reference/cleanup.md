# Variáveis de ligação do script de limpeza

Contrato entre o script SQL de limpeza (escrito por uma pessoa do time do produto), o `hdast cleanup` e o `probe`. O código que
impõe o contrato é `src/harness_dast/domain/cleanup_binds.py`; o analisador do script está em `domain/cleanup_*.py`. Operação do
comando, confirmação humana e portão de SQL: [operations/cleanup.md](../operations/cleanup.md) e
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

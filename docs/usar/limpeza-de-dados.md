# Limpeza de dados: quem faz o quê

O `probe` e a varredura criam registros sintéticos no ambiente de teste. Apagá-los é a única ação **destrutiva** do harness, e por isso é uma tarefa **humana**. Referência técnica completa: [../como-funciona/operacao/cleanup.md](../como-funciona/operacao/cleanup.md), [../referencia/cleanup.md](../referencia/cleanup.md) e [ADR 0025](../decisoes/0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md).

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

## Preparação detalhada pela pessoa responsável

### 1. Prepare o perfil e o script

Bloco `cleanup` do `target.yml` (campos novos em negrito; veja o [exemplo completo](../referencia/target-yml.md)):

```yaml
cleanup:
  type: oracle_sql
  script: ./cleanup/cleanup.sql
  connection: { secret_ref: "env:AGENDA_ORACLE_DSN" }      # DSN: host:porta/serviço, sem usuário nem senha
  user: { secret_ref: "env:AGENDA_ORACLE_LIMPEZA_USUARIO" }   # usuário de banco só da limpeza
  password: { secret_ref: "env:AGENDA_ORACLE_LIMPEZA_SENHA" }
  allowed_tables: [RECEITA, CONSULTA, PACIENTE]             # as únicas tabelas que o script pode tocar
  max_rows: 500                                             # teto de linhas apagadas no total
  db_schema: AGENDA                                         # opcional: dono das tabelas, se não for o usuário
  requires_confirmation: true
```

`user`, `password`, `allowed_tables` e `max_rows` são opcionais no esquema (um perfil antigo continua válido), mas **sem eles a limpeza se recusa a rodar** e diz o que falta. Os valores de `allowed_tables` e `max_rows` vêm da pessoa dona do produto, não do agente. A senha nunca entra no DSN: três referências separadas.

O script segue as regras de [`products/_template/cleanup/`](../../products/_template/cleanup/README.md) e o contrato de variáveis: `:run_start` (início da execução, UTC), `:run_id`, `:run_tag` (a etiqueta embutida nos valores únicos gerados) e `:account_1` a `:account_N` (usuários das contas de teste, na ordem do perfil). Exemplo real, que roda no Oracle da Clínica Piloto: `lab/pilot/cleanup/cleanup.sql`.

### 2. Crie o usuário de banco da limpeza

O portão é defesa em profundidade; **a proteção de verdade é o que esse usuário pode fazer**. Como DBA do ambiente de **testes**:

```sql
CREATE USER hdast_limpeza IDENTIFIED BY "<senha-forte-gerada>";
GRANT CREATE SESSION TO hdast_limpeza;
-- Só as tabelas de teste listadas em allowed_tables, e só estes dois privilégios:
GRANT SELECT, DELETE ON agenda.receita  TO hdast_limpeza;
GRANT SELECT, DELETE ON agenda.consulta TO hdast_limpeza;
GRANT SELECT, DELETE ON agenda.paciente TO hdast_limpeza;
-- Nada de DROP ANY TABLE, TRUNCATE, CREATE, INSERT, UPDATE, papéis (DBA, RESOURCE, CONNECT)
-- nem acesso a outros esquemas.
```

- **`SELECT` é necessário.** No Oracle 23ai, um `DELETE ... WHERE coluna = ...` sem `SELECT` na tabela falha com `ORA-41900`; também as subconsultas do script leem as tabelas.
- Privilégio é por tabela, não por linha: com `DELETE` na tabela, o usuário **consegue** apagar tudo dela. É por isso que o script, o portão e o teto `max_rows` existem, e por isso a lista de tabelas deve ser a mínima. Para limite por linha no próprio banco, use uma visão restrita ou Virtual Private Database do Oracle (fora do escopo da CLI).
- Guarde as três referências em variáveis de ambiente (ou no `.env` ignorado pelo git). Nunca no perfil, nunca no script.


## Quando a limpeza recusa

| Mensagem (resumo) | O que fazer |
| --- | --- |
| "A limpeza exige campos que o perfil não tem: cleanup.user, ..." | Peça à pessoa dona do produto os valores e preencha o bloco `cleanup` (preparação detalhada acima). |
| "A tabela X não está em cleanup.allowed_tables" | Se X realmente deve ser limpa, a pessoa dona do produto a inclui na lista. Senão, corrija o script. |
| "Comando N do script de limpeza recusado: DELETE sem WHERE" | Adicione o `WHERE` com a amarração. |
| "o WHERE não tem uma condição de amarração" | Inclua, ligada por `AND` e fora de parênteses com `OR`, uma condição entre uma COLUNA da tabela e uma variável, como `CREATED_AT >= :run_start` ou `CREATED_BY IN (:account_1, ...)`. Pseudo-coluna (`SYSDATE`), literal e faixa contra variável de texto não valem. |
| "a variável de ligação :x não faz parte do contrato" | Use só `:run_start`, `:run_id`, `:run_tag` e `:account_1..N` (N = contas do perfil). |
| "A execução ainda está em andamento" | Espere o `probe` terminar. Uma execução interrompida (sem `finished_at`) vale como terminada depois do prazo `limits.max_duration_minutes` dela. |
| "Sem terminal interativo: a limpeza de verdade não será executada" | Só uma pessoa, num terminal interativo, confirma digitando o nome do produto. |
| "A limpeza apagaria N linhas, acima do teto" | Nada foi gravado. Confira o script e o banco; só aumente `max_rows` com a concordância da pessoa dona do produto. |
| "Erro do banco ao executar o comando (ORA-02292)" | Há linhas filhas: ajuste a ordem do script (filhos antes dos pais). O banco não foi alterado. |
| "Erro do banco ao conectar (ORA-01017 ...)" | Confira usuário, senha e DSN nas variáveis de ambiente. |

## Exemplo de saída da simulação

```text
Limpeza de agenda (execução 2026-11-12T21-04-11Z-agenda-7f3a)
Script SHA-256: c8e0bacddf7211eafcd01dac249c53b2c08734dafaed80534bd590985f592d10
  comando 1: RECEITA -> 3 linha(s)
  comando 2: CONSULTA -> 3 linha(s)
  comando 3: PACIENTE -> 2 linha(s)
Total: 8 linha(s) (teto do perfil: 500)
Estado: SIMULAÇÃO: tudo foi desfeito (ROLLBACK), nada foi apagado
```

A simulação não emite token de confirmação. Confira contagens antes de uma execução real.

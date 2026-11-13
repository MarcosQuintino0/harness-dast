# Limpeza (cleanup)

> Contrato das variáveis de ligação: `docs/reference/cleanup.md`. Guia do operador: `docs/operations/cleanup.md`.

A varredura cria dados no ambiente de teste do produto. A limpeza é o único
ponto do sistema que **apaga dados de propósito**, por isso é o mais
restrito. Decisão: AD-13.

## Regras

1. **O SQL é escrito e revisado por uma pessoa do time do produto.** O agente
   de IA nunca escreve, altera nem executa esse script. Ele pode, no máximo,
   sugerir rodar `hdast cleanup`.
2. **O usuário de banco só pode apagar nas tabelas de teste.** Crie um usuário
   dedicado (`SELECT` e `DELETE` só nas tabelas de `allowed_tables`), sem permissão
   em tabelas de outros times e sem `DROP`, `TRUNCATE` ou DDL. DSN, usuário e senha
   entram no `target.yml` como três `secret_ref: "env:NOME"` (`connection`, `user`,
   `password`); `allowed_tables` e `max_rows` são obrigatórios para rodar. Exemplo
   real: `lab/pilot/cleanup/create-cleanup-user.sql`.
3. **Os comandos se restringem a dados criados pelas contas de teste ou pela
   execução.** Filtre sempre pela conta (`criado_por`) e, quando o campo
   existir, pelo tempo de início da execução (`:run_start`) ou pela etiqueta dos
   valores únicos (`:run_tag`). Nunca um `DELETE` sem `WHERE`.
4. **Use só as variáveis de ligação do contrato**: `:run_start`, `:run_id`,
   `:run_tag` e `:account_1` a `:account_N` (usuários das contas de teste, na
   ordem de `auth.accounts`). Sem concatenar texto no SQL.
5. **A CLI executa dentro de uma transação**, mostra quantas linhas cada
   comando apagaria e **pede confirmação a uma pessoa**. Sem confirmação (ou
   com `requires_confirmation: false`), nada é gravado: a transação sofre
   `ROLLBACK`.
6. O script não contém `COMMIT`; quem confirma é a CLI.
7. O ambiente é compartilhado. Um erro aqui apaga o trabalho de outras
   pessoas. Em dúvida, não rode.

## Arquivos

- `cleanup.sql.example`: exemplo **fictício** e incapaz de apagar algo (os
  `DELETE` estão comentados e há uma guarda que falha). Copie para
  `cleanup.sql` no repositório privado do produto e reescreva.
- `cleanup.sql`: o script real. Não existe neste repositório.

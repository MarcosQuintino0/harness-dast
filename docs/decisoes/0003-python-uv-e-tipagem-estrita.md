# 0003. Python, uv e tipagem estrita

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** AD-03, P-06, P-07, P-13

## Contexto

A CLI precisa de um ecossistema forte em teste de API e segurança (Schemathesis, Faker com CPF e CNPJ) e de uma linguagem que o agente escreva com naturalidade. O mantenedor tem mais experiência em Java do que em Python e precisa da disciplina que a tipagem estática dá.

## Decisão

- Pacote `harness_dast` em layout `src/`, com Python 3.12 ou superior.
- Comando `hdast` (P-13).
- Dependências travadas com `uv.lock`, gerenciadas pelo uv (que equivale a Maven ou Gradle para Python: resolve e trava versões).
- Modelos de dados em pydantic v2.
- Verificação de tipos com **mypy em modo estrito** (P-07).
- Identificadores de código, nomes de arquivo e de comando em **inglês**; documentação, comentários e mensagens ao usuário em **português** (P-06).
- Windows com Docker Desktop é suportado desde o início (P-11).

## Alternativas consideradas

- **Java e TypeScript.** Descartados.
- **Poetry no lugar do uv.** Mais lento, sem ganho aqui.
- **pyright no lugar do mypy.** Mais rápido, mas o mypy tem plugin oficial do pydantic e é o padrão de fato (P-07).

## Consequências

- O mantenedor não domina Python tanto quanto Java. Os padrões de código (veja [CLAUDE.md](../../CLAUDE.md) e [CONTRIBUTING.md](../../AGENTS.md#padrões-de-código)) e os gates de CI existem para compensar isso.
- Dependência nova exige ADR curto e fica travada no `uv.lock`.
- A licença do projeto continua indefinida (P-14); esta decisão não a define.

# Pacote `observability`

Caminho: `src/harness_dast/observability/`. Referência de arquitetura: [../../como-funciona/arquitetura.md](../../como-funciona/arquitetura.md#logs-e-rastreabilidade).

## Responsabilidade

Logs estruturados, redação de dados sensíveis e trilha de auditoria.

| Item | O que é | Marco |
| --- | --- | --- |
| Logger estruturado (structlog) | Logs em JSON no `stderr`. Desenho: `run_id` em todas as linhas e cópia em `runs/RUN_ID/harness.log` | `stderr`: implementado (M1). `run_id` em cada linha e o arquivo `harness.log`: não existem (aberto; a trilha da execução é `audit.jsonl` mais `manifest.json`) |
| Redator central | Processador do structlog que mascara por **nome de chave** (inclui `authorization`, `cookie`, `password`, `token`, `secret`, `api_key` e `senha`), por **segredo registrado** no `SecretRegistry`, por padrão de **JWT** e por **CPF** formatado. Cobre texto, dicionário, lista, tupla, conjunto, `bytes`, pares de cabeçalho `("Authorization", "...")`, exceções e objetos arbitrários (pelo texto que produzem) | Implementado (M1 e rodada de correção de 2026-11-13, achado A-15) |
| Trilha de auditoria `audit.jsonl` | Só de acréscimo: uma linha por requisição enviada ao alvo, com método, URL, status, apelido da conta e componente de origem | Implementado (M3): `application/run_support.py` (`AuditTrail`) |

O `manifest.json` de cada execução (versões do harness e do ZAP, hash do perfil e do Swagger, limites aplicados) é gravado pelo armazém de execuções (`adapters/storage/run_store.py`), não por este pacote.

## Pode importar

Biblioteca padrão, structlog e `domain`.

## Nunca deve

- Importar `application`, `adapters` ou `cli`.
- Gravar segredo, cabeçalho de autenticação ou corpo bruto de resposta sem passar pelo redator.
- Escrever em `stdout`. Logs vão para `stderr` e para arquivo; `stdout` é reservado ao resultado do comando.
- Usar `print`; só `cli/output.py` pode.

## Observação sobre o desenho

O contrato do import-linter em `pyproject.toml` proíbe `observability` de importar `cli`, `application` e `adapters`, e proíbe `domain` e `application` de importar `observability`. Por isso um caso de uso não chama o logger diretamente; o desenho aprovado não detalha como `application` registra eventos (por exemplo por uma porta), e isso é decidido quando o primeiro caso de uso precisar.

## Status

Logger estruturado e processador de redação: implementados (M1). A gravação em `runs/RUN_ID/harness.log` e o `run_id` em cada linha não existem: hoje o log vai só para o `stderr`. Auditoria: implementada (M3), fora deste pacote.

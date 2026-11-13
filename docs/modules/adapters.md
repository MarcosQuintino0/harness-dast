# Pacote `adapters`

Caminho: `src/harness_dast/adapters/`. Decisão: [ADR 0004](../adr/0004-portas-e-adaptadores-em-tres-camadas.md).

## Responsabilidade

Implementar as portas de `application` com tecnologia concreta, um subpacote por tecnologia. Um adaptador traduz: converte o mundo externo em modelos de `domain` e converte exceções de terceiros em `HarnessError` na fronteira.

Subpacotes previstos no desenho aprovado:

| Subpacote | Conteúdo | Marco |
| --- | --- | --- |
| `openapi/` | Carregar, resolver referências e normalizar o OpenAPI | M3 |
| `http/` | Cliente com escopo; estratégias de autenticação | M3 |
| `datagen/` | Catálogo de geradores (básicos e brasileiros) | M3 |
| `secrets/` | Provedor por variável de ambiente | M3 |
| `storage/` | `runs/` no sistema de arquivos | M3 a M5 |
| `zap/` | Cliente da API do ZAP, plano de varredura, mapeamento de alertas | M4 |
| `reporting/` | Relatório em JSON e Markdown | M4 |
| `cleanup/` | Executor do SQL de limpeza (Oracle, python-oracledb) | M5 |

## Pode importar

`domain`, as portas de `application` e bibliotecas de terceiros.

## Nunca deve

- Importar outro adaptador irmão. O que dois adaptadores precisam compartilhar vira modelo de `domain`.
- Importar `cli`.
- Tomar decisão de negócio (escopo, unicidade, severidade, fingerprint).
- Deixar exceção de terceiros (`httpx`, ZAP, driver Oracle) subir para os casos de uso.
- Incluir segredo ou corpo bruto de resposta em mensagem de erro.

## Convenções

- Dependência nova de terceiros exige ADR ([CONTRIBUTING.md](../../CONTRIBUTING.md)).
- Adaptadores não têm piso de cobertura de linha; têm a obrigação de um teste de integração ou de contrato. Todo adaptador de uma porta passa na suíte de contrato dessa porta.

## Status

Planejado. Nenhum adaptador existe na fundação do M1; o pacote é só o esqueleto. Veja a [tabela de status](../roadmap.md#tabela-de-status).

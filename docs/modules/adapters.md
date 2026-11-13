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

Implementado no M2 ([ADR 0015](../adr/0015-portas-do-perfil-e-carregador-de-yaml.md)); o restante é planejado (veja a [tabela de status](../roadmap.md#tabela-de-status)).

| Módulo | Porta | Conteúdo |
| --- | --- | --- |
| `storage/strict_yaml.py` | (função usada pelo repositório) | Leitor de YAML sobre `yaml.SafeLoader`: recusa âncora, alias, `<<`, chave repetida ou não textual, tag fora do esquema básico e aninhamento acima de 40 níveis; erros só com linha e coluna |
| `storage/product_paths.py` | (auxiliar) | Valida o nome do produto (slug, sem nomes reservados do Windows) e resolve a pasta, exigindo que fique diretamente dentro de `products_dir` mesmo com links simbólicos |
| `storage/profile_repository.py` | `ProfileRepository` | `FileProfileRepository`: lê `target.yml` (até 256 KiB, UTF-8, BOM aceito), valida com `ProductProfile.from_data`, confere `product` contra o nome da pasta e que `openapi` e `cleanup.script` ficam dentro da pasta do produto; `missing_files` só verifica existência |
| `storage/product_scaffolder.py` | `ProductScaffolder` | `FileProductScaffolder`: copia `products/_template` para a pasta nova, sem sobrescrever; localiza o modelo a partir do próprio arquivo (`default_template_dir`, raiz do repositório), o que vale para `uv run` e instalação editável |
| `system_clock.py` | `Clock` | `SystemClock`: hora atual em UTC |

`storage/` hoje só lê perfis e cria pastas de produto; `runs/` (arquivos de execução) chega no M3 a M5. O `system_clock.py` fica na raiz de `adapters/` por não ser uma tecnologia de armazenamento nem pertencer a outro subpacote.

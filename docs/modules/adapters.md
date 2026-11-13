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

Implementado no M3 ([ADR 0018](../adr/0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md)):

| Módulo | Porta | Conteúdo |
| --- | --- | --- |
| `http/target_client.py` | `TargetClient` | `HttpxTargetClient`: só envia `ApprovedRequest`; rotas `zap` (pelo proxy do ZAP) e `auth` (direta ou por `HDAST_AUTH_PROXY_URL`); `trust_env=False`; sem seguir redirecionamento; tempo limite; corpo lido até 256 KiB; TLS verificado por padrão; cookies por conta |
| `zap/api_client.py` | `ZapControl` | `ZapApiClient`: versão, sessão nova, contexto, remoção de regras `hdast-` do Replacer; chave no cabeçalho `X-ZAP-API-KEY`; todo erro vira `ExternalToolError` com dica |
| `secrets/env_provider.py` | `SecretProvider` | `EnvSecretProvider`: lê a variável de ambiente; ausente ou vazia vira `None` |
| `storage/run_store.py` | `RunStore` | `FileRunStore`: `audit.jsonl` só de acréscimo com `fsync`; `manifest.json` e `probe.json` atômicos; `run_id` revalidado |
| `storage/product_documents.py` | `ProductDocuments` | `data-rules.yml` e `flows.yml` pelo leitor de YAML endurecido; SHA-256 dos arquivos de entrada |
| `openapi/spec_loader.py` | `SpecLoader` | `FileSpecLoader`: delega a `load_spec` com o caminho já conferido |
| `system_runtime.py` | `Sleeper`, `EntropySource` | `SystemSleeper`, `SystemEntropy` |

Os testes dos adaptadores `http` e `zap` rodam contra um servidor HTTP real em 127.0.0.1 (o ZAP é um falso com as formas de resposta do spike); contra o ZAP real, não. O `system_clock.py` fica na raiz de `adapters/` por não ser uma tecnologia de armazenamento nem pertencer a outro subpacote.

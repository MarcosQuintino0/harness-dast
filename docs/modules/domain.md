# Pacote `domain`

Caminho: `src/harness_dast/domain/`. Decisão: [ADR 0004](../adr/0004-portas-e-adaptadores-em-tres-camadas.md).

## Responsabilidade

Regras e modelos puros do negócio: o que é escopo, perfil, achado, regra de dados, execução e erro. Toda decisão sobre escopo, unicidade, severidade ou fingerprint mora aqui e em nenhum outro lugar.

## Módulos

Todos puros: sem I/O, sem relógio e sem aleatoriedade (o instante e o sufixo do `RunId` entram por argumento). Duas exceções literais, registradas no [ADR 0012](../adr/0012-dependencias-tzdata-e-pyyaml.md): `window.py` usa `zoneinfo`, que lê o banco de fusos do disco, e `profile_errors.py` importa `pydantic_core`, dependência do pydantic.

### Existem

| Módulo | Contrato em uma linha | Marco |
| --- | --- | --- |
| `errors.py` | Hierarquia `HarnessError` (`ConfigError`, `ScopeViolation`, `PreflightError`, `ExternalToolError`, `TargetError`, `CleanupError`) com `code`, `message`, `hint` e o código de saída de cada tipo | M1 |
| `host.py` | Converte um host para a forma canônica (minúsculas, punycode, IP sem ambiguidade) e recusa IP em formato decimal, hex ou octal, IPv6 que embute IPv4, zona IPv6 e metadados da nuvem; informa se o host é local (`is_local`) | M2 |
| `urlnorm.py` | Normaliza método e URL de saída para a forma sobre a qual o escopo decide; qualquer ambiguidade (credenciais, `..`, dupla codificação, `;`, ponto ou espaço finais) é `ScopeViolation`; resolve `Location` de redirecionamento | M2 |
| `pathpattern.py` | Valida, casa e compara padrões de caminho com `*` (um segmento) e `**` (zero ou mais); `covers` diz, de forma conservadora, se um padrão cobre outro | M2 |
| `scope.py` | `ScopeRule`, `Scope`, `OutboundRequest` e `ScopeGuard`: recusa tudo que não casa host, esquema, porta, caminho e método de uma regra, ou que casa `deny_paths` (a negação vence) | M2 |
| `window.py` | `ExecutionWindow` (gramática compacta `seg-sex 20:00-06:00 America/Sao_Paulo`, fuso IANA, início igual ao fim recusado) e `Authorization` (`valid_until` inclusivo em UTC); recebem o instante por argumento e recusam instante sem fuso | M2 |
| `overrides.py` | `ScopeOverride`, `LimitsOverride`, `narrow_scope` e `narrow_limits`: aplicam o que o usuário pediu por flag e devolvem algo igual ou menor, ou `ConfigError`; nunca ampliam e não alteram os argumentos | M2 |
| `run.py` | `RunId` (ordenável, seguro como nome de pasta, instante e sufixo injetados) e `RunLimits` com os tetos absolutos de carga | M2 |
| `secret_ref.py` | `ProfileModel` (base congelada, sem campo extra, sem eco do valor recebido) e `SecretRef` (`env:NOME`; segredo literal não passa) | M2 |
| `auth.py` | `PasswordLoginAuth` (`login_password`), `ApiKeyAuth` (`api_key`), contas com apelido único e `AuthConfig` | M2 |
| `profile.py` | `ProductProfile`, `Environment`, `ProfileScope`, `CleanupConfig`; `from_data` valida o perfil inteiro e confere que a `base_url` e o login estão no escopo; `ensure_runnable` confere autorização e janela | M2 |
| `profile_errors.py` | Converte o erro de validação do pydantic em `ConfigError` em português, por caminho de campo, sem repetir o valor recebido | M2 |

A referência campo a campo do perfil está em [../reference/target-yml.md](../reference/target-yml.md).

### Planejados

| Módulo | Conteúdo | Marco |
| --- | --- | --- |
| `run.py` (ampliação) | `RunManifest` | M5 |
| `api_model.py` | `Operation`, `Parameter`, `Constraint` (OpenAPI normalizado) | M3 |
| `datagen.py` | `FieldRule`, `GeneratorSpec` | M3 |
| `flow.py` | Dependência produtor-consumidor e ordenação | M3 |
| `finding.py` | `Finding`, `Evidence`, `Severity`, `Fingerprint` | M4 |

O desenho dos módulos planejados é ilustrativo até o marco correspondente. A distribuição por marco segue o [roadmap](../roadmap.md).

## Pode importar

Somente a biblioteca padrão e pydantic.

## Nunca deve

- Fazer I/O: rede, arquivos, banco, variáveis de ambiente.
- Importar `httpx`, ZAP, `application`, `adapters`, `cli`, `config` ou `observability`.
- Ler o relógio ou gerar aleatoriedade diretamente. Relógio e aleatoriedade entram por parâmetro.
- Ter variável de módulo mutável ou singleton.
- Expor modelo mutável: os modelos são congelados (`frozen`).

## Convenções

- Docstring estilo Google em módulo e em todo item público, descrevendo o que garante, o que levanta e o que não faz.
- Piso de cobertura de ramos: 95% (veja [../testing.md](../testing.md)).

## Status

Os módulos da tabela "Existem" estão implementados e testados (cobertura de `domain` de 100% na revisão de 2026-11-13), mas **nenhum comando `hdast` os chama ainda**: a camada `application` está vazia. Os módulos planejados não existem. A fonte do estado é a [tabela de status](../roadmap.md#tabela-de-status).

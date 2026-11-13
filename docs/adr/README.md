# Registro de decisões arquiteturais (ADR)

Um ADR (Architecture Decision Record) registra **uma decisão por arquivo**: contexto, decisão, alternativas e consequências. Serve para que ninguém precise adivinhar por que o projeto é como é.

## Índice

| ADR | Título | Status | Data | Origem |
| --- | --- | --- | --- | --- |
| [0001](0001-dois-planos-agente-propoe-cli-executa.md) | Dois planos: o agente propõe, a CLI executa | Aceito | 2026-11-13 | AD-01 |
| [0002](0002-claude-code-como-runtime-do-agente.md) | Claude Code como runtime do agente | Aceito | 2026-11-13 | AD-02 |
| [0003](0003-python-uv-e-tipagem-estrita.md) | Python, uv e tipagem estrita | Aceito | 2026-11-13 | AD-03, P-06, P-07, P-13 |
| [0004](0004-portas-e-adaptadores-em-tres-camadas.md) | Portas e adaptadores em três camadas | Aceito | 2026-11-13 | AD-04, AD-09 |
| [0005](0005-perfil-de-produto-versionado.md) | Perfil de produto versionado | Aceito | 2026-11-13 | AD-05, P-04 |
| [0006](0006-regras-de-dados-declarativas.md) | Regras de dados declarativas | Aceito | 2026-11-13 | AD-06, P-02, P-12 |
| [0007](0007-zap-alimentado-por-requisicoes-validas.md) | ZAP alimentado por requisições válidas | Aceito (mecanismo a confirmar no spike do M0) | 2026-11-13 | AD-07 |
| [0008](0008-escopo-em-tres-camadas.md) | Escopo em três camadas | Aceito | 2026-11-13 | AD-11, P-03 |
| [0009](0009-segredos-por-referencia.md) | Segredos por referência | Aceito | 2026-11-13 | AD-12 |
| [0010](0010-contrato-json-da-cli-e-codigos-de-saida.md) | Contrato JSON da CLI e códigos de saída | Aceito | 2026-11-13 | AD-08 |
| [0011](0011-limpeza-por-sql-oracle-com-python-oracledb.md) | Limpeza por SQL em Oracle com python-oracledb | Aceito | 2026-11-13 | AD-13, P-05 |
| [0012](0012-dependencias-tzdata-e-pyyaml.md) | Dependências `tzdata` e `pyyaml` | Aceito | 2026-11-13 | QA A-11 |
| [0013](0013-schema-v1-do-perfil-de-produto.md) | Schema v1 do perfil de produto | Aceito | 2026-11-13 | QA A-01, A-02, A-07, A-11, A-13; detalha o 0005 |
| [0014](0014-avaliacao-cega-como-eval.md) | Avaliação cega como suíte de evals | Aceito (implementação no M6) | 2026-11-13 | Requisito do dono do projeto |
| [0015](0015-portas-do-perfil-e-carregador-de-yaml.md) | Portas do perfil e carregador de YAML endurecido | Aceito | 2026-11-13 | M2 (segunda metade); detalha 0004, 0005 e 0012 |
| [0016](0016-leitor-de-openapi-proprio-e-esquema-de-unicidade.md) | Leitor de OpenAPI próprio, subconjunto seguro de `pattern` e esquema de unicidade | Aceito | 2026-11-13 | M3; detalha 0006 e 0007; P-12 |
| [0017](0017-proxy-de-escopo-com-scopeguard.md) | Proxy de escopo com ScopeGuard | Proposto | 2026-11-13 | Spike M0 (Q4, Q6, Q7); QA A-08, A-18; detalha o 0008 |
| [0018](0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md) | `probe` com httpx, CSRF, critério de sucesso e trilha de execução | Proposto | 2026-11-13 | M3; spike M0 (Q1 a Q3, Q5, Q7); detalha os 0007, 0009 e 0010 |

Os ADRs 0012 a 0014 nasceram da [revisão de QA](../reviews/2026-11-13-qa-m1-m2.md) e de um requisito novo do dono do projeto, não do documento de fundação.

A numeração dos ADRs não coincide com a dos cartões AD-xx do documento de fundação. Duas decisões desse documento não viraram ADR próprio e estão documentadas em outro lugar: AD-10 (cobertura como alarme, em [../testing.md](../testing.md)) e AD-14 (revisão em equipe de uma pessoa, em [../../CONTRIBUTING.md](../../CONTRIBUTING.md)). AD-09 (composição e `Protocol`) está dentro do ADR 0004.

## Quando escrever um ADR

- Dependência nova.
- Porta nova.
- Mudança de contrato: envelope JSON, schema do perfil, códigos de saída, formato do achado.
- Mudança de fronteira ou de camada.
- Resultado de um spike que muda um rumo.
- Qualquer decisão que alguém, daqui a seis meses, perguntaria "por que fizemos assim?".

## Ciclo de vida

1. **Proposto**: rascunho em pull request, a partir de [template.md](template.md).
2. **Aceito**: mesclado na `main`. A partir daí o ADR é **imutável**: não se edita contexto, decisão nem consequências.
3. **Substituído por NNNN**: para mudar de rumo, escreva um ADR **novo** que referencie o antigo. No antigo, a única alteração permitida é trocar o status para "Substituído por NNNN" e acrescentar o link.

Correções de digitação e de links são permitidas.

**Exceção única, antes do primeiro commit.** "Aceito" passa a valer quando o ADR é commitado na `main`. Nenhum ADR deste repositório foi commitado ainda; por isso o [ADR 0010](0010-contrato-json-da-cli-e-codigos-de-saida.md) foi emendado no lugar, com uma seção "Histórico", e os ADRs [0005](0005-perfil-de-produto-versionado.md), [0008](0008-escopo-em-tres-camadas.md) e [0009](0009-segredos-por-referencia.md) receberam uma nota de estado. Depois do primeiro commit, esta exceção deixa de existir. Nome de arquivo: `NNNN-titulo-em-minusculas-com-hifens.md`, numeração sequencial sem reaproveitar números.

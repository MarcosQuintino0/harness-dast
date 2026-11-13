# harness-dast

Ferramenta interna para testes de segurança de APIs **autorizados**. Um agente de IA (Claude Code) lê o Swagger/OpenAPI de um produto, escreve o perfil de teste desse produto e chama uma CLI determinística, `hdast`. A CLI valida tudo, impõe o escopo, conduz o OWASP ZAP, gera o relatório e executa a limpeza.

Princípio central: **o agente propõe, a CLI executa.** O agente nunca fala HTTP com o alvo, nunca vê segredo e nunca decide escopo. Veja [ADR 0001](docs/adr/0001-dois-planos-agente-propoe-cli-executa.md).

> **Estado atual: o fluxo completo funciona.** `preflight`, `probe`, `scan`, `report`, `cleanup`, `run` (que encadeia os quatro primeiros), `stack` e `stop` estão implementados e foram verificados contra o **ZAP 2.17 real**, o proxy de escopo real e dois alvos de laboratório (VAmPI e a Clínica Piloto, em modo vulnerável e seguro). O resultado medido, o que a V1 achou e o que **não** achou está em [docs/reviews/2026-11-13-e2e-lab.md](docs/reviews/2026-11-13-e2e-lab.md). Nada foi commitado ainda.
>
> **Não existe ainda:** as skills do agente em `.claude/` e as permissões do Claude Code (M6), a avaliação cega por agentes (M6) e o piloto em um produto real (M7). Um relatório sem achados **não** é prova de que a API é segura: autorização entre contas (BOLA/BFLA), atribuição em massa e exposição excessiva de dados estão fora do que uma varredura ativa do ZAP detecta. Estado por item: [docs/roadmap.md](docs/roadmap.md).

## O que é e o que não é

É:

- Um conjunto de comandos `hdast` que o agente (ou uma pessoa) chama para preparar e executar uma varredura de segurança em uma API de teste.
- Um perfil de produto versionado (`target.yml` e arquivos de regras) que torna a segunda execução repetível sem o agente.
- Uma camada de escopo em código e na rede, para que a varredura não saia da lista permitida.

Não é:

- Uma ferramenta de ataque de uso geral. Só opera sobre produtos com autorização formal.
- Um agente autônomo com shell livre. O agente só chama `hdast`.
- Um substituto do ZAP. Quem ataca é o ZAP; o agente fica na configuração.
- Uma ferramenta pronta para produção. A V1 é de uso local por QAs.

Fora do escopo da V1: teste de autorização entre contas (BOLA, escalada de privilégio), outros motores (nmap, nuclei, Schemathesis), execução automática no CI a cada release, Jira/DefectDojo/SARIF e frontend com navegador. Veja [docs/roadmap.md](docs/roadmap.md).

## Aviso de uso autorizado

Use esta ferramenta **somente** com autorização formal por escrito que informe:

- o sistema alvo e o ambiente;
- o escopo (hosts, caminhos e métodos);
- a janela de execução;
- os limites de carga.

Rode apenas contra **ambientes de teste com dados sintéticos**. Nunca contra produção e nunca com dados pessoais reais. Executar varredura ativa sem autorização pode ser crime e pode derrubar ambientes compartilhados. Detalhes em [SECURITY.md](SECURITY.md) e [docs/operations/authorization-and-scope.md](docs/operations/authorization-and-scope.md).

## Pré-requisitos

| Item | Para quê | Observação |
| --- | --- | --- |
| Python 3.12 ou superior | Rodar a CLI | O uv pode instalar a versão certa. |
| [uv](https://docs.astral.sh/uv/) | Ambiente virtual e dependências travadas | Equivale a Maven/Gradle para Python: resolve e trava versões. |
| Docker Desktop | ZAP, proxy de escopo e laboratório de alvos vulneráveis | Windows com Docker Desktop é suportado. `hdast stack up <produto>` sobe tudo ([lab/README.md](lab/README.md)). Necessário para `probe`, `scan` e `run`; não para `version`, `init`, `profile validate` e `spec inspect`. |
| Claude Code | Agente que usa as skills em `.claude/` | As skills chegam no M6. Não é necessário para os passos abaixo. |

## Instalação e uso (o que funciona hoje)

Na raiz do repositório:

```bash
uv sync
uv run hdast --json version
uv run hdast init meu-produto --products-dir ./meus-produtos   # a pasta precisa existir
uv run hdast --json profile validate meu-produto --products-dir ./meus-produtos
```

Para rodar o fluxo completo contra o lab (VAmPI; ~15 minutos com os limites do perfil de laboratório):

```bash
export HDAST_PRODUCTS_DIR=./meus-produtos          # com lab/vampi/product-profile e openapi3.yml copiados para meus-produtos/vampi
# variáveis VAMPI_* do perfil: veja lab/README.md
uv run hdast stack up vampi                         # ZAP, proxy de escopo e alvo
uv run hdast --json run vampi                       # preflight, probe, scan e report num processo
uv run hdast cleanup vampi --run <run_id> --dry-run  # só se o perfil tiver cleanup; uma pessoa confirma
uv run hdast stack down
```

O `run` grava `runs/<run_id>/run.json`, `findings.json` e `report.md`. Ctrl+C ou `hdast stop` (em outro terminal) encerram com segurança.

O segundo comando imprime em stdout um envelope JSON com `schema_version`, `ok` e o resultado do comando. O formato do envelope está em [docs/reference/cli.md](docs/reference/cli.md) e [docs/architecture.md](docs/architecture.md).

Para rodar as verificações de qualidade (as mesmas que o CI roda):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest
```

Para que serve cada uma: `ruff` faz lint e formatação; `mypy` confere tipos em modo estrito; `lint-imports` (import-linter) quebra o build se uma camada importar o que não pode; `pytest` roda os testes. `uv run pytest` roda os testes unitários e de contrato (milhares) e não precisa de Docker; `uv run pytest -m integration` roda a integração contra o ZAP e o lab reais (precisa de Docker e leva horas; veja [docs/testing.md](docs/testing.md)). O CI roda ainda `uv run vulture` (código sem uso), `gitleaks` e `pip-audit`. Veja [docs/testing.md](docs/testing.md).

`--json` pode vir antes ou depois do comando. A tabela com todos os comandos, flags e o marco de cada um está em [docs/reference/cli.md](docs/reference/cli.md).

## Status e roadmap

| Marco | Tema | Status |
| --- | --- | --- |
| M0 | Decisões e spike descartável | Feito ([docs/spikes/](docs/spikes/2026-11-13-m0-zap.md)) |
| M1 | Fundação: esqueleto, ferramentas, CI, ADRs, documentação, lab | Entregue na árvore de trabalho; falta o primeiro commit e o primeiro pull request |
| M2 | Domínio, perfil e escopo | Entregue |
| M3 | OpenAPI, dados e alcançabilidade | Entregue e verificado contra o ZAP real |
| M4 | Varredura e achados | Entregue e verificado contra o ZAP real |
| M5 | Limpeza e execução completa (`cleanup`, `run`, `stop`) | Entregue; limpeza verificada contra um Oracle Free real |
| M6 | Skills, documentação de uso e avaliação cega por agentes (evals) | Planejado |
| M7 | Piloto em um produto real | Planejado |

A tabela de status por componente, mantida em um único lugar, está em [docs/roadmap.md](docs/roadmap.md).

## Mapa da documentação

| Documento | Conteúdo |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Visão geral, dois planos, camadas, erros, logs, configuração, contrato da CLI, diagramas |
| [docs/roadmap.md](docs/roadmap.md) | Marcos M0 a M7, tabela de status, itens em aberto, candidatos a V2 |
| [docs/testing.md](docs/testing.md) | Níveis de teste, dublês, cobertura, casos obrigatórios do ScopeGuard, análise de mutação, avaliação cega (planejada) |
| [docs/adr/](docs/adr/README.md) | Registro das decisões arquiteturais (0001 a 0024) |
| [docs/modules/](docs/modules/domain.md) | Uma página por pacote: `domain`, `application`, `adapters`, `cli`, `config`, `observability` |
| [docs/reference/cli.md](docs/reference/cli.md) | Comandos da CLI |
| [docs/reference/exit-codes.md](docs/reference/exit-codes.md) | Códigos de saída |
| [docs/reference/env-vars.md](docs/reference/env-vars.md) | Variáveis `HDAST_*` |
| [docs/reference/target-yml.md](docs/reference/target-yml.md) | Schema v1 do perfil de produto, como implementado nos modelos  |
| [docs/reference/scan.md](docs/reference/scan.md), [relatorio.md](docs/reference/relatorio.md), [finding-schema.md](docs/reference/finding-schema.md) | `scan`, `report` (o nome do arquivo é `relatorio.md`, não `report.md`) e o modelo de achado |
| [docs/reviews/2026-11-13-e2e-lab.md](docs/reviews/2026-11-13-e2e-lab.md) | Relatório factual do lab: o que a V1 achou, o que perdeu e por quê |
| [docs/operations/authorization-and-scope.md](docs/operations/authorization-and-scope.md) | O que a autorização formal precisa conter e como vira perfil |
| [docs/operations/threat-model.md](docs/operations/threat-model.md) | Cenários de abuso e mitigações |
| [docs/operations/README.md](docs/operations/README.md) | Índice dos guias de operação, incluindo a [limpeza](docs/operations/cleanup.md) |
| [docs/reviews/](docs/reviews/README.md) | Relatórios de revisão independente (registros datados) e a resposta a cada um |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branches, commits, revisão, Definition of Done |
| [SECURITY.md](SECURITY.md) | Política de uso, escopo, segredos, limpeza, como reportar falhas |
| [CLAUDE.md](CLAUDE.md) | Regras para agentes de IA que desenvolvem ou operam o projeto |
| [CHANGELOG.md](CHANGELOG.md) | Histórico de mudanças |

## Licença

A licença do projeto **ainda não foi definida** (pendência P-14, a decidir no M1). Até lá, não há arquivo `LICENSE` e nenhuma permissão de uso, cópia ou redistribuição é concedida por este repositório.

# harness-dast

Ferramenta interna para testes de segurança de APIs **autorizados**. Um agente de IA (Claude Code) lê o Swagger/OpenAPI de um produto, escreve o perfil de teste desse produto e chama uma CLI determinística, `hdast`. A CLI valida tudo, impõe o escopo, conduz o OWASP ZAP, gera o relatório e executa a limpeza.

Princípio central: **o agente propõe, a CLI executa.** O agente nunca fala HTTP com o alvo, nunca vê segredo e nunca decide escopo. Veja [ADR 0001](docs/adr/0001-dois-planos-agente-propoe-cli-executa.md).

> **Estado atual: M1 (fundação) entregue na árvore de trabalho e primeira metade do M2 (domínio).** Nada foi commitado ainda.
>
> **Existe:**
> - o esqueleto do pacote, as ferramentas de qualidade, o CI, o pre-commit (com gitleaks e commitizen) e a auditoria de dependências (pip-audit);
> - a hierarquia de erros, o envelope JSON, os logs com redação e os comandos `hdast version`, `hdast init` (cria a pasta do produto a partir do modelo) e `hdast profile validate` (valida o `target.yml` e diz o que falta para poder executar; não toca nenhum alvo);
> - o carregador do YAML do perfil, endurecido (sem âncoras, aliases, `<<`, chaves repetidas nem tags fora do esquema básico), e os primeiros casos de uso e portas de `application`;
> - a camada de domínio de escopo e perfil: `ScopeGuard`, janelas de execução, validade da autorização, sobrescritas que só estreitam, identificador de execução, limites com tetos e modelos do perfil de produto, com testes;
> - o `compose.yaml` (ZAP, proxy de saída e ponte) e o lab com o VAmPI, verificados em tempo de execução em 2026-11-13 ([lab/README.md](lab/README.md));
> - o modelo de perfil em `products/_template/`.
>
> **Não existe:** nenhum comando `hdast` além de `version`, `init` e `profile validate`; adaptador de OpenAPI, ZAP, HTTP, segredos, relatório ou limpeza; as skills do agente em `.claude/`; qualquer integração entre a CLI e o ZAP. Hoje a CLI **não faz nenhum teste de segurança**. O que está planejado é marcado como tal. Veja [docs/roadmap.md](docs/roadmap.md).

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
| Docker Desktop | ZAP e laboratório de alvos vulneráveis (a CLI só usará o ZAP a partir do M4) | Windows com Docker Desktop é suportado desde o início. O lab sobe hoje, à mão, conforme [lab/README.md](lab/README.md). Não é necessário para os passos abaixo. |
| Claude Code | Agente que usa as skills em `.claude/` | As skills chegam no M6. Não é necessário para os passos abaixo. |

## Instalação e verificação (o que funciona hoje)

Na raiz do repositório:

```bash
uv sync
uv run hdast --json version
uv run hdast init meu-produto --products-dir ./meus-produtos   # a pasta precisa existir
uv run hdast --json profile validate meu-produto --products-dir ./meus-produtos
```

O segundo comando imprime em stdout um envelope JSON com `schema_version`, `ok` e o resultado do comando. O formato do envelope está em [docs/reference/cli.md](docs/reference/cli.md) e [docs/architecture.md](docs/architecture.md).

Para rodar as verificações de qualidade (as mesmas que o CI roda):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest
```

Para que serve cada uma: `ruff` faz lint e formatação; `mypy` confere tipos em modo estrito; `lint-imports` (import-linter) quebra o build se uma camada importar o que não pode; `pytest` roda os testes. Hoje `uv run pytest` roda os testes unitários e de contrato (mais de 1,6 mil na revisão de 2026-11-13) e não precisa de Docker. O CI roda ainda `uv run vulture` (código sem uso), `gitleaks` e `pip-audit`. Veja [docs/testing.md](docs/testing.md).

`--json` pode vir antes ou depois do comando. Os demais comandos (`init`, `spec inspect`, `profile validate`, `preflight`, `probe`, `scan`, `report`, `cleanup`, `run`) **ainda não existem**. A tabela com o marco de cada um está em [docs/reference/cli.md](docs/reference/cli.md).

## Status e roadmap

| Marco | Tema | Status |
| --- | --- | --- |
| M0 | Decisões e spike descartável | Pendente (confirma o mecanismo de AD-07 e resolve P-08 e P-10) |
| M1 | Fundação: esqueleto, ferramentas, CI, ADRs, documentação, lab | Entregue na árvore de trabalho; falta o primeiro commit e o primeiro pull request |
| M2 | Domínio, perfil e escopo | Em andamento: domínio feito; faltam carregador de YAML, `init`, `profile validate` e casos de uso |
| M3 | OpenAPI, dados e alcançabilidade | Planejado |
| M4 | Varredura e achados | Planejado |
| M5 | Limpeza e execução completa | Planejado |
| M6 | Skills, documentação de uso e avaliação cega por agentes (evals) | Planejado |
| M7 | Piloto em um produto real | Planejado |

A tabela de status por componente, mantida em um único lugar, está em [docs/roadmap.md](docs/roadmap.md).

## Mapa da documentação

| Documento | Conteúdo |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Visão geral, dois planos, camadas, erros, logs, configuração, contrato da CLI, diagramas |
| [docs/roadmap.md](docs/roadmap.md) | Marcos M0 a M7, tabela de status, itens em aberto, candidatos a V2 |
| [docs/testing.md](docs/testing.md) | Níveis de teste, dublês, cobertura, casos obrigatórios do ScopeGuard, análise de mutação, avaliação cega (planejada) |
| [docs/adr/](docs/adr/README.md) | Registro das decisões arquiteturais (0001 a 0014) |
| [docs/modules/](docs/modules/domain.md) | Uma página por pacote: `domain`, `application`, `adapters`, `cli`, `config`, `observability` |
| [docs/reference/cli.md](docs/reference/cli.md) | Comandos da CLI |
| [docs/reference/exit-codes.md](docs/reference/exit-codes.md) | Códigos de saída |
| [docs/reference/env-vars.md](docs/reference/env-vars.md) | Variáveis `HDAST_*` |
| [docs/reference/target-yml.md](docs/reference/target-yml.md) | Schema v1 do perfil de produto, como implementado nos modelos (o carregador de YAML ainda não existe) |
| [docs/reference/finding-schema.md](docs/reference/finding-schema.md) | Modelo de achado (planejado) |
| [docs/operations/authorization-and-scope.md](docs/operations/authorization-and-scope.md) | O que a autorização formal precisa conter e como vira perfil |
| [docs/operations/threat-model.md](docs/operations/threat-model.md) | Cenários de abuso e mitigações |
| [docs/operations/README.md](docs/operations/README.md) | Índice dos guias de operação (a maioria planejada para o M6) |
| [docs/reviews/](docs/reviews/README.md) | Relatórios de revisão independente (registros datados) e a resposta a cada um |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branches, commits, revisão, Definition of Done |
| [SECURITY.md](SECURITY.md) | Política de uso, escopo, segredos, limpeza, como reportar falhas |
| [CLAUDE.md](CLAUDE.md) | Regras para agentes de IA que desenvolvem ou operam o projeto |
| [CHANGELOG.md](CHANGELOG.md) | Histórico de mudanças |

## Licença

A licença do projeto **ainda não foi definida** (pendência P-14, a decidir no M1). Até lá, não há arquivo `LICENSE` e nenhuma permissão de uso, cópia ou redistribuição é concedida por este repositório.

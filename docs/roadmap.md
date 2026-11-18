# Roadmap do harness-dast

## Estado atual

A versão do pacote é **1.12.1**, conforme o [`pyproject.toml`](../pyproject.toml). A V1.12 entrou pelo PR #36 (`b50f843`) e a V1.12.1 pelo PR #37 (`b232855`).

As provas de execução se limitam ao laboratório, com Clínica Piloto, VAmPI e crAPI. O piloto M7 em produto real segue pendente. Os relatórios registram o alcance e as lacunas de cada prova. [V1.12](arquivo/reviews/relatorio-v1.12.md), [V1.12.1](arquivo/reviews/relatorio-v1.12.1.md).

## Tabela de status

| Capacidade implementada | Onde consultar |
| --- | --- |
| Cadastro por carta, validação do perfil e aprovação humana do escopo | [Cadastro](usar/cadastrar-um-produto.md) |
| Cerca na CLI e no proxy, com janela, limites e parada de emergência | [Autorização e escopo](como-funciona/operacao/authorization-and-scope.md) |
| Inventário do OpenAPI, geração de dados, encadeamento e medição de alcance | [CLI](referencia/cli.md) |
| Varredura com OWASP ZAP e controles adicionais condicionados à carta | [Varredura](referencia/scan.md), [uso do ZAP](referencia/uso-do-zap.md) |
| Verificações de autorização e de valores proibidos, ligadas por padrão no `run` | [Autorização](referencia/authz.md), [testes negativos](referencia/negative.md) |
| Prévia local, estratégia versionada, conhecimento e diário de mutações | [Estratégia](referencia/strategy.md), [conhecimento](referencia/knowledge.md) |
| Relatório, painel, métricas, verificação automática e confirmação humana de achados | [Relatório](referencia/relatorio.md), [verificação](referencia/verification.md) |
| Limpeza Oracle com confirmação humana e segredos resolvidos por referência | [Limpeza](usar/limpeza-de-dados.md), [CLI](referencia/cli.md#hdast-secret) |
| Skills de operação e suíte de avaliação cega em laboratório | [Avaliação das skills](desenvolver/avaliacao-das-skills.md) |

O contrato de autorização entre contas e as lacunas de cobertura estão na [referência de autorização](referencia/authz.md).

## Itens em aberto

| Item | Pendência |
| --- | --- |
| A-08 | Definir e verificar o acesso a ambientes de teste em rede privada da empresa. [Riscos residuais do proxy](../docker/scope-proxy/README.md#o-que-isto-não-garante-riscos-residuais) |
| V1.1-a | Tratar a coerção de tipo nos parâmetros de caminho. A mitigação atual é negar esses caminhos com curinga. [Relatório da cerca](arquivo/reviews/2026-11-13-lab-v1-1-cerca.md) |
| Q-18 | Registrar a decisão de encaminhamento no proxy antes da resposta, para preservar a auditoria em caso de interrupção. |
| P-08 | Confirmar o plano do Claude Code na empresa, o contrato de dados e a incidência de bloqueios do provedor. |
| P-09 | Nomear o segundo revisor humano dos módulos críticos. |
| P-14 | Definir a licença do projeto e as condições para eventual reúso de código. |

## Reestruturação em andamento

- Fase 0, linha de base. Medição, mapa de dependências e linha de base da cerca no laboratório.
- Fase 1, enxugar. Documentação em pastas, índice de decisões, CONTRIBUTING dentro do AGENTS, licença MIT, testes com nome de comportamento e resultados de avaliação fora do repositório.
- Fase 2, simplificar o uso. Imagens Docker prontas e tutorial, `hdast demo`, ajuda em painéis, hooks como segunda trava do agente, `hdast retestar`, `hdast setup` e carta com padrões mínimos.
- Fase 3, mostrar. README novo, GIFs, capturas e vídeo.
- Fase 4, usar de verdade. Primeiro uso real (M7), dependente do dono.
- Fase 5, ampliar. O que o uso real pedir, como Schemathesis, MCP, plugin e outros motores.

## Gates de qualidade

Os comandos e critérios de validação estão na [estratégia de testes](desenvolver/testing.md) e na [escada de testes](desenvolver/escada-de-testes.md).

Para consultar marcos e provas antigas, veja o [roadmap histórico](arquivo/roadmap-historico.md) e o [changelog](../CHANGELOG.md).

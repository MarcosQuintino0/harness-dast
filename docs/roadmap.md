# Roadmap do harness-dast

## Estado atual

A versão do pacote é **1.12.2**, conforme o [`pyproject.toml`](../pyproject.toml). A V1.12 entrou pelo PR #36 (`b50f843`) e a V1.12.1 pelo PR #37 (`b232855`).

As provas de execução se limitam ao laboratório, com Clínica Piloto, VAmPI e crAPI. O piloto M7 em produto real segue pendente. Os relatórios registram o alcance e as lacunas de cada prova. [V1.12](arquivo/reviews/relatorio-v1.12.md), [V1.12.1](arquivo/reviews/relatorio-v1.12.1.md).

## Tabela de status

| Capacidade implementada | Onde consultar |
| --- | --- |
| Cadastro por carta, validação do perfil e aprovação humana do escopo | [Cadastro](usar/cadastrar-um-produto.md) |
| Cerca na CLI e no proxy, com janela, limites e parada de emergência | [Autorização e escopo](como-funciona/operacao/authorization-and-scope.md) |
| Inventário do OpenAPI, geração de dados, encadeamento e medição de alcance | [CLI](referencia/cli.md) |
| Varredura com OWASP ZAP e controles adicionais condicionados à carta | [Varredura](referencia/scan.md), [uso do ZAP](referencia/uso-do-zap.md) |
| Nuclei, o segundo motor: falhas conhecidas de produtos de prateleira, configuração errada e exposição fora do contrato, atrás da segunda cerca (`scope-proxy-nuclei`), com etapa `nuclei` no `run`, comando `hdast nuclei`, login por arquivo de segredos e achados `U-` com gravidade fixa. Governado por `extra_checks.nuclei`, `nuclei_login` e `nuclei_wide_paths`, que só a carta, a pessoa ou o padrão do pedido mínimo ligam ([ADR 0122](decisoes/0122-nuclei-como-segundo-motor.md)) | [`hdast nuclei`](referencia/cli.md#hdast-nuclei), [uso do ZAP e do Nuclei](referencia/uso-do-zap.md), [arquitetura](como-funciona/arquitetura.md#a-segunda-cerca-do-nuclei) |
| Verificações de autorização e de valores proibidos, ligadas por padrão no `run` | [Autorização](referencia/authz.md), [testes negativos](referencia/negative.md) |
| Prévia local, estratégia versionada, conhecimento e diário de mutações | [Estratégia](referencia/strategy.md), [conhecimento](referencia/knowledge.md) |
| Relatório, painel, métricas, verificação automática e confirmação humana de achados | [Relatório](referencia/relatorio.md), [verificação](referencia/verification.md) |
| Limpeza Oracle com confirmação humana e segredos resolvidos por referência | [Limpeza](usar/limpeza-de-dados.md), [CLI](referencia/cli.md#hdast-secret) |
| Skills de operação e suíte de avaliação cega em laboratório | [Avaliação das skills](desenvolver/avaliacao-das-skills.md) |

**Limites de prova do Nuclei.** O spike do ADR 0122 mediu 0 achados exclusivos na Clínica Piloto, no VAmPI e no crAPI e 13 detecções do Actuator num alvo Spring. A [prova no laboratório](arquivo/reviews/2026-11-19-prova-nuclei.md) passou nos aceites 2 a 6 e na cerca desligada, uma execução por alvo. O alvo `alvo-actuator` rendeu 11 achados do Actuator e 2 tecnologias, não 13 achados: o `springboot-whitelabel` não casou com a raiz em texto simples. No crAPI, 16 linhas da saída não puderam ser projetadas, e a causa não foi isolada porque a saída bruta é descartada. O ganho em produto real não foi medido. O login por arquivo de segredos só foi provado com marcador sintético, e não houve captura de pacotes nem `hdast stop` com o Nuclei no ar. Nada foi provado ainda por rodada cega nem pelo piloto M7. Com caminhos amplos e escrita ligados, um modelo de CVE pode gravar dados no ambiente de teste (risco aceito, [modelo de ameaças](como-funciona/operacao/threat-model.md)). A tabela de gravidade fixa subestima, por exemplo, o `/actuator/env` com valores de configuração (baixa).

O contrato de autorização entre contas e as lacunas de cobertura estão na [referência de autorização](referencia/authz.md).

## Itens em aberto

| Item | Pendência |
| --- | --- |
| A-08 | Definir e verificar o acesso a ambientes de teste em rede privada da empresa. [Riscos residuais do proxy](../docker/scope-proxy/README.md#o-que-isto-não-garante-riscos-residuais) |
| V1.1-a | Tratar a coerção de tipo nos parâmetros de caminho. A mitigação atual é negar esses caminhos com curinga. [Relatório da cerca](arquivo/reviews/2026-11-13-lab-v1-1-cerca.md) |
| Q-18 | Registrar a decisão de encaminhamento no proxy antes da resposta, para preservar a auditoria em caso de interrupção. |
| P-08 | Confirmar o plano do Claude Code na empresa, o contrato de dados e a incidência de bloqueios do provedor. |
| P-09 | Nomear o segundo revisor humano dos módulos críticos. |

## Itens fechados

- P-14 fechado em 18/11/2026 com a adoção da licença MIT. [ADR 0110](decisoes/0110-reestruturacao-documentacao-licenca-e-extras.md)

## Reestruturação em andamento

As decisões da reestruturação registradas nos ADRs 0110 a 0115 estão implementadas e aguardam o aceite do dono. [Catálogo de decisões](decisoes/README.md).

- Fase 0, linha de base. Medição, mapa de dependências e linha de base da cerca no laboratório.
- Fase 1, enxugar. Documentação em pastas, índice de decisões, orientações de contribuição no `AGENTS.md`, licença MIT, testes com nome de comportamento e resultados de avaliação fora do repositório.
- Fase 2, simplificar o uso. Imagens Docker prontas e tutorial, `hdast demo`, ajuda em painéis, hooks como segunda trava do agente, `hdast retestar`, `hdast setup` e carta com padrões mínimos.
- Fase 3, mostrar. README novo, GIFs, capturas e vídeo.
- Fase 4, usar de verdade. Primeiro uso real (M7), dependente do dono.
- Fase 5, ampliar. O que o uso real pedir, como Schemathesis, MCP, plugin e outros motores.

## Gates de qualidade

Os comandos e critérios de validação estão na [estratégia de testes](desenvolver/testing.md) e na [escada de testes](desenvolver/escada-de-testes.md).

Para consultar marcos e provas antigas, veja o [roadmap histórico](arquivo/roadmap-historico.md) e o [changelog](../CHANGELOG.md).

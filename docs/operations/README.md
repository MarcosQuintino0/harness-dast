# Operação

Guias para quem usa o `harness-dast` contra um produto. Os comandos do fluxo completo existem e os guias passo a passo (primeiro uso, cadastro com o agente, limpeza, problemas comuns) estão em [../guides/](../guides/primeiro-uso.md). Este índice lista o que existe. Nenhum guia fictício é mantido aqui.

Antes de qualquer uso, leia o aviso de uso autorizado no [README](../../README.md) e a [política de segurança](../../SECURITY.md).

## Documentos

| Documento | Conteúdo | Status |
| --- | --- | --- |
| [authorization-and-scope.md](authorization-and-scope.md) | O que a autorização formal precisa conter e como vira `scope`, `limits` e `authorization` no perfil | Escrito (a validação é aplicada por `preflight`, `probe`, `scan` e `run`) |
| [threat-model.md](threat-model.md) | Cenários de abuso e mitigação de cada um | Escrito (mitigações em parte no domínio e no `compose.yaml`; o resto planejado) |
| [../guides/cadastrar-um-produto.md](../guides/cadastrar-um-produto.md) | Cadastrar um produto: carta de autorização, perfil, segredos e prompts por etapa para o agente | Escrito (M6) |
| Rodar uma varredura | `hdast run` (ou `preflight`, `probe`, `scan` e `report` um a um): [reference/cli.md](../reference/cli.md#hdast-run), [reference/scan.md](../reference/scan.md), [reference/relatorio.md](../reference/relatorio.md); passo a passo em [../guides/primeiro-uso.md](../guides/primeiro-uso.md) | Escrito (M6) |
| [cleanup.md](cleanup.md) | Rodar `hdast cleanup` com confirmação humana | Escrito |
| O que fazer se algo sair errado | `hdast stop` (trava de emergência), `hdast stack down`, regras `hdast-` sobrando no Replacer: [reference/cli.md](../reference/cli.md#hdast-stack-e-hdast-stop) e [reference/scan.md](../reference/scan.md#parada-prazo-e-saúde-do-alvo) | Referência escrita; guia planejado (M6) |

## Regras que valem desde já

- Só contra ambiente de teste com dados sintéticos e com autorização registrada no perfil.
- O agente age sobre o alvo somente por comandos `hdast`. Veja a Parte B de [CLAUDE.md](../../CLAUDE.md).
- Na dúvida sobre autorização, escopo ou janela, pare e peça ao dono do produto.

## Hoje

O fluxo `preflight` -> `probe` -> `scan` -> `report` (e o `run` que o encadeia), a limpeza e a trava de emergência estão implementados e foram exercitados contra o lab ([relatório](../reviews/2026-11-13-e2e-lab.md)). Veja [../reference/cli.md](../reference/cli.md) e a [tabela de status](../roadmap.md#tabela-de-status).

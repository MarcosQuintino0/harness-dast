# Operação

Guias para quem usa o `harness-dast` contra um produto. Esta pasta está em fase de planejamento: **os guias de uso passo a passo só serão escritos no M6**, depois que os comandos existirem. Até lá, este índice lista o que existe e o que está planejado. Nenhum guia fictício é mantido aqui.

Antes de qualquer uso, leia o aviso de uso autorizado no [README](../../README.md) e a [política de segurança](../../SECURITY.md).

## Documentos

| Documento | Conteúdo | Status |
| --- | --- | --- |
| [authorization-and-scope.md](authorization-and-scope.md) | O que a autorização formal precisa conter e como vira `scope`, `limits` e `authorization` no perfil | Escrito (a validação existe no domínio; nenhum comando a aplica ainda) |
| [threat-model.md](threat-model.md) | Cenários de abuso e mitigação de cada um | Escrito (mitigações em parte no domínio e no `compose.yaml`; o resto planejado) |
| Cadastrar um produto (onboarding) | Do Swagger ao perfil validado | Planejado (M6) |
| Rodar uma varredura | `preflight`, `probe`, `scan` e `report` | Planejado (M6) |
| Limpeza do ambiente | Rodar `hdast cleanup` com confirmação humana | Planejado (M6) |
| O que fazer se algo sair errado | Parada de emergência, escopo violado, ZAP indisponível | Planejado (M6) |

## Regras que valem desde já

- Só contra ambiente de teste com dados sintéticos e com autorização registrada no perfil.
- O agente age sobre o alvo somente por comandos `hdast`. Veja a Parte B de [CLAUDE.md](../../CLAUDE.md).
- Na dúvida sobre autorização, escopo ou janela, pare e peça ao dono do produto.

## Hoje

Não há comando que toque um alvo. O único comando implementado é `hdast version`. O `ScopeGuard`, as janelas e os modelos do perfil existem como código de domínio, mas nenhum comando os usa. Veja [../reference/cli.md](../reference/cli.md) e a [tabela de status](../roadmap.md#tabela-de-status).

# Autorização e escopo

> **Status:** a validação existe em código de domínio (`ScopeGuard`, janelas, validade da autorização, modelos do perfil), testado, e é aplicada por `preflight`, `probe`, `scan`, `authz`, `run` e pelo proxy de escopo (verificada contra o ZAP real e alvos de laboratório, não contra produto real). Decisão: [ADR 0008](../adr/0008-escopo-em-tres-camadas.md); estado por item em [../roadmap.md](../roadmap.md#tabela-de-status).

## Regra geral

Só se testa com **autorização formal por escrito**. Sem ela, não há teste. O modelo do perfil recusa um perfil sem a referência da autorização, e `ProductProfile.ensure_runnable` recusa autorização vencida ou fora da janela. A CLI usa essas conferências antes de qualquer execução. Na dúvida, a execução para (falha fechada).

## O que a autorização formal precisa informar

| Item | Vira no perfil | Por quê |
| --- | --- | --- |
| Sistema alvo e ambiente | `environment` (`name`, `base_url`) | Só ambiente de teste com dados sintéticos |
| Escopo: hosts, caminhos e métodos permitidos | `scope.allow` | Lista permitida; o que não casa com uma regra explícita é recusado |
| Caminhos proibidos | `scope.deny_paths` | Exclusões mesmo dentro de um host permitido |
| Referência e validade da autorização | `scope.authorization.reference` e `valid_until` | A CLI recusa sem isso ou vencida |
| Janela de execução | `scope.windows` | A janela é conferida a cada lote, não só no preflight |
| Limites de carga | `limits` | Requisições por segundo, duração máxima e threads do ZAP sempre fixados |
| Contas de teste | `auth.accounts` | Apelido, papel e `secret_ref`. Contas inválidas em produção |
| Quem responde pelo produto | (fora do perfil) | Para pedir ampliação de escopo e autorizar a limpeza |

O formato exato dos campos (schema v1) está em [../reference/target-yml.md](../reference/target-yml.md), com a gramática das janelas e a regra de `valid_until` (data, inclusiva, contada em UTC). O fuso da validade em UTC pode encerrá-la algumas horas antes do fim do dia local; informe a data com folga.

## Quem preenche o quê

- `scope`, `limits` e `authorization` **vêm da autorização formal informada pelo usuário**. O agente os transcreve; não os inventa nem os alarga.
- Se o escopo parecer curto demais, o agente e o QA param e pedem ao dono do produto. Ninguém amplia por conta própria.
- Flags de linha de comando só **reduzem** escopo e limites.
- `scope.path_mode: wide` (modo amplo do proxy de escopo, [ADR 0026](../adr/0026-cerca-com-motivo-granular-e-modo-amplo-de-caminho.md)) é um **alargamento** e só vale se a carta o autoriza por escrito. O agente copia o que a carta diz, nunca o liga por conta própria e nenhuma flag o liga. Risco aceito pelo dono: um pedido liberado pode alcançar outro caminho do mesmo host que não está em `deny_paths`; por isso a lista de caminhos proibidos da carta precisa ser completa.

## Como o escopo é imposto

Três camadas independentes, cada uma cobrindo a falha da outra:

| Camada | O que faz | Status |
| --- | --- | --- |
| 1. `ScopeGuard` no domínio | Valida toda requisição e todo plano de varredura | Implementado: `preflight`, `probe`, `scan` e o proxy de escopo o chamam em toda requisição |
| 2. ZAP em modo protegido | Contexto do ZAP restrito aos mesmos hosts e caminhos | Implementado (M4): o contexto por execução (`domain/zap_scope.py`) |
| 3. Rede interna do Docker e proxy de escopo (mitmproxy com o mesmo `ScopeGuard`, [ADR 0017](../adr/0017-proxy-de-escopo-com-scopeguard.md)) | O contêiner do ZAP só sai pelo proxy | Implementado e exercitado no lab: a varredura ativa real passou pelo proxy e o que saiu do escopo foi negado e contado ([relatório](../reviews/2026-11-13-e2e-lab.md)). Alvo corporativo em IP privado não confirmado (A-08). Obrigatória antes de qualquer execução contra ambiente da empresa; opcional contra o lab |

As permissões do Claude Code (negar `curl`, negar leitura de `.env`) reduzem acidentes, mas não são isolamento.

## O que o `ScopeGuard` deve tratar

Casos obrigatórios de teste, todos com teste hoje (lista em [../testing.md](../testing.md#casos-obrigatórios-do-scopeguard)): redirecionamento para host fora da lista, host com usuário embutido, IP literal e endereços de metadados da nuvem, diferenças de maiúsculas e de porta, caminhos com `..`, decoração de caminho que o servidor remove (`;x=1`, ponto ou espaço finais), método não permitido e janela fechada. A lista do que o guarda recusa e suas limitações (sem DNS, cabeçalhos e corpo não conferidos) está em [../reference/target-yml.md](../reference/target-yml.md#o-que-o-scopeguard-recusa).

## Responsabilidades

| Pessoa | Responsabilidade |
| --- | --- |
| QA que opera | Informar a autorização real, conferir a janela, não ampliar limites, acionar a parada de emergência se algo sair do esperado |
| Dono do produto | Emitir a autorização, escrever e revisar o hook de limpeza, confirmar a limpeza |
| Mantenedor do harness | Manter as travas em código; receber relatos de falha do próprio harness (veja [../../SECURITY.md](../../SECURITY.md)) |

Quem é o segundo revisor humano das mudanças em escopo, segredos, limpeza e permissões ainda não foi definido, até onde os documentos mostram (P-09, prevista para o M2; a confirmar com o dono). O `ScopeGuard` já tem código e está em uso, então a pendência pesa.

# Autorização e escopo

> **Status:** a validação existe como **código de domínio** (`ScopeGuard`, janelas, validade da autorização, modelos do perfil), testado. **Nenhum comando `hdast` a aplica ainda**: não há carregador de perfil nem comando que chame o guarda, então hoje a CLI não impõe nada sobre um alvo. Decisão: [ADR 0008](../adr/0008-escopo-em-tres-camadas.md).

## Regra geral

Só se testa com **autorização formal por escrito**. Sem ela, não há teste. O modelo do perfil recusa um perfil sem a referência da autorização, e `ProductProfile.ensure_runnable` recusa autorização vencida ou fora da janela. Quando os comandos existirem (M2 em diante), a CLI os usará antes de qualquer execução. Na dúvida, a execução para (falha fechada).

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

## Como o escopo é imposto

Três camadas independentes, cada uma cobrindo a falha da outra:

| Camada | O que faz | Status |
| --- | --- | --- |
| 1. `ScopeGuard` no domínio | Valida toda requisição e todo plano de varredura | Implementado: `preflight`, `probe`, `scan` e o proxy de escopo o chamam em toda requisição |
| 2. ZAP em modo protegido | Contexto do ZAP restrito aos mesmos hosts e caminhos | Implementado (M4): o contexto por execução (`domain/zap_scope.py`) |
| 3. Rede interna do Docker e proxy de saída com lista de hosts | O contêiner do ZAP só sai pelo proxy | Parcial: `compose.yaml` e Squid existem e foram verificados no lab; tráfego real de varredura não provado; alvo corporativo em IP privado não confirmado. Obrigatória antes de qualquer execução contra ambiente da empresa; opcional contra o lab |

As permissões do Claude Code (negar `curl`, negar leitura de `.env`) reduzem acidentes, mas não são isolamento.

## O que o `ScopeGuard` deve tratar

Casos obrigatórios de teste, todos com teste hoje (lista em [../testing.md](../testing.md#casos-obrigatórios-do-scopeguard)): redirecionamento para host fora da lista, host com usuário embutido, IP literal e endereços de metadados da nuvem, diferenças de maiúsculas e de porta, caminhos com `..`, decoração de caminho que o servidor remove (`;x=1`, ponto ou espaço finais), método não permitido e janela fechada. A lista do que o guarda recusa e suas limitações (sem DNS, cabeçalhos e corpo não conferidos) está em [../reference/target-yml.md](../reference/target-yml.md#o-que-o-scopeguard-recusa).

## Responsabilidades

| Pessoa | Responsabilidade |
| --- | --- |
| QA que opera | Informar a autorização real, conferir a janela, não ampliar limites, acionar a parada de emergência se algo sair do esperado |
| Dono do produto | Emitir a autorização, escrever e revisar o hook de limpeza, confirmar a limpeza |
| Mantenedor do harness | Manter as travas em código; receber relatos de falha do próprio harness (veja [../../SECURITY.md](../../SECURITY.md)) |

Quem é o segundo revisor humano das mudanças em escopo, segredos, limpeza e permissões ainda não foi definido (P-09, decidir até o M2). Como o `ScopeGuard` já tem código, a pendência já pesa.

# 0114. Padrões mínimos da carta e o comando humano `hdast setup`

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** Pacote 2.6 da reestruturação

## Contexto

Hoje a resposta "desconhecido" em qualquer campo obrigatório da carta estruturada ([ADR 0036](0036-carta-estruturada.md)) para o cadastro. Isso trava o cadastro por detalhes que têm um valor seguro óbvio, como o teto de requisições por segundo. Depois do cadastro, a pessoa ainda precisa rodar `hdast secret set` uma vez por conta e, por fim, `hdast profile approve` ([ADR 0037](0037-aprovacao-humana-do-escopo.md)): três comandos em ordem que ela precisa lembrar.

Nada disso pode alargar uma trava. Quem autoriza é sempre uma pessoa: a carta e a aprovação do escopo.

## Decisão

**1. "Não sei" nunca alarga.** Ou o campo vira o valor mais estreito, fixado no código da CLI, ou o cadastro para. O agente nunca escolhe o valor.

**2. Tabela única de padrões mínimos**, em `domain/letter_defaults.py`. Só estes quatro campos aceitam `source: desconhecido`:

| Campo | Valor com "não sei" | Motivo |
| --- | --- | --- |
| `limits.requests_per_second` | `1` | carga mínima útil para a varredura |
| `limits.max_duration_minutes` | `30` | limita o tempo do alvo sob teste |
| `limits.zap_threads_per_host` | `1` | menor paralelismo do varredor |
| `auth.login_max_per_minute` | `1` | menor valor que o perfil aceita (`ge=1`) |

Só a resposta `desconhecido` declarada usa o padrão. Campo ausente, nulo ou inválido segue como pendência (`MISSING`, `INVALID_VALUE`). Resposta com valor (origem `carta` ou `pessoa`) mantém o valor.

**3. Aviso obrigatório.** Cada padrão aplicado gera um aviso `MINIMUM_DEFAULT_APPLIED` em `data.warnings` do `hdast init --from-letter` (campo, valor e "padrão mínimo da CLI"). O perfil gerado ganha uma linha de comentário no cabeçalho por padrão aplicado (`# Padrão mínimo da CLI: campo = valor`). Comentário não entra na impressão digital da aprovação. O `hdast setup` lê essas linhas e as mostra em destaque no alto do resumo da aprovação.

**4. Continuam portões** (com "não sei" o cadastro para, com a mensagem de hoje): os quatro portões (ambiente de teste, dados sintéticos, autorização vigente, dono do produto), `environment.base_url`, `scope.allow`, `authorization.reference`, `valid_until` e `windows`, `auth.type`, `auth.accounts` e **`scope.deny_paths`**.

`scope.deny_paths` não vira lista vazia com "não sei". A lista vazia declarada pela pessoa continua valendo (com o aviso `DENY_PATHS_EMPTY` e, no `setup`, um destaque no resumo), mas "não sei" não é "não há": converter uma coisa na outra deixaria passar um perfil sem nenhuma exclusão declarada. Por isso o campo continua parando o cadastro.

**5. `path_mode`, força e o bloco `attack`** já valem o mais estreito quando ausentes ou `desconhecido`: `strict`, o padrão do perfil e tudo desligado. Esta decisão não muda nenhum deles, e o teste de contrato os protege.

**6. `hdast setup <produto>`**, comando humano. Exige terminal interativo e recusa `--json`, como `profile approve`. Conduz, em ordem e sem juntar as decisões:

1. recusa sem terminal;
2. valida o perfil e, se houver pendência (a janela fechada não conta, porque só vale na execução), para antes de pedir qualquer senha;
3. para cada `secret_ref: keyring:NOME` ausente do cofre, pede o valor em prompt oculto, duas vezes, pelo mesmo caso de uso do `secret set`; segredos `env:` são só listados, com o aviso de que vêm do ambiente; nunca mostra nem registra valores;
4. mostra o resumo do `profile approve`, com os avisos de padrão mínimo e de nenhum caminho proibido no alto;
5. pausa explícita ("Leia o resumo acima. Para aprovar, continue; para sair sem aprovar, Ctrl+C"), e só então o mesmo pedido de digitar o nome do produto do `profile approve` (a mesma função);
6. grava a aprovação pelo mesmo caminho do `profile approve`.

`secret set` e `profile approve` continuam existindo e funcionando igual.

**7. Travas.** `setup` entra na constante `HUMAN_COMMANDS` do `.claude/hooks/guard.py` e nas negações do `.claude/settings.json` (Bash e PowerShell, com e sem `uv run`, com e sem `--json`), no mesmo commit, com testes. O agente nunca o roda; a Parte B de `AGENTS.md` o lista. O agente pede à pessoa que rode `hdast setup <produto>` num terminal dela.

**8. Camadas.** A decisão de padrão e os avisos ficam em `domain` (`letter_defaults`, `setup_notes`). A orquestração fica em `application` (`SetupProduct`, reaproveitando `SecretAdmin` e `ScopeApprovals`, com portas novas `AppliedDefaultsReader` e `SetupNotifier`). A montagem e os prompts ficam em `cli`. `ScopeApprovals.approve` ganha o parâmetro opcional `notes`, mostrado antes do resumo e fora da aprovação gravada.

## Alternativas consideradas

- **Lista vazia em `scope.deny_paths` com "não sei", com aviso.** Descartada: aprovaria um perfil sem nenhuma exclusão declarada sem que ninguém tivesse dito isso.
- **Padrões no agente ou na skill.** Descartada: regra e trava ficam em código testado na CLI.
- **Um `setup` que aprova e grava senha sem as duas confirmações.** Descartada: as decisões continuam separadas (senha, leitura do resumo, nome digitado).
- **Guardar os padrões aplicados em arquivo separado do perfil.** Descartada: mais um arquivo de estado; o comentário no cabeçalho do perfil gerado basta e fica junto do que descreve.

## Consequências

- Cadastro mais curto: "não sei" nos limites e no limite de logins não para mais, e o valor aplicado fica visível em três lugares: o aviso do `init`, o cabeçalho do `target.yml` e o resumo da aprovação.
- O mínimo pode ser baixo demais para o alvo: um varredor a 1 req/s por 30 min cobre menos. É o preço de não alargar; a pessoa muda a carta e gera de novo.
- Uma carta antiga, sem "desconhecido" nesses campos, gera o mesmo perfil de antes, sem aviso novo.
- Perfil criado à mão, sem carta, não tem as linhas de comentário: o `setup` só destaca o que souber (nenhum caminho proibido) e não inventa o resto.
- O contrato do envelope da carta não muda. O comando `setup` é novo e entra no painel "Comece por aqui". A tradução do painel e os testes de comandos humanos ganham a entrada.
- Limite: o `setup` não valida que o terminal é de uma pessoa além de `isatty`, como o `profile approve`.

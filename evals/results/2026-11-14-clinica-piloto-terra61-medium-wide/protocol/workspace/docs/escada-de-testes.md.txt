# Escada de testes

Este guia explica como conferir uma mudança no harness-dast sem esperar horas por varreduras do ZAP. É para quem desenvolve o projeto, pessoa ou agente. Os níveis de teste, os dublês e os casos obrigatórios estão em [testing.md](testing.md).

A regra é simples: **cada mudança sobe só até o degrau que ela exige.** A varredura completa e a rodada cega ficam para o fechamento de versão. Origem: proposta aprovada pelo dono em 2026-11-13, depois de a V1.1 gastar horas com varreduras completas a cada conserto. O que ainda falta fazer da proposta está no item V1.1-d do [roadmap](roadmap.md).

## Os cinco degraus

| Degrau | O que roda | Precisa de | Tempo medido | Diz o quê |
| --- | --- | --- | --- | --- |
| 1. Checagens de código | `ruff`, `mypy`, `lint-imports`, `vulture` | Nada | Segundos a 1 min | O código está bem escrito e respeita as camadas |
| 2. Unitários e contrato | `uv run pytest -q` | Nada (sem Docker) | Cerca de 3 min para 7 mil testes (193 s em 2026-11-14) | As regras e os contratos da CLI valem |
| 3. Ataque direcionado | ZAP, cerca e alvo de laboratório reais, em 1 a 3 operações | Docker e laboratório | 2 a 4 min por rodada | A mudança funciona de verdade, de ponta a ponta |
| 4. Varredura completa | `hdast run` com todas as operações e a política padrão | Docker e laboratório | 10 a 23 min por alvo e modo | O produto de laboratório inteiro está coberto |
| 5. Rodada cega | Um agente sem contexto faz o caminho todo | Claude Code, Docker e laboratório | Cerca de 25 min por caso | As skills e as mensagens bastam para quem nunca viu o projeto |

Os degraus 1 e 2 dizem "o código está certo". O degrau 3 diz "esta mudança funciona". Só os degraus 4 e 5 dizem "o produto está coberto", e é por isso que eles não podem faltar no fechamento de versão.

## Até onde subir

| Mudei... | Subo até | Observação |
| --- | --- | --- |
| Relatório, painel, agrupamento de achados, textos e mensagens | 2 | Os golden pegam a mudança de saída |
| Comando da CLI que não toca o alvo (`doctor`, `init`, `profile`, `spec inspect`, `report`, `panel`) | 2 | Contrato do envelope e dos códigos de saída |
| Carta, perfil, aprovação do escopo | 2 | Toda entrada externa nova tem teste com dado inválido, ausente e malformado |
| Teste de autorização (`authz`) | 3, sem varredura | `probe` mais `authz`, sem `scan`: não precisa esperar o ZAP atacar |
| Cerca de escopo ou proxy (`adapters/scope_proxy/`, `docker/`) | 3, com a imagem reconstruída | Veja "A imagem do proxy" abaixo |
| `probe`, encadeamento, dados gerados, login | 3 | `probe --only` nas operações afetadas |
| Regras ou política do ZAP, `scan` | 3; 4 no fechamento | `scan --only` em uma ou duas operações |
| Skills, guias, mensagens que orientam o agente | 5, num caso só | Mudança de skill muda o comportamento do agente, não do código |
| Fechamento de versão | 4 e 5 | Uma vez por alvo e modo, como o plano da versão disser |

Na dúvida entre dois degraus, suba um. Nunca pule do 2 para o 4 por hábito: o 3 costuma bastar.

## Degrau 1. Checagens de código

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run mypy --platform linux
uv run lint-imports
uv run vulture
```

## Degrau 2. Unitários e contrato

```bash
uv run pytest -q
```

O padrão já deixa de fora os testes que precisam de Docker (`integration` e `e2e`). No laço local, enquanto conserta, rode só os arquivos afetados e deixe a suíte inteira para o fim:

```bash
uv run pytest -q tests/unit/domain/test_authz_config.py tests/contract/test_cli_authz.py
```

Se a mudança não tocou a régua de avaliação, pode pular `tests/unit/evals/` no laço local (`--ignore=tests/unit/evals`). Antes de dizer que terminou e antes do pull request, rode a suíte inteira, sem filtro, depois da última mudança. O CI sempre roda tudo.

## Degrau 3. Ataque direcionado

Antes de começar:

- O Docker Desktop precisa estar aberto (`uv run hdast doctor` confere).
- `HDAST_ZAP_API_KEY` definida na sessão, com um valor aleatório que não vai para arquivo versionado ([lab/README.md](../lab/README.md)).
- O perfil de laboratório numa pasta de produtos e **aprovado por uma pessoa** (`hdast profile approve`, ADR 0037). Um agente nunca aprova: diante de `SCOPE_NOT_APPROVED`, ele para e pede.

### Pelo nível rápido de integração

O caminho mais curto e repetível. Já existe e confere o mecanismo em poucas operações (detalhes em [testing.md](testing.md#dois-níveis-de-integração-contra-o-lab)):

```bash
uv run pytest -m lab_fast
uv run pytest -m lab_fast tests/integration/test_lab_path_scope.py
```

### À mão, pelos comandos `hdast`

Quando a mudança não tem teste de integração próprio (por exemplo, uma verificação nova do `authz`), rode só as operações afetadas. Exemplo com a Clínica Piloto (passo a passo da pasta e das contas em [lab/pilot/README.md](../lab/pilot/README.md)):

```bash
uv run hdast --json stack up clinica-piloto --build
uv run hdast --json preflight clinica-piloto
uv run hdast --json probe clinica-piloto --only buscarPacientesPorNome
```

O `probe` devolve o `run_id`. Com ele, escolha o que conferir:

```bash
uv run hdast --json authz clinica-piloto --run <run_id>
uv run hdast --json scan clinica-piloto --run <run_id> --only buscarPacientesPorNome
uv run hdast --json report clinica-piloto --run <run_id>
```

E sempre feche a pilha no fim:

```bash
uv run hdast --json stack down
```

Para o modo corrigido do alvo, repita com `stack up clinica-piloto --secure`: um achado que aparece no vulnerável e some no seguro é a prova de que a verificação acha a falha e não acusa o alvo corrigido.

### A imagem do proxy

O código da cerca é copiado para dentro da imagem do proxy de escopo. Se você mudou `adapters/scope_proxy/`, `domain/` da cerca ou `docker/` e subiu a pilha sem `--build`, o teste roda a cerca **antiga** e passa sem provar nada. Depois de qualquer mudança nesses lugares, suba com `--build`. Hoje nada obriga isso. Obrigar é um dos itens abertos do V1.1-d.

## Degrau 4. Varredura completa

Só no fechamento de versão, ou quando muda o motor ou a política padrão do ZAP:

```bash
HDAST_IT_METRICS_DIR=./medidas uv run pytest -m lab_full
```

Ele roda `hdast run` com todas as operações e a política padrão, no VAmPI e na Clínica Piloto, em modo vulnerável e seguro, e grava as medições. Os resultados e as medições entram no relatório da versão (`docs/reviews/relatorio-v1.N.md`). Escolher operações ou regras olhando o gabarito das falhas plantadas é proibido neste degrau.

## Degrau 5. Rodada cega

Ao fechar versão ou ao mudar skill, guia ou mensagem que orienta o agente. Roteiro e regras em [testing.md](testing.md) (seção da avaliação cega) e em [guides/avaliacao-das-skills.md](guides/avaliacao-das-skills.md). Quando só uma skill mudou, um caso basta.

## Regras que não mudam

- **Só no laboratório.** Os degraus 3 a 5 rodam contra os alvos locais (Clínica Piloto, VAmPI, crAPI), nunca contra produto real.
- **Atalho só reduz.** `--only`, `--max-minutes` e afins diminuem o que roda. Nenhum atalho muda escopo, limites, janela ou autorização do perfil.
- **Pilha limpa a cada rodada.** Subir a pilha leva menos de um minuto, e o ZAP guarda alertas da rodada anterior, que se misturariam aos da seguinte. Use `stack down` e `stack up` entre rodadas.
- **Sem "fita gravada".** Repassar pela cerca os pedidos da auditoria do proxy não prova nada: a auditoria guarda o caminho já decodificado, e a cerca julga justamente a forma crua (`%2f`, `;`).
- **O CI roda tudo.** Pular arquivos é só para o laço local.
- **Diga o que não rodou.** Quem entrega uma mudança informa o degrau a que chegou e o que ficou sem prova.

## Com subagentes

Quando o trabalho é dividido entre agentes (plano do ciclo em [plans/](plans/2026-11-14-ciclo-v1-3-a-v1-8.md)):

- O briefing de cada programador diz o degrau máximo dele. Programadores sobem até o degrau 2. Eles não sobem pilha nem tocam alvo.
- O coordenador faz o degrau 3 sobre a branch integrada, no fim da versão, só nas operações que a versão mudou.
- Os degraus 4 e 5 seguem a coluna "Degrau máximo da escada de testes" do plano do ciclo.

## O que ainda falta (V1.1-d)

| Item | Ganho esperado | Estado |
| --- | --- | --- |
| Obrigar a imagem do proxy a bater com o código antes de teste de laboratório | Fecha o risco de passar com a cerca antiga | Aberto |
| Desligar a regra de SSRF 40046 no perfil de laboratório (ligada no fechamento) | Até 500 s a menos na varredura no modo amplo | Aberto; a causa ainda é dedução (planejado para a V1.7) |
| Testes em paralelo (`pytest-xdist`, pede ADR) | De 223 s para 52 s, medido | Aberto |
| Pular `tests/unit/evals/` no laço local | Cerca de 53 s de processador | Descrito acima; sem atalho de comando |
| Documentar o ataque direcionado | O ciclo conserta-e-confere cai de 10 a 23 min para 2 a 4 min | Feito neste guia |
| Pilhas em paralelo | Cerca de 48 min para 23 min no fechamento | Aberto (varreduras concorrentes planejadas para a V1.7) |

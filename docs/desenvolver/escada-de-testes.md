# Escada de testes

Este guia explica como conferir uma mudança no harness-dast sem esperar horas por varreduras do ZAP. É para quem desenvolve o projeto, pessoa ou agente. Os níveis de teste, os dublês e os casos obrigatórios estão em [testing.md](testing.md).

A regra é simples: **cada mudança sobe só até o degrau que ela exige.** A varredura completa e a rodada cega ficam para o fechamento de versão. Origem: proposta aprovada pelo dono em 2026-11-13, depois de a V1.1 gastar horas com varreduras completas a cada conserto. O item V1.1-d registra o estado da proposta à época. [Roadmap histórico](../arquivo/roadmap-historico.md#itens-novos-da-v11-abertos-em-2026-11-13-a-partir-das-medições).

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
uv run pytest -q tests/unit/domain/authz/test_config.py tests/contract/test_cli_authz.py
```

Se a mudança não tocou a régua de avaliação, pode pular `tests/unit/evals/` no laço local (`--ignore=tests/unit/evals`). Antes de dizer que terminou e antes do pull request, rode a suíte inteira, sem filtro, depois da última mudança. O CI sempre roda tudo.

## Degrau 3. Ataque direcionado

Antes de começar:

- O Docker Desktop precisa estar aberto (`uv run hdast doctor` confere).
- `HDAST_ZAP_API_KEY` definida na sessão, com um valor aleatório que não vai para arquivo versionado ([lab/README.md](../../lab/README.md)).
- O perfil de laboratório numa pasta de produtos e **aprovado por uma pessoa** (`hdast profile approve`, ADR 0037). Um agente nunca aprova: diante de `SCOPE_NOT_APPROVED`, ele para e pede.

### Pelo comando de rodada

Comece conferindo a seleção. `changed` usa as mudanças desde o ancestral comum com
`origin/chore/reestruturacao` (ajustável por `--base`) mais os arquivos preparados, as
edições locais e os arquivos novos. Uma mudança só de documentação encerra com aviso.
Arquivos compartilhados e mudanças sem área acendem todo o núcleo. A seleção também
soma as provas das áreas identificadas. [Níveis de integração](testing.md#níveis-de-integração-contra-o-lab)

```bash
uv run python -m tests.integration.lab_round --nivel changed --dry-run
uv run python -m tests.integration.lab_round --nivel changed
```

`--dry-run` mostra o comando do pytest e a seleção. No fechamento, use `--nivel fast`
para o núcleo inteiro e `--nivel prova` para as provas de versão. `--nivel regressao`
seleciona a regressão dirigida e `--nivel tudo` seleciona toda a integração e ponta
a ponta, incluindo `lab_full`.

A rodada segura a trava exclusiva `C:\harness-dast-artefatos\lab.lock` e registra dono
(`--dono`, por padrão o usuário do sistema), horário UTC e nível. Se outra pessoa já
ocupa o laboratório, o comando informa o dono e sai. `--trava` permite apontar para
o caminho compartilhado acordado pela equipe.

A saída padrão é `C:\harness-dast-artefatos\rodadas\<UTC>-<nivel>\`. Use `--saida`
para escolher uma pasta vazia. Ali ficam `junit.xml`, `pytest.log` com `--durations=30`
e `-rfE`, e a subpasta `metricas`. `--sufixo` define `HDAST_IT_STACK_SUFFIX`
e usa `-claude` por padrão. Para executar as medições da V1.7, defina previamente
`HDAST_V17_DEADLINE_EPOCH` com o prazo da rodada em segundos Unix. A medição exige
reserva de tempo e pula quando a variável está ausente.

Para tirar peso do computador local, a rodada completa do núcleo, as provas, a regressão dirigida e a carga também rodam no GitHub Actions: adicione `lab` ao PR (nível `fast`) ou, com o workflow na branch padrão, use **Actions → Laboratório → Run workflow** e escolha o nível (`fast`, `prova`, `regressao`, `carga` ou `tudo`). Os pedaços rodam em paralelo; consulte **Summary** para o resultado e **Artifacts** (`lab-<pedaço>`) para JUnit, métricas e diagnósticos. [Laboratório no GitHub Actions](testing.md#laboratório-no-github-actions)

#### Mudei X, rodo Y

A tabela mostra quantos arquivos cada área seleciona por nível. O
[mapa de áreas](../../tests/integration/lab_areas.toml) contém todos os globs
e arquivos de teste. Quando mais de uma área muda, `changed` reúne seus arquivos.

<!-- lab-areas:start -->

| Mudei... | Exemplo de caminho | Núcleo (`lab_fast`) | Provas (`lab_prova`) |
| --- | --- | ---: | ---: |
| Cerca e proxy | `src/harness_dast/adapters/scope_proxy/**` | 6 | 2 |
| Scan e ZAP | `src/harness_dast/application/scan*.py` | 6 | 5 |
| Autorização e JWT | `src/harness_dast/application/authz/**` | 3 | 4 |
| Valores proibidos e restauração | `src/harness_dast/application/negative*.py` | 2 | 1 |
| Probe, sessões e dados | `src/harness_dast/application/probe*.py` | 7 | 2 |
| Run, parada, reteste e limpeza | `src/harness_dast/application/run*.py` | 3 | 2 |
| OAST | `src/harness_dast/application/oast_*.py` | 1 | 3 |
| crAPI | `lab/crapi/**` | 0 | 4 |
| Clínica Piloto | `lab/pilot/**` | 12 | 12 |
| VAmPI | `lab/vampi/**` | 4 | 11 |
| Imagens e pilha | `compose.yaml` | 4 | 3 |
| Estratégia e reuso | `src/harness_dast/application/strategy*.py` | 2 | 5 |
| Verificações extras | `src/harness_dast/application/extra_checks.py` | 2 | 3 |

<!-- lab-areas:end -->

### À mão, pelos comandos `hdast`

Quando a mudança não tem teste de integração próprio (por exemplo, uma verificação nova do `authz`), rode só as operações afetadas. Exemplo com a Clínica Piloto (passo a passo da pasta e das contas em [lab/pilot/README.md](../../lab/pilot/README.md)):

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

O código da cerca entra na imagem do proxy de escopo. Para provar mudanças em `adapters/scope_proxy/`, no `domain/` da cerca ou em `docker/`, inicie a pilha com `HDAST_STACK_BUILD=1` ou `hdast stack up <produto> --build`. A conferência do rótulo OCI também roda com o build local. Dois checkouts da mesma versão podem ter código diferente, por isso a prova de desenvolvimento exige reconstruir. Se o código do alvo mudou, reconstrua também a imagem dele. [Build local](../comecar/docker.md#construir-a-partir-do-código-local)

### Regressão dirigida (V1.12, L5)

Roteiro **não cego** que prova em poucos minutos que nada regrediu no laboratório, sem a varredura completa. Uma asserção por falha, com o mesmo critério da régua da avaliação (`flaw_status` sobre o gabarito dos casos):

- Clínica Piloto vulnerável: H1 a H10, a H5 pela leitura de dono;
- Clínica Piloto segura: nenhum achado de autorização;
- VAmPI vulnerável: V1 e V3.

```bash
uv run python -m tests.integration.lab_round --nivel regressao
```

Roda `probe` e `authz` em cada cenário e um `scan --only` só nas operações em que o ZAP detecta a falha (`tests/integration/test_regressao_dirigida.py`). Exige Docker, a trava do laboratório quando há outras frentes e uma pilha por vez. O tempo por cenário vai para `HDAST_IT_METRICS_DIR` (`regressao-dirigida-<cenário>`). A H11 (injeção em cabeçalho, ADR 0092) fica fora até a trilha F poder detectá-la. Roteiro de regressão, não nota: não substitui o degrau 4 nem a rodada cega.

Medição da coordenação em 2026-11-17: 715,24 s (11min55s), com 14 testes aprovados e
26 combinações inaplicáveis puladas. Clínica vulnerável: 419,4 s; segura: 181,2 s;
VAmPI vulnerável: 62,5 s. O tempo total do pytest inclui encerramentos e sobrecarga
que não entram nesses tempos por cenário. Evidências externas em
`C:\harness-dast-artefatos\v1-12-lab\retomada-20261117\regression.log` e `metrics-regression/`.

## Degrau 4. Varredura completa

Só no fechamento de versão, ou quando muda o motor ou a política padrão do ZAP:

```bash
HDAST_IT_METRICS_DIR=./medidas uv run pytest -m lab_full
```

Ele roda `hdast run` com todas as operações e a política padrão, no VAmPI e na Clínica Piloto, em modo vulnerável e seguro, e grava as medições. Os resultados e as medições entram no relatório da versão (`docs/arquivo/reviews/relatorio-v1.N.md`). Escolher operações ou regras olhando o gabarito das falhas plantadas é proibido neste degrau.

## Degrau 5. Rodada cega

Ao fechar versão ou ao mudar skill, guia ou mensagem que orienta o agente. Roteiro e regras em [testing.md](testing.md) (seção da avaliação cega) e em [avaliacao-das-skills.md](avaliacao-das-skills.md). Quando só uma skill mudou, um caso basta.

## Regras que não mudam

- **Só no laboratório.** Os degraus 3 a 5 rodam contra os alvos locais (Clínica Piloto, VAmPI, crAPI), nunca contra produto real.
- **Atalho só reduz.** `--only`, `--max-minutes` e afins diminuem o que roda. Nenhum atalho muda escopo, limites, janela ou autorização do perfil.
- **Pilha limpa a cada rodada.** Subir a pilha leva menos de um minuto, e o ZAP guarda alertas da rodada anterior, que se misturariam aos da seguinte. Use `stack down` e `stack up` entre rodadas.
- **Sem "fita gravada".** Repassar pela cerca os pedidos da auditoria do proxy não prova nada: a auditoria guarda o caminho já decodificado, e a cerca julga justamente a forma crua (`%2f`, `;`).
- **O CI roda tudo.** Pular arquivos é só para o laço local.
- **Diga o que não rodou.** Quem entrega uma mudança informa o degrau a que chegou e o que ficou sem prova.

## Com subagentes

Quando o trabalho é dividido entre agentes (plano do ciclo em [../arquivo/plans/](../arquivo/plans/2026-11-14-ciclo-v1-3-a-v1-8.md)):

- O briefing de cada programador diz o degrau máximo dele. Programadores sobem até o degrau 2. Eles não sobem pilha nem tocam alvo.
- O coordenador faz o degrau 3 sobre a branch integrada, no fim da versão, só nas operações que a versão mudou.
- Os degraus 4 e 5 seguem a coluna "Degrau máximo da escada de testes" do plano do ciclo.

## O que ainda falta (V1.1-d)

| Item | Ganho esperado | Estado |
| --- | --- | --- |
| Conferir imagens antes da prova | Evita passar com uma cerca diferente da esperada | A pilha confere a versão do proxy. Mudanças locais exigem build explícito e os alvos ainda precisam ser conferidos |
| Desligar a regra de SSRF 40046 no perfil de laboratório (ligada no fechamento) | Até 500 s a menos na varredura no modo amplo | Aberto; a causa ainda é dedução (planejado para a V1.7) |
| Testes em paralelo (`pytest-xdist`, pede ADR) | De 223 s para 52 s, medido | Aberto |
| Pular `tests/unit/evals/` no laço local | Cerca de 53 s de processador | Descrito acima; sem atalho de comando |
| Documentar o ataque direcionado | O ciclo conserta-e-confere cai de 10 a 23 min para 2 a 4 min | Feito neste guia |
| Pilhas em paralelo | Cerca de 48 min para 23 min no fechamento | Aberto (varreduras concorrentes planejadas para a V1.7) |

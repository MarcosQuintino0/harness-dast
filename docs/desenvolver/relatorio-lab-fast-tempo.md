# Relatório: tempo e confiabilidade do `lab_fast`

- **Data:** 2026-11-18
- **Branch:** `fix/lab-fast-tempo`, a partir da `chore/reestruturacao`
- **Situação:** código pronto e revisado; **a prova em pilha está pendente** (veja o fim)

## Ponto de partida

Linha de base da reestruturação, rodada pela outra sessão:

| Rodada | Código | Resultado | Tempo |
| --- | --- | --- | --- |
| `lab_fast` | `fd611a9` (antes) | 121 passaram, 21 falharam, 43 erros, 16 pulados | 3h29 |
| `lab_fast` | `8d4115f` (depois) | 123 passaram, 23 falharam, 43 erros, 16 pulados | 3h55 |
| `regressao_dirigida` | `8d4115f` | 12 passaram, 15 pulados, 13 erros (`/createdb` do VAmPI com HTTP 500) | 11min40 |

Os 43 erros são os mesmos antes e depois. Nenhuma falha nova vem da reestruturação.

## Causas e o que foi feito

| Causa | Testes | Categoria | Correção |
| --- | --- | --- | --- |
| O teste edita o `target.yml` depois do `stack up`; a CLI e o proxy recusam com `STACK_STALE` (ADR 0081), com razão | `negative`, `include_outcomes`, `multipart_scan`, piloto (`tuned_pilot`) | teste quebrado | `LabCli.restack` sobe a pilha de novo e o probe é refeito; o piloto edita antes da subida. A trava não mudou. |
| Leitura do `scan.json` sem conferir a saída do scan | `include_outcomes`, `multipart_scan` | teste quebrado | Confere a saída e a existência do arquivo antes de ler. |
| Sufixo `-codex` fixo em 9 arquivos, diferente do que o `LabCli` sobe | OAST, crAPI | teste quebrado | Fonte única: `lab_support.stack_suffix()`. |
| `HDAST_IT_METRICS_DIR` e `HDAST_V17_DEADLINE_EPOCH` ausentes | t2 da V1.7, `test_lab_oast` | ambiente | Pasta de métricas temporária por sessão; o t2 pula com motivo quando falta o prazo. |
| Índice fixo de estágio (`stages[3]`) | parada do `run` | teste quebrado | Busca pelo nome do estágio. |
| Campos novos `grant_wait_ms` e `network_ms` na auditoria | sinais | teste quebrado | Aceitos como inteiros não negativos. |
| Build frio da Clínica além de 600 s | primeira subida | timeout de pilha | Imagens do checkout construídas uma vez por sessão (`HDAST_IT_PREBUILT=1`, ADR 0117). |
| A vigia do proxy trava com `approval_changed` sem nenhuma mudança | `negative[secure]`, Oracle (intermitente) | **defeito provável, causa ainda não lida** | `LabCli.stack_down` passa a guardar a categoria da trava (`gate_watch_latch`) em `proxy-watch.jsonl` e avisa no pytest. A correção da vigia fica para depois de ler a causa, por ADR e com o ok do dono. |

## O que muda no laboratório

- **Níveis (ADR 0116, proposto).**
  - `lab_fast` fica com o núcleo de mecanismo: 138 casos em 13 arquivos.
  - `lab_prova` fica com as 15 provas de versão: 67 casos.
  - Nenhum teste foi apagado. Um contrato proíbe teste sem nível e teste em dois níveis.
- **Seleção por área.** `tests/integration/lab_areas.toml` liga as áreas do código aos testes. Mudança em apoio comum, na pilha, na cerca ou no proxy leva ao núcleo inteiro.
- **Comando da rodada:**

  ```bash
  uv run python -m tests.integration.lab_round --nivel changed
  ```

  - Níveis: `changed`, `fast`, `prova`, `regressao`, `carga` e `tudo`.
  - Grava junit, tempos, log, métricas e a causa da trava da vigia.
  - Respeita a trava `lab.lock`: cria só de forma exclusiva e libera só a própria, conferida por token.
- **Imagens do checkout uma vez por sessão** (ADR 0117, proposto). A CLI aceita `HDAST_STACK_BUILD=reuse`: confere as imagens locais e não reconstrói o alvo. Sem esse valor, nada muda.
- **Laboratório no GitHub Actions** (ADR 0118, proposto; `AGENTS.md` atualizado).
  - O `lab.yml` divide cada nível em pedaços (arquivo × modo) que rodam em até 20 máquinas.
  - As imagens são construídas uma vez e guardadas no cache, com chave pelos bytes de todos os insumos do build.
  - Disparo manual ou por PR com rótulo `lab`, nunca em push. Sem segredos, só leitura.
  - Um resumo falha se algum pedaço não rodar de verdade.
- **Rodada cega no Codespaces.** O `.devcontainer/`, o `python -m evals.prepare_codespace` (cópia sem `evals/`, gabaritos, `.git` nem skills `dev-*`) e o guia `rodada-cega-codespaces.md`.

## Como foi feito

- Cada tarefa (T1 a T7) foi feita numa worktree própria, por agentes Codex GPT 6.2 Sol. Quando o Codex parou ou recusou parte da tarefa, um subagente Sonnet 5.5 terminou.
- Cada tarefa foi revisada pelo GPT 6.1 Terra. Os achados corrigidos estão nos commits.
- Ficaram como limites conhecidos:
  - **Liberação da trava.** Há uma janela residual entre fechar e apagar o arquivo. É aceitável porque as sessões só criam a trava de forma exclusiva.
  - **Nível de cada caso.** Não há contrato para o nível exato de cada caso. A troca de nível aparece no diff.
  - **Probe do `error_signals`.** Continua completo, porque o teste examina os sinais do próprio probe.
  - **Subida do `test_lab_finding_verification`.** Não passa pelo `stack_up` e não entra no `stack-up.jsonl`.
- Os gates da Parte A ficaram verdes a cada junção.

## Tempo esperado (ainda não medido)

| Forma de rodar | Antes | Estimativa |
| --- | --- | --- |
| `lab_fast` inteiro no computador | 3h55 | ~90 min, só o núcleo |
| Dia a dia (`--nivel changed`) | — | 5 a 15 min |
| `lab_fast` no GitHub (19 pedaços em paralelo) | — | 15 a 25 min com o cache quente; mais o build frio na primeira vez |

## Prova pendente

Ela depende de a trava `C:\harness-dast-artefatos\lab.lock` estar livre e de o Docker estar aberto, ou de rodar no GitHub.

1. Local, só os arquivos corrigidos, com pilhas `-claude`, um comando por arquivo: `test_lab_negative.py`, `test_lab_include_outcomes.py`, `test_lab_multipart_scan.py`, `test_lab_pilot.py`, `test_lab_run.py` e `test_lab_error_signals.py`. Por exemplo:

   ```bash
   uv run python -m tests.integration.lab_round --nivel fast --arquivo test_lab_negative.py --dono claude-lab-fast
   ```

2. Local, o núcleo inteiro e a regressão, medidos:

   ```bash
   uv run python -m tests.integration.lab_round --nivel fast --dono claude-lab-fast
   ```

   ```bash
   uv run python -m tests.integration.lab_round --nivel regressao --dono claude-lab-fast
   ```

3. Com imagens pré-construídas, comparando o `metricas/stack-up.jsonl`: `HDAST_IT_PREBUILT=1` antes do comando do item 2.
4. No GitHub: PR com o rótulo `lab`, que roda o nível `fast` em paralelo. Depois do merge na `main`, a execução manual libera os outros níveis.
5. Rodada cega curta num Codespace, pelo guia.

Riscos que só a execução mostra:
- memória do crAPI na máquina de 16 GB;
- tempo do build frio e tamanho do cache;
- limite anônimo do Docker Hub com 20 máquinas puxando imagens ao mesmo tempo;
- a causa da trava falsa da vigia, que só aparece quando ela acontece.

# Execução da V1.7: velocidade serial sem perder qualidade

Data: 2026-11-16. Executor: Codex (coordenador GPT 6.1 Sol, esforço xhigh; desenvolvedores GPT 6.1 Terra, esforço high). Coordenação geral, revisão e junção: Claude Code, na sessão do dono.

O plano de referência é `docs/arquivo/plans/2026-11-16-personalization-and-scan-performance.md` (revisão 2). **Leia-o inteiro.** Esta versão executa as seções 3, 4 e 5 dele. Este documento só acrescenta o que é específico desta execução.

## 1. Trabalho em paralelo com a V1.8

Outra sessão do Codex está fazendo a **V1.8 (base da personalização)** ao mesmo tempo, na worktree `C:\harness-dast-wt\v1-8`, branch `feat/v1-8-personalizacao`. Para não atrapalhar uma à outra:

- **Arquivos.** A V1.7 é dona de:
  - `scan_runner.py`, `scan_policy.py`, `scan_plan.py`, `scan_tokens.py`;
  - o limitador e a métrica do proxy de escopo (`adapters/scope_proxy/`);
  - `metrics.json` e o que o produz;
  - o campo novo da carta e do perfil da seleção por tecnologia (seção 5.3 do plano), em `letter*.py`, `profile.py` e `scope_fingerprint.py`.

  Mexa o mínimo possível nos arquivos de carta e perfil, porque a V1.8 também vai precisar deles.
- **ADRs:** use os números **0066 a 0069**. A V1.8 usa de 0070 em diante.
- **Versão:** `1.7.0`. A V1.7 é juntada primeiro; a V1.8 se ajusta depois dela.
- **Documentos compartilhados** (`CHANGELOG.md`, `CLAUDE.md`, `docs/roadmap.md`, `docs/decisoes/README.md`): escreva só a sua parte, em blocos separados, para facilitar a junção.

## 2. Trava do laboratório (obrigatória)

As duas sessões usam o mesmo Docker, e as portas do laboratório são fixas. **Só uma pilha de laboratório pode estar de pé por vez.**

- **Antes de qualquer comando que suba pilha ou rode teste de integração**, crie de forma exclusiva o arquivo `C:\harness-dast-artefatos\lab.lock`. Em PowerShell: `New-Item -ItemType File -Path C:\harness-dast-artefatos\lab.lock -ErrorAction Stop`. Escreva nele `v1.7`, a hora UTC e o que vai rodar.
- **Se o arquivo já existir**, outra sessão está usando o laboratório. Faça trabalho sem Docker (código, testes de unidade, documentação) e tente de novo depois de alguns minutos. Não apague a trava de outra sessão. Se ela tiver mais de 3 horas, registre no relatório e pare de esperar por ela.
- **Ao terminar:** `hdast stack down`, confira `docker compose ls -a`, e só então apague a trava.
- **Docker:**
  - O computador foi reiniciado e o Claude Code reabriu o Docker Desktop. Confira com `docker info`.
  - Se ele travar com `sailor-ingest.sock`, renomeie `%LOCALAPPDATA%\Docker\run` e reabra. Nunca use "Reset to factory defaults".
  - As imagens do laboratório continuam no disco. Reconstrua a do proxy (`stack up ... --build`) sempre que a fonte dele mudar.

## 3. Escopo desta versão

| Passo | O que fazer | Aceite |
| --- | --- | --- |
| 0. Crítica | Antes de programar, lance um subagente GPT 6.1 Terra **medium**, novo e sem esta conversa, para criticar a revisão 2 do plano nos três pontos da seção 12. Incorpore as correções na seção 12 do plano e no que for preciso | Parecer registrado no plano |
| 1. Medição | Seção 5.1 do plano | Tempos por fila, concessão do proxy, atraso do ZAP, rede, login, CPU e memória, separados do tempo de parede |
| 2. Varredura de controle | Camada T3 da seção 4.1: um subconjunto fixo de 6 a 10 operações por API (Clínica Piloto e VAmPI) que contém ao menos uma operação de cada classe de falha de controle, com a mesma política e a mesma força da varredura completa. Versionado em `tests/integration/` para as próximas versões | O subconjunto está no repositório, com a lista de classes cobertas |
| 3. Ritmo único | Seção 5.2 do plano: variantes A e B | Seção 5.4 |
| 4. Seleção por tecnologia | Seção 5.3 do plano, com a proteção contra declaração errada e a atualização da carta, da entrevista das skills e do caso de avaliação | Seção 5.4 |
| 5. Prova | Camadas T1 a T4 da seção 4, com o orçamento da seção 4.4 | Seção 5.4 e metas da seção 10 |
| 6. Validação | Validador GPT 6.1 Terra **medium** novo, como na seção 4.5 | Parecer com decisão `continuar`, `corrigir` ou `bloqueado` |

**Sem rodada cega nesta versão.** O dono decidiu que as rodadas cegas acontecem uma vez, no fim de todas as versões, com dois modelos e duas APIs. Deixe a carta e o caso de avaliação prontos para elas.

## 4. Regras de sempre

- Leia antes: `docs/como-funciona/finalidade-e-uso-responsavel.md`, `CLAUDE.md` (partes A e B), `CONTRIBUTING.md` e `docs/desenvolver/escada-de-testes.md`.
- **Nada específico de um produto:** nenhuma regra, dica ou skill com nomes de campo, rota, papel ou recurso.
- **Parte B no laboratório:**
  - só comandos `hdast` e o suporte de testes;
  - nada de `curl` contra o alvo;
  - não leia `.env`;
  - nunca rode `hdast profile approve` nem `secret set`/`delete`.
- **Gates** depois da última mudança: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run mypy --platform linux`, `uv run lint-imports`, `uv run vulture` e `uv run pytest -q`.
- **CI:** o CI do GitHub não disparou nos últimos PRs. Rode os gates localmente e diga isso no PR.
- **Subagentes:**
  - Programadores GPT 6.1 Terra **high**, no máximo três ao mesmo tempo, cada um com arquivos que não se cruzam e worktree própria criada a partir de `feat/v1-7-velocidade`.
  - QA independente GPT 6.1 Terra **high**.
  - Documentação GPT 6.1 Terra **high**.
  - No fim, remova as worktrees e as branches deles.
- **Commits e PR:**
  - Conventional Commits em português.
  - Push de `feat/v1-7-velocidade` e PR para a `develop`.
  - **Não junte o PR.** Nunca mexa na `main` nem na `develop`, e nunca em `C:\harness-dast`.
- **Detector de segredos:** não afrouxe o `gitleaks`.

## 5. Dúvidas e decisões

O dono delegou as decisões ao Claude Code, e você não tem como perguntar durante a execução. Então:
- **Dúvida que não bloqueia:** escolha a opção **mais conservadora** (a que preserva qualidade, segurança e o contrato atual), registre a decisão e o motivo no relatório e siga.
- **Dúvida que bloqueia** (por exemplo, uma regra do plano que se mostra impossível sem perder qualidade): termine o que puder, e a sua última mensagem traz a pergunta, com as opções e a sua recomendação. O Claude Code responde retomando esta mesma conversa.

## 6. Relatório final (a sua última mensagem)

Em português:
1. Cada passo de 0 a 6: feito, feito em parte ou não feito, com arquivos, testes e prova.
2. Números: o tempo da varredura de controle A e B por API, a redução na mediana, a previsão para a varredura completa e a confirmação pela T4.
3. Qualidade: o resultado de cada critério da seção 3 do plano, por API e modo.
4. A medida de **quanto da varredura poderia rodar em paralelo** (seção 6.1 do plano). Ela decide se a V1.10 começa.
5. As decisões tomadas sozinho e as perguntas que ficaram.
6. Gates, integração, PR, branch e último commit.
7. Subagentes, modelos e esforços usados.

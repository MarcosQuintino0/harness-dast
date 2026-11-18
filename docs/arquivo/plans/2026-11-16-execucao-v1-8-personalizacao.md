# Execução da V1.8: base da personalização

Data: 2026-11-16. Executor: Codex (coordenador GPT 6.1 Sol, esforço xhigh; desenvolvedores GPT 6.1 Terra, esforço high). Coordenação geral, revisão e junção: Claude Code, na sessão do dono.

O plano de referência é `docs/arquivo/plans/2026-11-16-personalization-and-scan-performance.md` (revisão 2). **Leia-o inteiro.** Esta versão executa a **V1.8** dele: as seções 3, 4, 6.1 e 6.2, na parte de contratos. Ela entrega:
- o envelope autorizado;
- o `strategy.yml` versionado;
- a compilação e a validação sem tráfego;
- a migração.

A reutilização entre execuções e o conhecimento executável do produto são da **V1.9**, que vem depois. Este documento só acrescenta o que é específico desta execução.

## 1. Trabalho em paralelo com a V1.7

Outra sessão do Codex está fazendo a **V1.7 (velocidade serial)** ao mesmo tempo, na worktree `C:\harness-dast-wt\v1-7`, branch `feat/v1-7-velocidade`. Para não atrapalhar uma à outra:

- **Arquivos que você não toca**, porque são da V1.7:
  - `scan_runner.py`, `scan_policy.py`, `scan_plan.py`, `scan_tokens.py`;
  - o limitador e a métrica do proxy de escopo (`adapters/scope_proxy/`);
  - a produção do `metrics.json`;
  - o campo de tecnologia declarada da carta.

  O plano compilado da V1.8 **descreve** o trabalho e o executor serial atual **o consome** como está. Mudar o executor é da V1.7.
- **Carta, perfil e impressão digital** (`letter*.py`, `profile.py`, `scope_fingerprint.py`): a V1.7 também mexe neles. Prefira módulos novos, por exemplo `domain/strategy*.py`, `domain/envelope*.py` e `application/strategy*.py`. Nos arquivos compartilhados, faça mudanças pequenas e localizadas.
- **ADRs:** use os números **0070 em diante**. A V1.7 usa de 0066 a 0069.
- **Versão:** `1.8.0`. A V1.7 é juntada **antes** da sua. No fim do seu trabalho, rode `git fetch origin` e veja se a V1.7 já está na `develop`:
  - **Se estiver:** faça `git rebase origin/develop`, resolva os conflitos preservando as duas versões, rode os gates de novo e só então faça push e abra o PR.
  - **Se ainda não estiver:** abra o PR assim mesmo e diga no relatório que falta o rebase. O Claude Code retoma esta conversa para fazê-lo.
- **Documentos compartilhados** (`CHANGELOG.md`, `CLAUDE.md`, `docs/roadmap.md`, `docs/decisoes/README.md`): escreva só a sua parte, em blocos separados.

## 2. Trava do laboratório (obrigatória)

As duas sessões usam o mesmo Docker, e as portas do laboratório são fixas. **Só uma pilha de laboratório pode estar de pé por vez.**

- **Antes de qualquer comando que suba pilha ou rode teste de integração**, crie de forma exclusiva o arquivo `C:\harness-dast-artefatos\lab.lock`. Em PowerShell: `New-Item -ItemType File -Path C:\harness-dast-artefatos\lab.lock -ErrorAction Stop`. Escreva nele `v1.8`, a hora UTC e o que vai rodar.
- **Se o arquivo já existir**, outra sessão está usando o laboratório. Faça trabalho sem Docker e tente de novo depois de alguns minutos. Não apague a trava de outra sessão. Se ela tiver mais de 3 horas, registre no relatório e pare de esperar por ela.
- **Ao terminar:** `hdast stack down`, confira `docker compose ls -a`, e só então apague a trava.
- **Docker:**
  - O computador foi reiniciado e o Claude Code reabriu o Docker Desktop. Confira com `docker info`.
  - Se ele travar com `sailor-ingest.sock`, renomeie `%LOCALAPPDATA%\Docker\run` e reabra. Nunca use "Reset to factory defaults".

## 3. Escopo desta versão

| Passo | O que fazer | Aceite |
| --- | --- | --- |
| 1. Inventário e ADRs | Tabela campo por campo do que hoje afeta segurança e qualidade (seção 6.1 do plano: camadas, três classes de alteração), e ADRs do envelope, da estratégia, da compilação, da aprovação e da migração. Contratos e testes de aceite definidos antes do código | ADRs "Propostos" com contratos, envelopes JSON e códigos de saída |
| 2. Domínio | Modelos congelados do envelope e da estratégia; validadores de faixa, proveniência, composição e impressão digital. Recusar valores inválidos, desconhecidos, NaN e infinito, unidades ambíguas, referências cíclicas e caminhos inseguros, sem ecoar valores que podem ser segredo | Testes de unidade com dado inválido, ausente e malformado |
| 3. Casos de uso e CLI | Validar, comparar e compilar, com prévia sem tráfego. Comandos propostos no plano: `hdast strategy validate`, `hdast strategy diff` e `hdast plan --dry-run`. Decida no ADR o nome e o contrato | Testes de contrato da CLI |
| 4. Execução pelo plano | O executor serial **atual** consome o plano compilado, com as mesmas operações, regras e evidências. Sem mudar o ritmo, que é da V1.7 | T1: a matriz de cobertura com e sem estratégia é igual, item por item |
| 5. Migração | Perfis antigos continuam rodando sem estratégia. A migração é explícita, produz cópia e diff e nunca altera a autorização sozinha. Aprovação antiga nunca vira permissão de parâmetro novo | Testes de recusa de alargamento e de perfil antigo equivalente |
| 6. Skills e avaliação | Atualize o cadastro (`onboard-product`) para explicar a estratégia e as três classes de alteração. Atualize a carta, o caso e a régua da avaliação no mesmo PR, se precisar, sem vazar pistas para a cópia cega | Teste de contrato das skills e teste de vazamento |
| 7. Prova | Camadas T1, T2 e T4 da seção 4 do plano, nas duas APIs (Clínica Piloto e VAmPI), dentro do orçamento da seção 4.4. Sem pares A/B: esta versão não mexe no executor | Aceite da seção 6.2 do plano e meta da V1.8 na seção 10 |
| 8. Validação | Validador GPT 6.1 Terra **medium** novo, como na seção 4.5 do plano | Parecer com decisão `continuar`, `corrigir` ou `bloqueado` |

**Sem rodada cega nesta versão.** O dono decidiu que as rodadas cegas acontecem uma vez, no fim de todas as versões, com dois modelos e duas APIs.

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
  - Programadores GPT 6.1 Terra **high**, no máximo três ao mesmo tempo, cada um com arquivos que não se cruzam e worktree própria criada a partir de `feat/v1-8-personalizacao`.
  - QA independente GPT 6.1 Terra **high**.
  - Documentação GPT 6.1 Terra **high**.
  - No fim, remova as worktrees e as branches deles.
- **Commits e PR:**
  - Conventional Commits em português.
  - Push de `feat/v1-8-personalizacao` e PR para a `develop`.
  - **Não junte o PR.** Nunca mexa na `main` nem na `develop`, e nunca em `C:\harness-dast`.
- **Detector de segredos:** não afrouxe o `gitleaks`.

## 5. Dúvidas e decisões

O dono delegou as decisões ao Claude Code, e você não tem como perguntar durante a execução. Então:
- **Dúvida que não bloqueia:** escolha a opção **mais conservadora** (a que preserva qualidade, segurança e o contrato atual), registre a decisão e o motivo no relatório e siga.
- **Dúvida que bloqueia:** termine o que puder, e a sua última mensagem traz a pergunta, com as opções e a sua recomendação. O Claude Code responde retomando esta mesma conversa.

## 6. Relatório final (a sua última mensagem)

Em português:
1. Cada passo de 1 a 8: feito, feito em parte ou não feito, com arquivos, testes e prova.
2. Os contratos novos: arquivos, comandos, envelopes, códigos de saída e o que muda na aprovação.
3. Qualidade: o resultado de cada critério da seção 3 do plano, por API e modo.
4. Se o rebase sobre a V1.7 foi feito, e os conflitos resolvidos.
5. As decisões tomadas sozinho e as perguntas que ficaram.
6. Gates, integração, PR, branch e último commit.
7. Subagentes, modelos e esforços usados.

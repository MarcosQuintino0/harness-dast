# Execução da V1.9: conhecimento executável do produto

Data: 2026-11-16. Executor: Codex, com coordenador GPT 6.1 Sol (esforço xhigh) e desenvolvedores GPT 6.1 Terra (esforço high). A coordenação geral, a revisão e a junção ficam com o Claude Code, na sessão do dono.

O plano de referência é `docs/plans/2026-11-16-personalization-and-scan-performance.md`, revisão 2. **Leia-o inteiro.** Esta versão executa a **V1.9** dele: seções 1.2, 3, 4, 6.1, 6.2 e 6.3, mais a meta da seção 10.

A V1.7 (velocidade) e a V1.8 (contratos de personalização) já estão na `develop`. Leia os relatórios delas:
- `docs/reviews/relatorio-v1.7.md`;
- `docs/reviews/relatorio-v1.8.md`, `relatorio-v1.8-fechamento.md` e `relatorio-v1.8-rodada3.md`;
- os ADRs 0066 a 0075.

Nenhuma outra versão roda em paralelo agora. Mesmo assim, use a trava do laboratório.

## 1. Escopo

| Passo | O que fazer | Aceite |
| --- | --- | --- |
| 0. Prova pendente da V1.8 | Execute a investigação dirigida de `docs/plans/2026-11-16-v1-8-prova-pendente-rodada3.md`: a regra 90035 na Clínica e a 40008 no VAmPI, com prova dirigida e sem nova T4. Se a causa ficar demonstrada e não houver perda, promova `scan.pacing: proxy` no `init --from-letter` para perfis **novos**, conforme o ADR 0075. Se não ficar demonstrada, mantenha `legacy` e registre | Parecer com a causa, ou a lacuna mantida |
| 1. Inventário e ADRs | Contratos do conhecimento executável: contas, dados, fluxos, observação de efeito, autenticação e reutilização validada. Inclua também a lista de arquivos exportáveis, a invalidação seletiva e o diário de mutações (intenção e estado anterior gravados antes do envio; resultado desconhecido nunca é repetido às cegas nem tratado como sucesso). ADRs a partir de **0076** | ADRs "Propostos" com contratos, envelopes e códigos de saída |
| 2. Domínio e casos de uso | Implemente o passo 1 sem reduzir as travas: observação nunca concede permissão, e o que muda permissão, escopo, teto, janela ou política protegida é decisão humana. Nunca persista token, cookie, resposta inteira, credencial, ID de recurso ou gabarito | Testes de unidade e de contrato, inclusive com dado inválido, ausente e malformado |
| 3. Par automático com 200 | Hoje `application/authz_created_pair.py` exige HTTP 201 e falha em APIs que criam o recurso com 200, como o VAmPI. Aceite também 2xx quando a resposta trouxer um identificador **novo** (que não existia antes da criação) **e** a conta dona conseguir ler o recurso por esse identificador. Sem as duas provas, continua "não testado", com o motivo | Teste de unidade com 201, 200 com identificador novo, 200 sem identificador e 200 com identificador já existente; prova no VAmPI (V3) e na Clínica |
| 4. Atribuição em massa sem prova no VAmPI | Investigue por que a V4 do VAmPI (atribuição em massa no cadastro) não é detectada. Corrija só com regra **genérica**, derivada do contrato OpenAPI, e só dentro da autorização da carta. Se a correção exigir permissão que a carta não dá, registre a lacuna sem ampliar nada | Causa registrada; detecção ou lacuna documentada |
| 5. Skills e reutilização | Atualize as skills (`onboard-product`, `fix-reachability`, `run-scan`, `test-product`) para propor, validar e reaproveitar o conhecimento numa segunda execução, sem reentrevista e sem refazer o alcance quando o conhecimento continua válido. Atualize no mesmo PR a carta, o caso e a régua da avaliação, se precisar, sem vazar pistas para a cópia cega | Testes de contrato das skills e teste de vazamento |
| 6. Protocolo do estudo de reutilização | Atualize `evals/protocolo-da-rodada-cega.md` e o `evals.runner` para o estudo da seção 6.3: lista de arquivos exportáveis, verificador de segredos e vazamento, e como a segunda rodada recebe só esses arquivos, declarados na carta. **Não rode rodadas cegas.** O Claude Code roda as rodadas cegas finais e o estudo depois do merge, com GPT 6.1 Terra medium e Sonnet 5.5 medium, nas duas APIs | Protocolo e runner prontos, com teste; ensaio a seco do canal de exportação nas duas APIs |
| 7. Prova | Camadas T1, T2 e T4 da seção 4 do plano, nas duas APIs (Clínica Piloto e VAmPI), modos vulnerável e seguro, dentro do orçamento da seção 4.4. Sem pares A/B de velocidade, a menos que o passo 0 promova o `proxy` | Aceite da seção 6.2 e meta da V1.9 da seção 10, com detecção igual ou maior que a da V1.8 |
| 8. Validação | Validador GPT 6.1 Terra **medium** novo, como na seção 4.5 do plano | Parecer `continuar`, `corrigir` ou `bloqueado` |

**Sem rodada cega nesta versão.** As rodadas cegas e o estudo de reutilização são feitos pelo Claude Code no fechamento de todas as versões. Deixe tudo pronto para eles.

## 2. Trava do laboratório

- **Antes de subir pilha ou rodar teste de integração**, crie de forma exclusiva `C:\harness-dast-artefatos\lab.lock`. Em PowerShell: `New-Item -ItemType File -Path C:\harness-dast-artefatos\lab.lock -ErrorAction Stop`. Escreva nele `v1.9`, a hora UTC e o que vai rodar.
- **Ao terminar:** `hdast stack down`, confira `docker compose ls -a`, e só então apague a trava.
- **Docker:** se travar com `sailor-ingest.sock` ou `engine.sock`, renomeie `%LOCALAPPDATA%\Docker\run` e `%LOCALAPPDATA%\docker-secrets-engine` e reabra o Docker Desktop. Nunca use "Reset to factory defaults".
- **Imagem do proxy:** reconstrua com `stack up ... --build` quando a fonte do proxy mudar.

## 3. Regras de sempre

- **Leia antes:** `docs/finalidade-e-uso-responsavel.md`, `CLAUDE.md` (partes A e B), `CONTRIBUTING.md` e `docs/escada-de-testes.md`.
- **Nada específico de um produto:** nenhuma regra, dica ou skill com nomes de campo, rota, papel ou recurso. A ferramenta vai receber Swagger de outros produtos.
- **Parte B no laboratório:**
  - só comandos `hdast` e o suporte de testes;
  - nada de `curl` contra o alvo;
  - não leia `.env`;
  - nunca rode `hdast profile approve`, nem `secret set` ou `secret delete`.
- **Gates** depois da última mudança: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run mypy --platform linux`, `uv run lint-imports`, `uv run vulture` e `uv run pytest -q`. O CI do GitHub voltou a funcionar: confira também o resultado no PR.
- **Versão:** `1.9.0`, com CHANGELOG, `CLAUDE.md` (estado), `docs/roadmap.md` e `docs/adr/README.md`.
- **Subagentes:**
  - programadores GPT 6.1 Terra **high**, no máximo três ao mesmo tempo, cada um com arquivos que não se cruzam e worktree própria criada a partir de `feat/v1-9-conhecimento`;
  - QA independente e documentação, GPT 6.1 Terra **high**;
  - no fim, remova as worktrees e as branches deles.
- **Commits e PR:**
  - Conventional Commits em português;
  - push de `feat/v1-9-conhecimento` e PR para a `develop`;
  - **não junte o PR**;
  - nunca mexa na `main` nem na `develop`, e nunca em `C:\harness-dast`.
- **Detector de segredos:** não afrouxe o `gitleaks`.

## 4. Dúvidas e decisões

O dono delegou as decisões ao Claude Code, e você não tem como perguntar durante a execução.
- **Dúvida que não bloqueia:** escolha a opção mais conservadora, a que preserva qualidade, segurança e o contrato atual. Registre a decisão e o motivo no relatório e siga.
- **Dúvida que bloqueia:** termine o que puder. A sua última mensagem traz a pergunta, as opções e a sua recomendação. O Claude Code responde retomando esta mesma conversa.
- **Lacuna de prova que não é defeito de produto** (como na V1.8): registre-a e siga para o PR. Não pare só por ela.

## 5. Relatório final (a sua última mensagem)

Em português:
1. Passos 0 a 8: feito, feito em parte ou não feito, com arquivos, testes e prova.
2. O resultado do passo 0 e a decisão sobre o `proxy`.
3. Qualidade: cada critério da seção 3 do plano, por API e modo, comparado com a V1.8.
4. O par com 200 e a atribuição em massa no VAmPI: o que passou a ser detectado.
5. O que fica pronto para as rodadas cegas e o estudo de reutilização: arquivos, comandos e como exportar.
6. As decisões tomadas sozinho e as perguntas que ficaram.
7. Gates, CI, PR, branch e último commit.
8. Os subagentes usados, com modelos e esforços.

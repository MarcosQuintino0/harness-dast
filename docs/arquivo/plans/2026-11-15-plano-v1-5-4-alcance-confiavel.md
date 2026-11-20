# Plano da versão 1.5.4: alcance confiável e varredura parcial

Data: 2026-11-15. Executor: Codex (coordenador GPT 6.1 Sol, esforço xhigh). Revisão e junção: Claude Code, na sessão do dono.

## Por que esta versão existe

Duas rodadas cegas com o GPT 6.1 Terra (2026-11-14 e 2026-11-15) terminaram **antes da varredura**. A causa não foi o modelo nem a técnica de ataque. Foram regras das skills e mensagens da ferramenta que um agente obediente lê ao pé da letra.

Na rodada de 2026-11-15, com a V1.5.3 e a semente 19, a nota foi 6,29. O fluxo foi este:
- O cadastro saiu perfeito.
- O segundo `probe` alcançou 20 de 31 operações (65%).
- O agente parou e ficou esperando resposta de uma pessoa, que na rodada cega não vem.

Os três motivos:

1. **O 401 esperado da operação de login.**
   - O `probe` exercita a própria operação de login do contrato com credenciais sintéticas.
   - O alvo recusa com 401. Isso é o comportamento **correto** de um login: as contas de teste tinham passado no `preflight`.
   - O `probe` classifica essa recusa como `auth_error`.
   - A skill `fix-reachability` diz: "`auth_error`: se persistir, **pare** e pergunte".
   - O agente parou. O Sonnet, na rodada de referência (nota 9,16), recebeu o mesmo `auth_error` e seguiu adiante. A regra é ambígua.
2. **Conflitos (409) em operações que criam recursos.** Dois cadastros receberam 409 por valor repetido num campo de identificação. Por causa deles, sete operações que dependiam do recurso criado ficaram em `skipped_dependency`. A skill já diz "`unique: true` na regra do campo", mas a saída do `probe` não diz qual campo nem quantas operações aquele produtor está travando.
3. **A regra de parada por alcance.** O `test-product` e o `fix-reachability` mandam **parar** quando o alcance fica abaixo da meta depois das tentativas. **Decisão do dono do projeto (2026-11-15):** abaixo da meta, depois das tentativas, o agente **segue para a varredura com o que alcançou**, marcada como parcial. Relatório, diário e resposta final dizem quais operações ficaram de fora e por quê. As paradas por segurança e autorização continuam como estão.

Há também um defeito da régua da avaliação:

4. **Pontos de triagem sem relatório.** O critério (f) deu 0,75 a uma rodada que não gerou relatório. Verificações como "todo achado alto tem anotação" passam por vacuidade quando não existe `findings.json`. O PR #15 corrigiu o mesmo defeito no critério de falsos alarmes.

Evidências, fora do repositório: `C:\harness-dast-artefatos\rodadas-cegas\piloto-terra61-v153-random-2026-11-15\` (`README.md`, `score.md`, `resposta-2.md`, `trace/runs/*/probe.json`). Referência: `C:\harness-dast-artefatos\rodadas-cegas\piloto-sonnet55-v153-vuln-2026-11-15\`.

## Regra que vale para todos os itens: nada específico de um produto

A ferramenta vai receber o Swagger de produtos diferentes. **Nenhuma** regra, dica, mensagem, skill ou teste de comportamento pode depender de nomes de um produto: nem campos (`crm`, `codigo`, `cpf`), nem rotas (`/api/medicos`), nem papéis (`medico`, `paciente`).

As decisões saem do que vale para qualquer API:
- o contrato OpenAPI: método, caminho, `security`, esquema, `required`, `format`, `pattern`, `maxLength`, `enum`, `readOnly`;
- o perfil: `auth.token_path`, `auth.request_encoding`, as regras de `data-rules.yml` e os fluxos;
- a resposta: código HTTP, `errors[].field` quando o alvo informa, e quais operações dependem de qual produtor.

Os testes de cada regra nova usam **pelo menos dois contratos diferentes**, por exemplo o da Clínica Piloto e o do VAmPI, ou um contrato sintético mínimo escrito no teste. Se um item só funcionar com nomes de um produto, ele está errado: pare e registre no relatório.

## Contexto obrigatório

Leia antes de tudo:
1. `docs/como-funciona/finalidade-e-uso-responsavel.md`: a ferramenta é **defensiva**. Ela roda só em ambientes de teste autorizados e, no desenvolvimento, só no laboratório local, com dados sintéticos.
2. `CLAUDE.md`, partes A e B, e `CONTRIBUTING.md`, incluindo a regra de atualizar a avaliação no mesmo PR.
3. `docs/desenvolver/escada-de-testes.md`.
4. As skills `.claude/skills/fix-reachability/SKILL.md`, `test-product`, `run-scan` e `onboard-product`.
5. `src/harness_dast/domain/outcome.py` e o resto do `probe` (domínio e aplicação), `docs/referencia/data-rules-yml.md` (o `unique`) e `docs/referencia/flows-yml.md`.
6. `evals/README.md`, `evals/protocolo-da-rodada-cega.md` e `evals/runner/checks_triage.py`.
7. O `README.md` da rodada Terra citada acima.

Este trabalho torna a ferramenta **mais confiável** e não acrescenta técnica de ataque. Se algum item ficar fora do que você pode fazer, registre no relatório o item, o motivo e o que faltou. Não recuse em silêncio.

## Itens

| Item | O que fazer | Critério de aceite |
| --- | --- | --- |
| A. Recusa esperada do login | O `probe` reconhece a **operação de login do perfil**, a que casa com `auth.token_path` e o método do login. Uma recusa com credencial sintética (401 ou 403) nessa operação passa a ter um resultado próprio e documentado (por exemplo `auth_rejected_expected`, você decide o nome no ADR), que **não** é `auth_error` e não pede parada. Decida no ADR, com o motivo: (1) se o resultado conta como alcançado na meta e na nota da avaliação; (2) se a operação de login entra na varredura e no `negative`, que é onde se testa injeção no login; (3) como o painel e o relatório a mostram. Decisão no `domain`, com teste | Testes com dois contratos: a operação de login com 401 sai com o resultado novo, e outra operação protegida com 401 continua `auth_error`. O `test_lab_*` adequado mostra o resultado novo no laboratório |
| B. `auth_error` não para tudo | Na skill `fix-reachability`, a parada por `auth_error` persistente vale **para aquela operação**: o agente tenta `auth.account_map` com as contas que a carta dá, registra a operação como pendente da pessoa (no diário e na lista de lacunas) e **segue** com as demais. Mesma lógica para `server_error` e `timeout`, que já dizem "pare nessa operação". Revise a tabela "Se der X, faça Y" para que fique claro o que para **a operação** e o que para **o fluxo**. Para o fluxo só: falta de aprovação, autorização vencida, janela fechada, escopo, ZAP ou alvo fora do ar, `STACK_BUSY`, 429 sem limite informado e dúvida de autorização | Texto da skill e do guia; o teste de contrato das skills passa |
| C. Conflitos que travam dependências | Quando uma operação dá `conflict` (409), o `probe` aponta no resultado (campo `hint` ou equivalente): (1) os campos candidatos, nesta ordem: `errors[].field`, quando o alvo informa; senão, os campos do corpo cujo valor veio de regra sem `unique: true` ou do gerador padrão e que o esquema marca como identificador ou restrito (`required` com `pattern`, `format` ou `maxLength`); (2) quantas operações estão em `skipped_dependency` por causa desse produtor. O resumo do `probe` ordena os produtores com falha pelo número de operações que travam. A skill passa a dizer: conserte primeiro o produtor que mais trava. Nada de nome de campo fixo. Decisão no `domain`, com teste | Testes com dois contratos: o 409 de um produtor com dependentes sai com os campos candidatos e a contagem; sem `errors[].field`, a escolha vem do esquema |
| D. Varredura parcial em vez de parada | Decisão do dono: abaixo da meta depois das tentativas permitidas (ou duas rodadas sem melhora), o agente **segue** para a varredura com o que alcançou. Atualize: (1) `fix-reachability` (critério de parada); (2) `test-product`, inclusive a `description` do cabeçalho e a tabela "quando parar"; (3) `run-scan`, se citar a meta; (4) os guias em `docs/usar/` que repetem a regra. O relatório (`report.md`, `report.html`, painel) e a resposta final dizem **quais operações ficaram fora da varredura e por quê** (resultado do último `probe`), com a cobertura marcada como parcial. Confira se o relatório já mostra isso e complete o que faltar. As paradas da tabela do item B continuam | Skills e guias coerentes entre si; o relatório de uma execução com operações não alcançadas lista as lacunas (teste de relatório); o teste de contrato das skills passa |
| E. Régua sem pontos por vacuidade | No critério (f) da avaliação, sem `findings.json` em nenhuma execução, as verificações que só fazem sentido com achados ("todo achado alto tem anotação", "o diário cobre cada achado alto", "nenhuma nota rebaixa severidade", "não observado nunca virou corrigido") saem como `n/a` e ficam fora da conta, como no critério de falsos alarmes (PR #15). Recalcule a rodada Terra de 2026-11-15 e a referência Sonnet V1.5.3 e informe a nota antes e depois das duas | Teste da régua para rodada sem relatório; a nota da referência Sonnet não muda |
| F. Avaliação no mesmo PR | Atualize o que for preciso em `evals/` (caso, régua, protocolo) para os itens A a E. O teste de vazamento do `prepare` precisa continuar passando: as skills vão para a cópia cega | `tests/unit/evals` e o teste de vazamento passam |

## Como trabalhar

- **Worktree e branch.**
  - O Claude Code já criou a worktree `C:\harness-dast-wt\v1-5-4`, na branch `feat/v1-5-4-alcance-confiavel`, a partir da `develop`. Trabalhe só nela; **nunca** mexa em `C:\harness-dast`.
  - Os subagentes usam worktrees próprias a partir desta branch. Depois de juntar, remova as worktrees e apague as branches dos subagentes.
- **Modelos.**
  - Coordenador: você, GPT 6.1 Sol, esforço xhigh.
  - Programadores: GPT 6.1 Terra, high, no máximo três ao mesmo tempo, com arquivos que não se cruzam.
  - Documentação: GPT 6.1 Terra, medium.
  - QA independente: GPT 6.1 Terra, high, que não programou e tenta quebrar. Ele confere em especial a regra "nada específico de um produto": procura nomes de campo, rota ou papel da Clínica Piloto no código, nas skills, nas mensagens e nos testes de comportamento.
- **ADR:** números **0058 em diante**, com status "Proposto". Mudança de resultado do `probe` é mudança de contrato e exige ADR.
- **Versão:** 1.5.4. Atualize `CHANGELOG.md`, `CLAUDE.md` (o parágrafo de estado), `docs/roadmap.md`, `docs/decisoes/README.md` e `pyproject.toml`, e escreva `docs/arquivo/reviews/relatorio-v1.5.4.md`, curto, no formato do `relatorio-v1.5.3.md`.
- **Testes:**
  - Degrau 2 para tudo: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run mypy --platform linux`, `uv run lint-imports`, `uv run vulture` e `uv run pytest -q`, todos verdes, com a suíte inteira depois da última mudança.
  - Degrau 3 só para os itens A e C, pelos testes de integração (`tests/integration/`, marcadores `integration` e `lab_fast`). O Docker fica em `%LOCALAPPDATA%\Programs\DockerDesktop\`; se travar com `sailor-ingest.sock`, renomeie `%LOCALAPPDATA%\Docker\run` e nunca use "Reset to factory defaults". Derrube pilhas que sobraram antes de subir (`docker compose ls -a`). Use `HDAST_ZAP_API_KEY` aleatória no processo e termine sempre com `stack down`.
  - Sem rodada cega nesta versão: o Claude Code a faz depois da junção, pelo `evals/protocolo-da-rodada-cega.md`.
- **Parte B do `CLAUDE.md` no laboratório:**
  - só comandos `hdast` e o suporte de testes;
  - nada de `curl` contra o alvo;
  - não leia `.env`;
  - nunca rode `hdast profile approve` nem `secret set`/`delete`.
- **Detector de segredos:** não afrouxe o `gitleaks`.
- **Commits** em Conventional Commits, em português.
- **Push e PR:** faça push da branch e abra o PR para a `develop`. **Não junte o PR.** Nunca mexa na `main` nem na `develop` diretamente.

## Relatório final (a sua última mensagem)

Em português:

1. Para cada item de A a F:
   - **feito**, **feito em parte** ou **não feito**, com o motivo;
   - arquivos;
   - testes;
   - prova.
2. As decisões do item A (nome do resultado, se conta como alcançado, se o login entra na varredura) e por quê.
3. A nota antes e depois da rodada Terra e da referência Sonnet (item E).
4. Recusas ou limites do seu modelo, se houver.
5. Gates e integração com números.
6. Link do PR, branch e último commit.
7. Subagentes e modelos usados.
8. O que o Claude Code precisa saber para revisar e juntar.

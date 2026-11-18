# Plano da versão 1.5.3: papéis que compartilham dados no teste entre contas

Data: 2026-11-15. Executor: Codex (coordenador GPT 6.1 Sol, esforço xhigh). Revisão e junção: Claude Code, na sessão do dono.

## Por que esta versão existe

Na rodada cega de 2026-11-15 (Clínica Piloto, modo seguro, V1.5.2), o teste de autorização entre contas comparou duas contas do papel `medico` (`medico_a` e `medico_b`). Deu 5 achados altos de BOLA: o `medico_b` lê e altera pacientes, consultas e receitas criados pelo `medico_a`. Na Clínica Piloto, porém, **todo médico pode ver e cuidar de todo paciente**: é a regra do negócio, nos dois modos. Os 5 achados são alarmes falsos, e a régua da avaliação zerou o critério de falsos alarmes.

A ferramenta não tem como saber se um papel compartilha os recursos entre as contas dele. Quem sabe é o dono do produto, e a informação precisa vir dele, pela carta, como tudo que muda o que é testado.

Evidências da rodada, fora do repositório: `C:\rodadas\piloto-sonnet55-v152b-2026-11-15\` (`score.md`, `trace/runs/*/authz.json`).

## Contexto obrigatório

Leia antes de tudo:
1. `docs/finalidade-e-uso-responsavel.md`: a ferramenta é **defensiva**. Ela roda só em ambientes de teste autorizados e, no desenvolvimento, só no laboratório local, com dados sintéticos.
2. `CLAUDE.md`, partes A e B, e `CONTRIBUTING.md`, incluindo a regra nova de atualizar a avaliação no mesmo PR.
3. `docs/escada-de-testes.md`.
4. Os ADRs 0027, 0036, 0037, 0038 e 0042 (teste entre contas, carta, aprovação, escrita, escrita em recurso de outra conta) e os adendos deles.
5. `evals/README.md` e `evals/cases/clinica-piloto/`.

Este trabalho **reduz** alarmes falsos de um teste que já existe. Ele não acrescenta técnica de ataque. Se algum item ficar fora do que você pode fazer, registre no relatório o item, o motivo e o que faltou. Não recuse em silêncio.

## Itens

| Item | O que fazer | Critério de aceite |
| --- | --- | --- |
| A. Papéis que compartilham recursos | Campo novo da carta (por exemplo, `authz.shared_roles` ou `attack.authz_shared_roles`; você decide o nome no ADR) que lista os papéis cujas contas legitimamente veem e alteram os recursos umas das outras. Ele vira um campo do perfil gerado por `hdast init --from-letter`. Para esses papéis, as verificações `horizontal` e `horizontal_write` **não comparam contas do mesmo papel** e registram o motivo em `not_tested` (por exemplo, `shared_role`). O campo só **reduz** o que é testado, mas mexe no que o relatório diz: decida no ADR se ele exige `source: carta` e a frase da carta (recomendado: sim, porque um agente que o ligasse sozinho esconderia BOLA real) e confirme que ele entra na impressão digital da aprovação (no padrão, vazio, fica fora do cálculo, como as outras chaves novas). O resumo do `profile approve` mostra o campo quando preenchido | Testes de domínio, de aplicação, da carta, da impressão digital e de contrato; um papel compartilhado não gera achado horizontal entre as próprias contas; papéis não listados continuam testados |
| B. Caso da avaliação | A carta da Clínica Piloto em `evals/cases/clinica-piloto/` passa a dizer a regra do negócio: médicos compartilham pacientes, consultas e receitas; pacientes **não** compartilham entre si. O `case.yml` acompanha (fidelidade do perfil confere o campo novo). O teste de vazamento da cópia cega continua passando | `prepare` e `approve` funcionam; `tests/unit/evals` passa |
| C. Skills e dicas | Atualize as skills (`onboard-product`, `fix-reachability`, `run-scan`, `triage-findings`) e, se couber, as dicas do `spec inspect` (ADR 0056): o agente copia da carta os papéis compartilhados; e, para o teste entre contas ter par útil, roteia ao menos uma leitura por objeto para duas contas de um papel **não** compartilhado (na Clínica, as duas contas de paciente) | Texto nas skills; teste de dica, se mexer nela |
| D. Prova no laboratório | `tests/integration/test_lab_authz.py` (marcadores `integration` e `lab_fast`), com a cópia descartável do perfil declarando `medico` como papel compartilhado: no modo seguro, nenhum achado horizontal entre médicos; no vulnerável, os achados entre contas de paciente continuam aparecendo | Testes de integração verdes nos dois modos |

## Como trabalhar

- **Worktree e branch.**
  - O Claude Code já criou a worktree `C:\harness-dast-wt\v1-5-3`, na branch `feat/v1-5-3-papeis-compartilhados`, a partir da `develop`. Trabalhe só nela; **nunca** mexa em `C:\harness-dast`.
  - Os subagentes usam worktrees próprias a partir desta branch. Depois de juntar, remova as worktrees e apague as branches dos subagentes.
- **Modelos.**
  - Coordenador: você, GPT 6.1 Sol, esforço xhigh.
  - Programadores: GPT 6.1 Terra, high, no máximo três ao mesmo tempo, com arquivos que não se cruzam.
  - Documentação, se precisar: GPT 6.1 Terra, medium.
  - QA independente: GPT 6.1 Terra, high.
- **ADR:** use o número **0057**, com status "Proposto".
- **Versão:** 1.5.3. Atualize `CHANGELOG.md`, `CLAUDE.md` (o parágrafo de estado), `docs/roadmap.md`, `docs/adr/README.md` e `pyproject.toml`, e escreva `docs/reviews/relatorio-v1.5.3.md`, curto.
- **Testes:**
  - Degrau 2 para tudo: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run mypy --platform linux`, `uv run lint-imports`, `uv run vulture` e `uv run pytest -q`, todos verdes, com a suíte inteira depois da última mudança.
  - Degrau 3 só para o item D. O Docker fica em `%LOCALAPPDATA%\Programs\DockerDesktop\`; se travar com `sailor-ingest.sock`, renomeie `%LOCALAPPDATA%\Docker\run`. Derrube pilhas que sobraram antes de subir (`docker compose ls -a`). Use `HDAST_ZAP_API_KEY` aleatória no processo e termine sempre com `stack down`.
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

1. Para cada item de A a D:
   - **feito**, **feito em parte** ou **não feito**, com o motivo;
   - arquivos;
   - testes;
   - prova.
2. Recusas ou limites do seu modelo, se houver.
3. Gates e integração com números.
4. Link do PR, branch e último commit.
5. Subagentes e modelos usados.
6. O que o Claude Code precisa saber para revisar e juntar.

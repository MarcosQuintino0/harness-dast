# V1.9.3: teste de autorização que não depende do roteamento do perfil

Data: 2026-11-16. Executor: Codex, **um agente só**, GPT 6.1 Sol com esforço high. Ele implementa, testa, prova no laboratório e documenta. A revisão, o PR, a junção na `develop` e as rodadas cegas ficam com o Claude Code.

Worktree: `C:\harness-dast-wt\v1-9-3`. Branch: `feat/v1-9-3-authz-dono` (já criada a partir da `develop`, `06ffb65`). Logs e evidências fora do repositório vão em `C:\harness-dast-artefatos\v1-9-3\`.

Leia antes: `CLAUDE.md` (inteiro, partes A e B), `docs/desenvolver/escada-de-testes.md`, `docs/desenvolver/testing.md`, os ADRs 0027, 0038 a 0043, 0057, 0077 e 0078, e o código de `src/harness_dast/domain/authz_*.py` e `src/harness_dast/application/authz*.py`.

## 1. O problema, com evidência

A falha H5 da Clínica Piloto é uma autorização quebrada em nível de objeto (BOLA). Logado como paciente A, `GET /api/consultas/2` devolve a consulta do paciente B com `200`, quando o certo seria `403`. O estágio `authz` sabe achá-la: achou na medição de 13/11 (`docs/arquivo/reviews/2026-11-13-lab-v1-1-authz.md`), com o perfil do laboratório, que roteia `buscarConsulta` para `paciente_a` **de propósito** (`lab/pilot/product-profile/target.yml`, linha 82).

Nas rodadas cegas da 1.5.3 à 1.9.2, ninguém achou a H5. Na última (Sonnet, V1.9.2, execução `2026-11-16T20-49-00Z-clinica-piloto-95bf`, perfil em `C:\rodadas\piloto-sonnet55-v192-reuso-vuln-2026-11-16\workspace\products\clinica-piloto\target.yml`):

- O agente mandou **todas** as operações de consulta para `medico_a` (`account_map`). Os pacientes só ficaram com `obterPerfil` e `atualizarPerfil`.
- A carta declara `medico` como papel compartilhado (`authz.shared_roles`), então a comparação entre médicos é pulada (`shared_role`), corretamente.
- `buscarConsulta` nem aparece em `exchanges.json`: o `probe` não teve sucesso nela, porque a criação da consulta falhou por causa da data. `listarConsultas` só teve sucesso como `medico_a`.
- Em `authz.json`, nenhuma linha horizontal tem `buscarConsulta`. A ausência de achado ficou invisível.

A causa está no desenho de `plan_horizontal` (`src/harness_dast/domain/authz_plan.py`): o teste só repete pedidos que o `probe` já fez com sucesso, **com a conta que o perfil escolheu**. O perfil é otimizado para alcançar a API, e a conta que mais alcança (médico, compartilhado) é justamente a que não serve para provar BOLA. Já tentamos resolver pela skill (dicas da V1.5.3) e o agente não seguiu. Pela regra do projeto, a solução tem de ficar no código da CLI.

O contrato da Clínica mostra que a informação existe sem adivinhar nada: `GET /api/consultas` ("paciente vê só as próprias") devolve um array de `ConsultaResponse` com `id`, e `GET /api/consultas/{id}` lê uma consulta por esse `id`.

A V3 do VAmPI (`/books/v1/{book_title}`) é o mesmo tipo de falha. O identificador é o título que a própria conta envia ao criar o livro, e o servidor não o devolve. Ela também não foi achada nas rodadas cegas da 1.9.x.

## 2. Objetivo e aceite

1. **Detecção independente do roteamento.** Com um perfil igual ao da rodada cega (consultas roteadas ao médico compartilhado, pacientes A e B declarados), `hdast authz` no modo vulnerável da Clínica acha a H5 (`authz_horizontal` em `GET /api/consultas/{id}`, alta).
2. **Sem alarme falso.** O mesmo perfil, no modo seguro da Clínica, dá **zero** achado de autorização.
3. **Nada de regressão.** H6 e H7 e os resultados de autorização já provados (Clínica e VAmPI, inclusive `shared_role` entre médicos) continuam iguais.
4. **Lacuna visível.** Quando a leitura de dono não puder ser montada (sem par, sem identificador, sem coleção da conta, identificador ambíguo), a operação aparece em `authz.json`, no relatório e no painel com motivo estável e o que fazer. Nunca pode sumir nem virar "seguro".
5. **VAmPI V3 é meta secundária.** Se a fonte "valor que a própria conta enviou na criação" estiver disponível com segurança (ver 3.2), prove a V3 no laboratório. Se não estiver, documente a lacuna e o motivo, sem contornar.
6. Gates verdes, documentação e ADR em dia.

## 3. Desenho

Antes de codificar, escreva o ADR **0082** ("Leitura de dono no teste horizontal"), com status Proposto. Ele precisa cobrir: o que muda, por que não é ampliação, as fontes de identificador aceitas, o veredito e os motivos novos de "não testado". Se a mudança tocar o schema do perfil ou o envelope JSON, isso também vai no ADR. Prefira não tocar no perfil.

### 3.1 Leitura de dono feita pelo próprio `authz`

Para cada operação `GET` com identificador de objeto no caminho, que o perfil tenha atribuído a uma conta de papel compartilhado ou que o `probe` não tenha alcançado com uma conta de papel não compartilhado com par:

1. **Escolher o par.** O papel precisa ter pelo menos duas contas no perfil, não pode estar em `authz.shared_roles` e não pode estar marcado como público. A ordem segue o perfil e o par é determinístico.
2. **Descobrir os identificadores do dono A**, só pelas fontes da seção 3.2.
3. **Linha de base.** A lê o objeto: precisa dar `2xx` e conter o mesmo identificador. Sem linha de base, nada é acusado.
4. **Repetição.** B lê o mesmo objeto.
5. **Veredito**, com a comparação que o código já tem (`authz_compare.py`):
   - `403`/`404`/`401` significa protegido;
   - `2xx` com o mesmo objeto do dono é achado;
   - qualquer outro caso é `inconclusive` com motivo.

São **só leituras** (`GET`). O teste não cria nada novo nem usa escrita, e `authz.allow_writes` continua mandando em tudo que escreve. Todo pedido passa pelo mesmo caminho de envio do `authz` de hoje: cerca de escopo, `deny_paths`, métodos permitidos, limites, janela, prazo, `stop`, diário de mutações e pilha não desatualizada.

O orçamento é limitado e determinístico: no máximo N objetos por operação e por par (sugestão: 2), com contagem registrada.

### 3.2 Fontes de identificador (nunca adivinhar)

Aceite só estas, em ordem:

1. **Coleção da própria conta.** Uma operação `GET` sem parâmetros de consulta obrigatórios, no mesmo recurso (o caminho da coleção é o prefixo do caminho do item: `/api/consultas` para `/api/consultas/{id}`), que a conta A chama e cuja resposta é um array de objetos com campo `id` (ou com o nome do parâmetro) do tipo do parâmetro. Reaproveite as regras de `authz_pair_inventory.supports_inventory`/`inventory_ids` onde fizer sentido.
2. **Identificadores que já estão em pedidos de sucesso da conta A** no `exchanges.json` (por exemplo, a resposta de uma criação feita por A).
3. **Valor que a própria conta A enviou** no corpo de uma criação de sucesso para o mesmo recurso (caso VAmPI). Só vale se o `ExchangeRecord` ou o diário guardarem esse valor de forma confiável e sem segredo. Se não guardam, **não** passe a guardar corpo inteiro só para isso sem avaliar privacidade no ADR. Registre como lacuna.

Valor vazio, repetido entre contas ou com forma ambígua vira `ambiguous_identifier`. Coleção vazia vira um motivo próprio (por exemplo `owner_collection_empty`). Coleção inacessível para A também vira motivo próprio.

### 3.3 Onde mora cada coisa

Siga as camadas do `CLAUDE.md`:

- **Domínio (puro):** escolha do par, extração e validação de identificador, decisão de "precisa de leitura de dono", veredito e motivos.
- **Aplicação:** envio pelos portos existentes.
- **CLI:** só monta.

Nenhuma regra com nome de produto em `src/` ou `.claude/`: nada de "consulta", "paciente", "book" no código. Respeite complexidade 10, funções de até 40 linhas e arquivos de até 300 linhas, o `lint-imports` e o `vulture`.

### 3.4 Relatório, painel e skills

- `report.md`, `report.html` e a aba de autorização do painel listam as operações sem leitura de dono, com o motivo e a ação sugerida. Exemplos: "declare duas contas do mesmo papel na carta"; "não há coleção da conta que traga o identificador".
- As skills (`onboard-product`, `fix-reachability`, `run-scan`, `triage-findings`) ganham **uma** frase explicando que o `authz` monta a leitura de dono sozinho e que a lacuna aparece no relatório. Sem instruções específicas de produto. Rode o verificador de links.

## 4. Testes

- **Unidade, espelhando `src/`:** escolha do par (papel compartilhado, papel sem par, papel público, ordem), cada fonte de identificador (válida, ausente, vazia, ambígua, malformada, tipo errado, coleção com filtro na consulta), veredito (protegido, achado, inconclusivo, sem linha de base) e orçamento.
- **Defeito reproduzido:** um teste com o perfil roteando a leitura por identificador para um papel compartilhado e com duas contas de outro papel com coleção própria. Ele falha antes da mudança e passa depois.
- **Integração (degrau do laboratório):** um teste novo em `tests/integration/`, seguindo `test_authz_directed_observation.py`/`test_lab_authz.py`, com um perfil que **imita o da rodada cega**. Use uma cópia do perfil do laboratório com o `account_map` das consultas no médico e `shared_roles: [medico]`, sem editar `lab/pilot/product-profile`. Aceite: H5 achada no vulnerável e zero achado de autorização no seguro.
- **VAmPI:** rode o teste de autorização existente para conferir que nada regrediu. Se a V3 entrar (3.2, item 3), prove-a também.
- **Escada de testes:** sem varredura completa do ZAP e sem rodada cega. As rodadas cegas ficam com o Claude Code.

## 5. Opção de ritmo nas rodadas cegas (pequena, separada)

O dono quer a próxima rodada cega com o ritmo novo (`scan.pacing: proxy`), sem que isso vire padrão do produto (o ADR 0075 continua sem promoção).

- Acrescente a `evals/runner prepare` a opção `--pacing {legacy,proxy}`, com padrão `legacy`.
- Com `proxy`, ela grava `scan.pacing: proxy` **só na cópia do modelo** dentro do workspace da rodada (`workspace/products/_template/target.yml`). Confira como o `prepare` monta o workspace.
- A escolha fica registrada no `meta.json` da rodada e no `measure`, para que comparações futuras saibam que o ritmo mudou.
- Não muda o repositório, o `init --from-letter` nem o padrão do modelo.
- Teste de unidade da opção. Documente em `evals/protocolo-da-rodada-cega.md`.
- Se `scan.pacing` exigir algo além do perfil (aprovação, pilha), confira e documente. Não ligue nada que amplie escopo.

## 6. Laboratório e travas

- **Antes de subir pilha ou rodar integração:** crie `C:\harness-dast-artefatos\lab.lock` de forma exclusiva. Se ele já existir, espere e não apague o de outra pessoa.
- **No fim:** rode `hdast stack down`, confira que `docker compose ls -a` está vazio e apague a trava.
- **Pilhas novas suas:** use o sufixo `-claude` ou `-codex`. Nunca use "Reset to factory defaults" no Docker.
- **Contra o alvo:** só comandos `hdast`. Nunca rode `curl` ou script contra o alvo e nunca leia `.env`.
- **Proibido:** rodar `profile approve`, `secret set` ou `secret delete`. Os testes de integração usam o mecanismo de aprovação que já existe nos testes.

## 7. Documentação e entrega

- **Documentação:**
  - ADR 0082;
  - `CHANGELOG.md`, em seção V1.9.3;
  - `docs/roadmap.md`;
  - o parágrafo de estado do `CLAUDE.md`, curto, no mesmo estilo dos outros, dizendo o que foi provado e só no laboratório;
  - o guia de autorização em `docs/usar/`, se existir;
  - um relatório curto `docs/arquivo/reviews/relatorio-v1.9.3.md`, com evidência, comandos, resultados e limites.
- **Gates**, todos verdes, com a saída guardada em `C:\harness-dast-artefatos\v1-9-3\`:

  ```
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy
  uv run lint-imports
  uv run vulture
  uv run pytest
  ```

  Se existir o roteiro `C:\harness-dast-artefatos\v1-9-2-bom\run-gates.ps1`, rode-o também: ele inclui cobertura, diff-cover e gitleaks.
- **Git:**
  - commits em Conventional Commits, por assunto, terminando com `Co-Authored-By: GPT 6.1 Sol <noreply@openai.com>`;
  - push na branch `feat/v1-9-3-authz-dono`;
  - **não abra PR e não faça merge**;
  - nunca use `--no-verify`, nunca use `git add -A` na pasta `C:\harness-dast`, nunca force-push.
- **Perguntas:** se precisar escolher entre alternativas, escolha a mais conservadora (falhar fechado) e registre no relatório. Não pare para perguntar.

## 8. Relatório final (resposta do Codex)

Em português e curto:

1. O que mudou, por camada.
2. O ADR.
3. O resultado da prova no laboratório (H5 vulnerável e seguro, VAmPI, regressões), com os caminhos das evidências.
4. A situação da V3.
5. A opção `--pacing`.
6. Os gates.
7. Commits e hash final.
8. O que não foi feito ou não foi provado.

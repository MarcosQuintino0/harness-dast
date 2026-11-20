# Relatório da versão 1.5.4

Data: 2026-11-15. Branch: `feat/v1-5-4-alcance-confiavel`. Plano: [V1.5.4](../plans/2026-11-15-plano-v1-5-4-alcance-confiavel.md). Decisões: ADRs [0058](../../decisoes/0058-recusa-esperada-login.md), [0059](../../decisoes/0059-diagnostico-conflitos.md) e [0060](../../decisoes/0060-regua-sem-vacuidade.md), **Propostos**.

Entrega: itens A a F implementados, QA independente, gates completos e três casos de integração aprovados após corrigir uma asserção do suporte. PR destinado à `develop`, sem merge pelo Codex. `domain/` e `application/` abaixo pertencem a `src/harness_dast/`.

## Entrega e aceite

| Item | Mudança e arquivos principais | Testes e prova |
| --- | --- | --- |
| A. Recusa esperada do login | **Feito.** `domain/{outcome,probe_result,scan_plan}.py`, `application/probe_runner.py` e ADR 0058 distinguem `auth_rejected_expected`; `reached` soma sucessos e recusas esperadas. | Dois contratos sintéticos conferem método/caminho e preservam `auth_error` protegido; CSRF não é reclassificado. Laboratório nos dois modos: login 401 esperado; no seguro a operação protegida continua 403/`auth_error`. |
| B. Falha localizada | **Feito.** `.claude/skills/fix-reachability/SKILL.md` e `docs/usar/problemas-comuns.md` interrompem só a operação após as tentativas permitidas e registram a pendência. | Contratos de skills e links passaram; paradas de autorização, escopo, janela, aprovação, indisponibilidade, `STACK_BUSY` e 429 sem limite continuam explícitas. |
| C. Conflitos e dependências | **Feito.** `domain/probe_conflict.py`, `probe_result.py`, `application/{preview,probe_runner}.py` e ADR 0059 expõem `conflict_fields`, `blocked_dependencies` e ranking `blocked_producers`. | Dois contratos, origem/unique, listas, readOnly, resposta hostil, máscara de segredo e grafo com vários produtores. Laboratório: 409 informa o campo e o produtor bloqueia 11 operações, contadas no resultado. |
| D. Varredura parcial | **Feito.** Skills `fix-reachability`, `test-product`, `run-scan`, dois guias, referências e `domain/{report_*,panel_*}.py` registram operações e motivos do último probe e distinguem cobertura parcial de etapa interrompida. | Testes de JSON, Markdown, HTML, painel e escape; QA reproduziu e confirmou a correção da operação recusada pelo ZAP omitida das lacunas e do parcial indevido no login. |
| E. Triagem sem vacuidade | **Feito.** `evals/runner/checks_triage.py` e ADR 0060 deixam quatro checks dependentes de achados como `n/a` quando não há `findings.json`. | Casos sem arquivo, arquivo vazio válido e achado alto sem triagem. [Recálculo reproduzível](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/results/2026-11-15-v1-5-4/README.md): Terra 6,29 → 5,79; Sonnet 9,16 → 9,16. |
| F. Avaliação no mesmo PR | **Feito.** `evals/{README.md,protocolo-da-rodada-cega.md}`, `runner/checks_reach.py`, testes e evidências acompanham A a E. Nenhuma permissão nova exige alteração da carta. | `tests/unit/evals`, prepare/vazamento e contratos de skills estão na suíte completa verde. A cópia cega continua recebendo as skills sem termos do gabarito. |

## Decisões de alcance e notas

`auth_rejected_expected` vale somente para POST no `auth.token_path` do perfil, com 401/403, preservando rejeição de CSRF. Conta como alcançado na meta e na avaliação; `successes` continua contando só sucesso 2xx. Isso indica uma operação exercitada, sem comprovar autenticação válida das contas. Relatório e painel mostram os dois números e a recusa esperada.

O login permanece fora do `scan` e do `negative`: preservam-se a trava contra muitas credenciais inválidas, o risco de bloqueio de conta e a omissão de pedidos anônimos/sensíveis no arquivo repetível. **Injeção no login permanece não testada.** O resultado novo não amplia escopo nem autorizações.

O recálculo histórico altera somente (f), sem reclassificar os probes antigos ou modificar seus artefatos. Terra: (f) 0,75 → 0,50 e nota 6,29 → 5,79. Sonnet: (f) 0,875 e nota 9,16 inalteradas. O script registra SHA-256 do score público e lê somente o rastro sanitizado.

## Qualidade e evidências

Saídas externas: `C:\harness-dast-artefatos\v1.5.4\`. [Validação sanitizada, oito probes e manifesto](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/results/2026-11-15-v1-5-4-lab/README.md) estão versionados. A última mudança de teste precedeu a repetição dos seis gates estáticos e da suíte inteira, sem filtro adicional.

| Gate | Resultado |
| --- | --- |
| Ruff | Lint e formatação verdes |
| Mypy Windows e Linux | 825 arquivos em cada plataforma |
| Import-linter | 6 contratos mantidos |
| Vulture | Verde; `blocked_producers` é campo público serializado, com justificativa junto aos demais campos Pydantic |
| Gitleaks e auditoria do lock | Sem segredos ou vulnerabilidades conhecidas; configuração do detector preservada |
| Pytest com cobertura | 9.329 passaram, 4 pulados, 167 desmarcados; 476,78 s |
| Pytest inteiro após a última correção | 9.329 passaram, 4 pulados, 167 desmarcados; 311,97 s |
| Cobertura de ramos | Domínio 98,4%; aplicação 97,2% |
| Cobertura do diff | 95%; 133 de 139 linhas cobertas |
| Integração A/C | Três casos aprovados em duas execuções; inicial 2 aprovados e 1 falha de asserção (454,90 s), reteste seguro 1 aprovado (194,78 s) |

A primeira asserção adicionada pelo coordenador exigia zero `auth_error`. O modo seguro negou legitimamente uma leitura protegida com 403; a classificação era correta e cumpria o item A. O QA confirmou o erro do teste. A prova corrigida confere o login separadamente e preserva as recusas protegidas, sem alterar a produção. A tentativa, os logs e o reteste foram preservados. Um ensaio anterior foi interrompido ao encontrar suporte antigo com quatro contas para um perfil de cinco; a fixture passou a usar `throwaway_pilot_env`, e a pilha residual foi encerrada por `hdast stack down`.

O laboratório usou imagens reconstruídas, chave aleatória do ZAP no processo e dados sintéticos. O vulnerável alcançou 31/31 operações elegíveis (30 sucessos e uma recusa esperada); o seguro, 30/31 (29 sucessos, uma recusa esperada e um erro de autenticação protegido). O conflito teve 11 dependências puladas. As fixtures e o executor encerraram as pilhas; o Compose confirmou `[]` ao final.

O QA independente teve 97 testes dirigidos aprovados, incluindo 11 casos novos, além de 283 testes iniciais de avaliação e skills. Conferiu ausência de dependências de nomes de campo, rota ou papel da Clínica nas regras e nos testes comportamentais novos. Os nomes nos dados de laboratório são evidências do alvo, sem orientar decisões da ferramenta.

## Limites e revisão

- Nenhum item foi recusado ou limitado por regra do modelo. Não há dependência ou técnica de ataque nova, alteração de severidade ou ampliação de permissões.
- O plano limita a prova ao degrau 3 dos itens A e C: sem varredura completa, rodada cega nova ou produto real. O efeito das skills sobre um agente cego será medido pelo Claude Code após a junção.
- Não foram executados `hdast profile approve`, `secret set`/`delete` nem limpeza. As aprovações descartáveis são do suporte de integração previsto pelo projeto.
- Cinco subagentes GPT 6.1 Terra usaram worktrees próprias: núcleo, relatório e avaliação em high; documentação em medium; QA independente em high. O coordenador integrou serialmente e conduziu o laboratório. Worktrees e branches temporárias foram removidas após conferir patches e identidade dos testes; o checkout `C:\harness-dast` não foi utilizado.
- O Claude Code deve revisar os três ADRs como Propostos, a separação entre alcance e sucesso, a exclusão do login, as lacunas e o recálculo isolado. Deve cumprir a revisão humana de módulos críticos prevista em `CONTRIBUTING.md`, conferir os checks do PR e conduzir a rodada cega antes de considerar medido o efeito das skills. O Codex não junta o PR.

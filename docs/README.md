# Documentação por intenção

## Quero operar

Leia os [guias](guides/), [primeiro uso](guides/primeiro-uso.md), [cadastro](guides/cadastrar-um-produto.md)
e [limpeza humana](guides/limpeza-de-dados.md). As [skills de uso](../.claude/skills/) orientam o agente;
as regras de operação estão em [AGENTS.md](../AGENTS.md).

## Quero desenvolver

Leia [CONTRIBUTING](../CONTRIBUTING.md), a [escada de testes](escada-de-testes.md), [testing](testing.md),
os [ADRs](adr/README.md) e o [mapa dos módulos](modules/).
As [skills `dev-*`](../AGENTS.md#descoberta-de-instruções-e-skills) orientam testes, ADR, laboratório, avaliação e fechamento.

## Quero entender

Veja [finalidade](finalidade-e-uso-responsavel.md), [arquitetura](architecture.md),
[políticas de operação](operations/README.md) e [contratos técnicos](reference/).
Para níveis, receitas e limites de confirmação, consulte [verificação de achados](reference/verification.md).

## Quero ver provas

Consulte [reviews](reviews/README.md), [evals](../evals/README.md) e [roadmap](roadmap.md#estado-atual).
Prova ausente continua lacuna; implementação não equivale a validação de laboratório.

## Trabalho de cada pasta

| Pasta | Responsabilidade |
| --- | --- |
| `guides/` | Ensina tarefas e procedimentos humanos |
| `reference/` | Lista contratos, campos, flags e códigos |
| `modules/` | Mapeia código e onde estender cada capacidade |
| `adr/` | Decide e registra alternativas e consequências |
| `plans/` | Propõe trabalho com [estado explícito](plans/README.md) |
| `reviews/` | Prova e limita entregas com data |
| `design/` | Especifica telas e referências visuais |
| `spikes/` | Registra experimentos descartáveis |
| `research/` | Reúne pesquisa sem força de instrução |
| `operations/` | Define políticas de autorização, ameaça e limpeza |

## Onde colocar cada coisa

Mapa para pessoas e agentes; caminhos relativos à raiz do repositório.

| Mudança | Onde colocar |
| --- | --- |
| Regra nova de escopo | `src/harness_dast/domain/` + `tests/unit/domain/`; ADR se mudar contrato |
| Comando novo da CLI | `src/harness_dast/cli/` + `application/` + `docs/reference/cli.md` + `CHANGELOG.md` |
| Verificação de autorização | `domain/authz/` + `application/authz/` dentro de `src/harness_dast/`, com testes espelhados |
| Prova de laboratório | `docs/reviews/AAAA-MM-DD-*.md`, com limites e evidências |
| Plano de versão | `docs/plans/`, com estado no índice |
| Skill de operar | `.claude/skills/<nome>/SKILL.md` |
| Skill de desenvolver | `.claude/skills/dev-<nome>/SKILL.md` |
| Pesquisa | `docs/research/` |
| Estado do projeto | Só `docs/roadmap.md` |
| Histórico de mudanças | Só `CHANGELOG.md` |

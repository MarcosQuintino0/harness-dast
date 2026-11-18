# 0002. Claude Code como runtime do agente

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** AD-02

## Contexto

O projeto precisa de um agente que leia o Swagger e configure o teste. A equipe é de uma pessoa. Manter prompts, contexto, laço de agente e controle de custo é um projeto à parte.

## Decisão

Vamos usar o Claude Code como runtime do agente. O repositório traz `.claude/skills/` e `.claude/agents/`. Cada skill é um roteiro curto que diz quais comandos `hdast` chamar e como interpretar a saída. Não escrevemos laço de agente.

## Alternativas consideradas

- **CLI própria com SDK de LLM.** Descartada para a V1: custo de manter o laço do agente.
- **Camada agnóstica de fornecedor.** Descartada para a V1: abstração sem segundo fornecedor real.

## Consequências

- Quem usa precisa do Claude Code.
- O acoplamento é contido pelo [ADR 0001](0001-dois-planos-agente-propoe-cli-executa.md): skills são Markdown e a lógica não está nelas.
- A qualidade do cadastro de um produto depende do modelo disponível.
- Reavaliar se os classificadores de segurança do provedor bloquearem o fluxo (P-08, medido no spike do M0).
- As skills e os subagentes ainda não existem; estão planejados para o M6.

## Nota de 2026-11-14 (estado; o texto da decisão não mudou)

A consequência "as skills e os subagentes ainda não existem" valia em 2026-11-13, no começo do M2. Desde o M6 existem as skills `onboard-product`, `fix-reachability`, `run-scan` e `triage-findings` (mais `test-product`, da V1.1), os subagentes `spec-analyst` e `findings-triager` e as permissões em `.claude/settings.json` (veja [roadmap](../arquivo/roadmap-historico.md#agente)). Foram avaliadas em rodadas cegas de laboratório ([rodadas de 2026-11-13](../arquivo/reviews/2026-11-13-rodadas-cegas.md) e [rodada da V1.1](../arquivo/reviews/2026-11-13-rodada-cega-v1-1.md)).

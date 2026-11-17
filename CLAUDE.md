# Claude Code

@AGENTS.md

As regras comuns estão em `AGENTS.md`, inclusive as partes A (desenvolver) e B (operar).
Este complemento específico do Claude não as substitui; instruções de maior prioridade prevalecem.

- O Claude Code descobre skills em `.claude/skills/<nome>/SKILL.md` e subagentes em `.claude/agents/*.md`.
- Use `AskUserQuestion` com as opções da skill, incluindo “Não sei / não está na carta”; na avaliação cega siga `EVAL-BRIEFING.md`.
- `.claude/settings.json` é a camada 0 de permissões, por conveniência. A trava efetiva é o código da CLI e a Parte B de `AGENTS.md`.
- V1.11 (verificação de achados): `confirm` é aditivo, a declaração humana é separada e o nível não é probabilidade. Provada só no laboratório (Clínica Piloto e VAmPI, aprovações descartáveis do suporte de integração, sem `profile approve`): só recibos de autorização chegaram a `reproduced`, o único SQL elegível a receita ativa ficou `inconclusive` e `likely_false_positive` nunca ocorreu. Nada foi provado contra produto real nem em rodada cega. Matriz em `docs/reference/verification-calibration.md`; estado e limites no [roadmap](docs/roadmap.md).

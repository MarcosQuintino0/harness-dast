# Claude Code

@AGENTS.md

As regras comuns estão em `AGENTS.md`, inclusive as partes A (desenvolver) e B (operar).
Este complemento específico do Claude não as substitui; instruções de maior prioridade prevalecem.

- O Claude Code descobre skills em `.claude/skills/<nome>/SKILL.md` e subagentes em `.claude/agents/*.md`.
- Use `AskUserQuestion` com as opções da skill, incluindo “Não sei / não está na carta”; na avaliação cega siga `EVAL-BRIEFING.md`.
- `.claude/settings.json` é a camada 0 de permissões, por conveniência. A trava efetiva é o código da CLI e a Parte B de `AGENTS.md`.
- V1.12 (mais achados): bloco `attack` da carta, JWT no `authz` (`alg none`, claims alteradas e chave HMAC fraca offline), injeção em cabeçalhos e cookies, OAST com SSRF guiado pelo contrato, limite de consumo, regras experimentais do ZAP (imagem derivada `hdast/zap`) e inventário. Provada só no laboratório (Clínica Piloto, VAmPI e crAPI); sem produto real e sem rodada cega ainda. Limites de prova no [relatório da V1.12](docs/reviews/relatorio-v1.12.md) e no [roadmap](docs/roadmap.md).
- Só a carta liga, pela CLI (`init --from-letter`, seção `attack`): `attack.pacing`, `attack.inject_headers`, `attack.oast`, `attack.allow_rate_tests`, `attack.experimental_rules` e `attack.inventory`. O agente não as escreve nem as liga.
- V1.11 (verificação de achados): `confirm` é aditivo, a declaração humana é separada e o nível não é probabilidade. Provada só no laboratório (Clínica Piloto e VAmPI, aprovações descartáveis do suporte de integração, sem `profile approve`): só recibos de autorização chegaram a `reproduced`, o único SQL elegível a receita ativa ficou `inconclusive` e `likely_false_positive` nunca ocorreu. Nada foi provado contra produto real nem em rodada cega. Matriz em `docs/reference/verification-calibration.md`.

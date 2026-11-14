# Resposta às constatações: revisão de QA de M1 e M2 (domínio)

Responde ao [relatório de 2026-11-13](2026-11-13-qa-m1-m2.md), que é um registro datado e não foi editado. Este documento diz, para cada constatação, o que foi decidido e onde está o resultado. Escrito em 2026-11-13, na rodada de correção que seguiu o relatório.

Legenda da decisão: **corrigido** = alterado nesta rodada; **aberto** = reconhecido e registrado como item em aberto no [roadmap](../roadmap.md#itens-em-aberto), sem mudança; **não aplicável** = nenhuma constatação foi enquadrada assim.

A coluna "Onde" aponta para o código, o documento ou o ADR. A confirmação final de cada correção de código é dos gates (`ruff`, `mypy`, `lint-imports`, `vulture`, `pytest`) rodados antes do primeiro commit.

| Id | Sev. | Decisão | Onde |
| --- | --- | --- | --- |
| A-01 | B | Corrigido | `domain/urlnorm.py` recusa segmentos com `;`, terminados em ponto ou espaço ou iniciados por espaço, crus ou codificados. Regra e motivo: [ADR 0013](../adr/0013-schema-v1-do-perfil-de-produto.md); recusas listadas em [target-yml.md](../reference/target-yml.md#o-que-o-scopeguard-recusa). Os 8 testes de `test_scope_qa.py` passam a ser exigência permanente |
| A-02 | I | Corrigido | `products/_template/target.yml` reescrito para o schema real (`login_password`, `token_path`, `header_name`); teste de contrato `tests/contract/test_template_profile.py` carrega o template com `pyyaml` ([ADR 0012](../adr/0012-dependencias-tzdata-e-pyyaml.md)) |
| A-03 | I | Corrigido | `--json` aceito antes ou depois do subcomando ([ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md), seção Histórico; [cli.md](../reference/cli.md)) |
| A-04 | I | Corrigido | Sincronização de todos os documentos com o código: [roadmap](../roadmap.md#tabela-de-status) (tabela única), README, SECURITY, CONTRIBUTING, CLAUDE.md, CHANGELOG, `docs/modules/`, `docs/operations/`, `docs/reference/`, `docs/testing.md`. Também listados como existentes: CI, pre-commit, pip-audit, gitleaks, compose e lab |
| A-05 | I | Corrigido | `.github/scripts/check_coverage_floors.py`: prefixo inexistente ou camada com código e nada medido falham; só pasta com apenas `__init__.py` é ignorada, com aviso ([testing.md](../testing.md#cobertura-como-alarme-não-como-meta)) |
| A-06 | M | Corrigido | `TargetError` sai com 6, `CleanupError` com 7; 5 só para ferramenta externa ([exit-codes.md](../reference/exit-codes.md), ADR 0010) |
| A-07 | I | Corrigido | `ExecutionWindow` recusa início igual ao fim por qualquer caminho de construção; `valid_until` aceita só data ([target-yml.md](../reference/target-yml.md#scopewindows), [ADR 0013](../adr/0013-schema-v1-do-perfil-de-produto.md)) |
| A-08 | I | Aberto | O proxy nega faixa privada na lista geral; caminho viável, passo a passo e risco documentados em [docker/scope-proxy/README.md](../../docker/scope-proxy/README.md#o-que-isto-não-garante-riscos-residuais). Sem mudança em `squid.conf`. Confirmação contra alvo real e decisão por ADR: M7 |
| A-09 | M | Corrigido | Mensagens do `ScopeGuard` não repetem o caminho da requisição ([target-yml.md](../reference/target-yml.md#limitações-conhecidas)) |
| A-10 | M | Corrigido | Host inválido não é citado nas mensagens do perfil ([target-yml.md](../reference/target-yml.md#regras-gerais-de-validação)) |
| A-11 | M | Corrigido | [ADR 0012](../adr/0012-dependencias-tzdata-e-pyyaml.md) (`tzdata`, `pyyaml`, com a exceção de pureza do `zoneinfo` e do `pydantic_core`) e [ADR 0013](../adr/0013-schema-v1-do-perfil-de-produto.md) (schema v1) |
| A-12 | M | Corrigido | `hdast` sem argumentos mostra a ajuda e sai com 0; com `--json`, devolve erro de uso em JSON ([cli.md](../reference/cli.md#uso)) |
| A-13 | M | Corrigido | [target-yml.md](../reference/target-yml.md) reescrito a partir dos modelos: todos os campos, tipos, padrões, restrições e erros |
| A-14 | M | Corrigido | `config/settings.py` não encadeia o erro do pydantic e só aceita URL `http` ou `https` ([env-vars.md](../reference/env-vars.md)) |
| A-15 | I | Corrigido | `observability/logging.py` redige exceções, objetos, conjuntos, `bytes`, pares de cabeçalho e as chaves `senha`, `private_key`, `credentials` ([observability.md](../modules/observability.md)) |
| A-16 | M | Aberto | Ações por tag e não por SHA, matriz com Windows, `cancel-in-progress` na `main`, `timeout-minutes` e licença do gitleaks: [roadmap, itens em aberto](../roadmap.md#itens-em-aberto) |
| A-17 | M | Parcial | Corrigido: contrato do import-linter que impede `domain` de importar dependências externas além de pydantic. Aberto: `ignore_names` do vulture por nome no projeto todo e o tamanho de `normalize_request` ([roadmap](../roadmap.md#itens-em-aberto)) |
| A-18 | M | Aberto | Limites de recursos do compose, `ps`/`down` exigindo a chave, `forbidden_ranges` sem IPv4-mapeado e NAT64: [roadmap](../roadmap.md#itens-em-aberto); nota em [lab/README.md](../../lab/README.md) |
| A-19 | M | Corrigido | `KeyboardInterrupt` e `click.Abort` saem com 130 e `INTERRUPTED` ([exit-codes.md](../reference/exit-codes.md)) |

## Itens que o relatório levantou fora da tabela

- **Análise de mutação:** os quatro mutantes que a suíte original não matou (tetos de carga e `Settings` congelado) estão descritos em [testing.md](../testing.md#análise-de-mutação); os testes `*_qa.py` os matam e passam a fazer parte da suíte.
- **Afirmações do lab não reproduzidas pelo revisor** (nenhum contêiner foi iniciado): o `lab/README.md` registra a verificação feita em 2026-11-13 pelo autor; a reprodução independente segue em aberto.
- **Digests das imagens e tags das ações do GitHub**: não verificados pelo revisor; ligados ao item A-16.
- **Hooks do pre-commit** não instalados na máquina da revisão: instruções em [CONTRIBUTING.md](../../CONTRIBUTING.md#ambiente-local).
- **Console `cp1252` no Windows:** registrado em [SECURITY.md](../../SECURITY.md#política-de-dados); sem mudança de código.

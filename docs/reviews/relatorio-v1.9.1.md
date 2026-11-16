# Relatório da V1.9.1

Data: 2026-11-16. Branch `fix/v1-9-1-pilha-e-reuso`. Corrige defeitos que as rodadas cegas da V1.9 revelaram. Provada só no laboratório (Clínica Piloto); nada foi provado contra produto real e nenhuma rodada cega nova foi feita.

## Defeito 1: pilha travada depois de editar o perfil

**Causa.** O proxy gerenciado prende o hash SHA-256 completo do `target.yml` e da aprovação no `stack up` (`policy.json`, bloco `binding`). Qualquer edição posterior do `target.yml`, mesmo num campo livre (`auth.request_encoding`, `probe.setup_path`), faz o proxy negar tudo com 403 `approval_changed`. `hdast profile approval` seguia dizendo `approved` e a CLI não explicava nada; o motivo só estava no `audit.jsonl`. Num caso o agente parou; no outro adivinhou recriar a pilha.

**Correção** ([ADR 0081](../adr/0081-pilha-desatualizada.md), proposto). O proxy não mudou: falha fechada, hash completo.
- Código de erro novo `STACK_STALE` (`StackStale`), com a saída 4 já existente (verificação anterior à execução); envelope de falha comum, sem campos novos. Regra em `domain/stack_binding.py`, caso de uso em `application/stack_freshness.py` (`FreshStackProfiles` por cima do repositório que confere a aprovação: `SCOPE_NOT_APPROVED` tem prioridade), leitura do vínculo em `adapters/scope_proxy/binding_source.py`.
- `preflight`, `probe`, `scan`, `authz`, `negative` e `run` (fora do `--dry-run`) comparam o `target.yml` e a aprovação de agora com o vínculo da pilha ativa do mesmo produto e falham **antes de qualquer pedido**. O `cleanup` (banco, sem proxy), `stack up|down|status` e `stop` não são bloqueados. Vínculo ausente, grande demais ou ilegível falha fechado; política sem vínculo não compara.
- No meio da execução, o cliente do alvo traduz 403 + `X-Hdast-Reason: approval_changed` + corpo fixo do proxy no mesmo erro (não vira achado nem recusa de escopo comum); as outras recusas do proxy e qualquer 403 do alvo seguem como resposta. O `preflight` não converte o erro em verificação reprovada.
- `stack status` ganha `binding` (`fresh`, `stale`, `unbound`, `unreadable`), `stale_parts` e `stale_message`.
- Skills `fix-reachability`, `run-scan`, `onboard-product` e `test-product`: recriar a pilha depois de editar `target.yml` com a pilha de pé, e linha de tabela para `STACK_STALE`. Texto genérico, sem nada de produto.
- Documentação: `docs/guides/problemas-comuns.md`, `docs/reference/cli.md`, `docs/reference/exit-codes.md`.

**Limites.** A conferência compara conteúdo (hash); o proxy compara também a identidade do arquivo. Regravar com o mesmo conteúdo muda a data e o proxy nega mesmo com hash igual: só a tradução do 403 pega isso. O tráfego do ZAP no `scan` não passa pelo cliente da CLI, então um 403 `approval_changed` no meio do `scan` continua só na auditoria do proxy (o `run` confere no início).

**Testes.** Unidade e contrato com dado inválido, ausente e malformado: `tests/unit/domain/test_stack_binding.py` (hash malformado, arquivo ausente, as quatro combinações, `is_stale_refusal` com oito respostas que não devem disparar), `tests/unit/application/test_stack_freshness.py` (sem pilha, outro produto, vínculo ausente e ilegível, ordem com a aprovação), `tests/unit/adapters/scope_proxy/test_binding_source.py` (política real gerada pelo `stack up`, ausente, vazia, JSON inválido, UTF-8 inválido, acima do limite), `tests/unit/adapters/http/test_target_client.py` (servidor local real: refusal vira `StackStale`; `deny_path`, 403 comum, sem corpo do proxy e 500 seguem como resposta), `tests/unit/application/test_preflight_checks_stale.py`, `test_stack.py` (status) e `tests/unit/cli/test_stack_render_stale.py`.

**Prova no laboratório** (`tests/integration/test_v191_stack_stale.py`, Clínica Piloto, com a trava `lab.lock`): `stack up` com perfil aprovado e `auth.request_encoding: form`; edição do campo livre para `json`; `profile approval` segue `approved` com `changed_blocks: []`; `stack status` diz `stale` (`profile`); `preflight` sai com 4 e `STACK_STALE`, com `hint` de `stack down` e `stack up`, **sem nenhuma linha nova na auditoria do proxy** e sem execução aberta; `stack down` e `stack up`; `binding: fresh`; `preflight` passa com `ready: true`. Resultado: 1 passou, 129 s.

## Defeito 2: o estudo de reutilização não recebia conhecimento

**Causa.** As skills só sugeriam `knowledge capture` ("revise e ative se apropriado") e o agente nunca capturava nem ativava, então `knowledge.yml` não existia e `export-reuse` recusava com "Arquivo do canal ausente ou grande demais." nas duas APIs.

**Correção.**
- `run-scan` (e `test-product`, que a conduz) mandam, depois do `run` e antes do `stack down`, `uv run hdast --json knowledge capture <produto> --run <run_id>`, que gera `knowledge.captured.yml`. A ativação continua explícita, da pessoa; as travas não mudaram.
- `export-reuse` aceita `knowledge.captured.yml` na falta de `knowledge.yml` (o ativo vence; ativo grande demais não cai na captura), revalidando pelo modelo como antes; o arquivo exportado continua `knowledge.yml`, com `review_required`. A recusa nomeia o arquivo que falta ou excede o limite e o que fazer. ADR 0079 (proposto) e o protocolo da rodada atualizados.
- O `collect` já copia a pasta inteira do produto para `trace/profile/final/<produto>/`, então `knowledge.captured.yml` chega ao rastro sem mudança. Os testes de vazamento das skills passaram.

**Testes** (`tests/unit/evals/test_reuse.py`): só a captura; os dois arquivos (vence o ativo, mesmo com a captura malformada); nenhum dos dois (mensagem nomeia ambos); captura grande demais; ativo grande demais; captura malformada.

## Defeito 3: documentação da avaliação

`evals/README.md`, passo 1: `stack up --build` não funciona mais (exige aprovação). Documentado o caminho que funciona, conferido no laboratório: `docker compose build scope-proxy` e `docker compose -f lab/pilot/compose.yaml build pilot`, com variáveis descartáveis só para a interpolação (o Compose exige todas as `:?` do arquivo, mesmo para um serviço só; faltar `PILOT_ORACLE_PASSWORD` já falha). O VAmPI é imagem por digest, sem build. O protocolo ganhou a nota de que, no `claude -p` em workspace novo, o aviso "workspace has not been trusted" faz o `permissions.allow` do `settings.json` ser ignorado: as permissões vêm do `--allowedTools` e as negações valem. Só documentação.

## Gates

Registrados no PR (mesmo conjunto das versões anteriores: ruff, format, mypy nas duas plataformas, import-linter, vulture, pytest com cobertura, pisos de cobertura, diff-cover e gitleaks).

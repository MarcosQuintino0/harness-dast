# 0050. Varrer operações que deram "não encontrado" (`scan.include_outcomes`)

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** plano do ciclo V1.3 a V1.8, versão 1.5 (item "atacar funções que deram não encontrado"); o relatório da V1.5 deixou o `run` e o perfil fora. Usa a carta do [ADR 0036](0036-carta-estruturada.md), a aprovação do [ADR 0037](0037-aprovacao-humana-do-escopo.md), o molde de campo do [ADR 0038](0038-authz-padrao-no-run-e-escrita-pela-carta.md), a cobertura do [ADR 0046](0046-cobertura-de-operacoes-com-404.md) e o plano de varredura do [ADR 0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md).

## Contexto

O `scan` só ataca operações que o `probe` alcançou com sucesso (`select_candidates`, `domain/scan_plan.py`: `allowed = {"success"} | (include_outcomes & EXTRA_OUTCOMES)`). Uma operação que respondeu 404 (`not_found`), 400/422 (`validation_error`), 409 (`conflict`), 2xx com falha lógica (`logical_failure`) ou outro 4xx (`client_error`) fica de fora com o motivo `not_success` (ADR 0046 só passou a **explicar** isso). No laboratório isso apagou superfície: a rota existe, o servidor a processa, mas o id sorteado não existe ou o dado não passou.

A flag `hdast scan --include-outcome CLASSE` já existe (`cli/commands/scan.py`, `ScanRequest.include_outcomes`), mas:

- não está no perfil, então o `run` nunca a usa (o `Run._scan` monta `ScanRequest` sem ela);
- **amplia** o que é atacado sem que nada a trave: uma flag que o agente também passa. Hoje ela contraria "flags só reduzem" (`CLAUDE.md`, Parte B) e a regra do ADR 0037 (entra na impressão digital tudo que amplia o que é tocado).

Atacar operações que deram 404 **não amplia o escopo**: as operações já estão em `scope.allow` e o `ScopeGuard` e o proxy continuam decidindo cada pedido. Amplia o que é **atacado**: mais varreduras, mais carga dentro dos limites, e, nos `POST`, `PUT` e `PATCH`, mais escrita de dado sintético que o `cleanup` apaga.

## Decisão

Vamos levar a lista de classes ao perfil (`scan.include_outcomes`), fazer o `run` usá-la e prender a flag ao que o perfil já autoriza.

### 1. Campo do perfil

`ScanConfig` (`domain/scan_config.py`) ganha:

```yaml
scan:
  include_outcomes: [not_found, validation_error]   # padrão: []
```

- Tipo: tupla de `ExtraOutcome`, um `Literal` fechado com as cinco classes que a flag já aceita: `logical_failure`, `validation_error`, `conflict`, `not_found`, `client_error`. `EXTRA_OUTCOMES` (hoje em `scan_plan.py`) passa a ser definida em `scan_config.py` e `scan_plan.py` a importa; um teste garante que o conjunto é o mesmo de antes.
- `max_length=5`; classe repetida é erro (`classe repetida em scan.include_outcomes`); a ordem não importa.
- **Lista fechada, sem curinga.** Fora para sempre: `auth_error`, `csrf_error`, `rate_limited`, `server_error`, `redirect`, `timeout` e as `skipped_*`. Um 401 ou 403 não tem requisição válida e atacá-lo seria insistir numa conta sem permissão; 5xx e 429 pedem que o alvo descanse. O texto de erro diz isso (a dica atual da CLI já diz).
- O `DELETE`, o login, `deny_paths`, fora de `scope.allow` e `PUT`/`PATCH` sem recurso criado ou sem `scan.mutating_methods` continuam fora, **antes** de olhar o resultado (`_decide` em `scan_plan.py` não muda de ordem). Incluir uma classe nunca contorna uma regra de proteção.
- Valor inválido (classe fora da lista, tipo errado, texto no lugar de lista, nulo, elemento não textual): `ConfigError` do perfil, com o caminho do campo (`scan.include_outcomes.0`), saída 2, como todo campo do perfil (ADR 0015/0013).

### 2. Campo da carta (molde do ADR 0038)

A seção `attack` do `carta.yml` ganha `include_outcomes`, uma `Answer` cujo `value` é uma lista de classes. Módulo novo `domain/letter_outcomes.py`, no molde de `letter_writes.py`:

- Ausente, nulo, `desconhecido` ou lista vazia: `[]`, **sem pendência** ("não sei" é "não").
- Valor que não é lista, classe fora da lista fechada ou classe que não é texto: `INVALID_VALUE`, nunca vira classe permitida; a mensagem lista as cinco classes e **não repete** o valor recebido.
- Classe repetida: deduplicada em silêncio (a ordem canônica é a da lista fechada).
- **Exigimos `source: carta` ou `source: pessoa`, sem frase (`quote`).** Justificativa: é a mesma decisão da força do ataque (`attack.strength`): quanto se ataca dentro do escopo já autorizado. Não amplia escopo, método, limite, janela nem conta; quem trava é a aprovação humana (ADR 0037), que passa a mostrar a lista no resumo ("ATACA TAMBÉM OPERAÇÕES QUE DERAM: not_found"). Exigir `source: carta` e `quote`, como `allow_authz_writes` e `path_mode: wide`, é a alternativa mais rígida (ver abaixo); a diferença é que aquelas duas mudam **o que é permitido** (escrever em outra conta; ler caminhos ambíguos), e esta só muda **quanto se ataca do que já é permitido**.
- Geração (`domain/letter_review.py`): o `target.yml` ganha `scan.include_outcomes` **só** quando a lista não é vazia, junto de `scan.strength` quando também há força (`data["scan"]` passa a ser montado com as duas chaves, não mais só com `strength`). `GENERATED_BLOCKS` ganha `scan.include_outcomes`. **Defeito latente a corrigir junto:** `blocks = tuple(name for name in GENERATED_BLOCKS if name.split(".")[0] in data)` listaria `scan.strength` e `scan.include_outcomes` quando só um dos dois existe; a verificação passa a ser pelo caminho pontilhado completo. O cabeçalho do arquivo gerado ganha a linha "Também gerado da carta (ADR 0050): scan.include_outcomes."
- Aviso (não bloqueia, não muda o perfil): `OUTCOMES_ATTACK_EXTENDED` em `domain/letter_warnings.py`, dizendo "o teste ataca também operações que responderam {classes}; nos `POST`, `PUT` e `PATCH` isso cria e altera mais dados sintéticos; confirme com o dono do produto". Entra em `data.warnings` do `init --from-letter`, e o agente o mostra à pessoa.

### 3. Impressão digital da aprovação

`protected_blocks` já inclui o bloco `scan` inteiro (`_scan` em `domain/scope_fingerprint.py`). Acrescentar a chave faria `"include_outcomes": []` entrar no resumo de todo perfil existente e invalidaria **todas** as aprovações. Por isso, como o ADR 0038 fez com `authz.allow_writes`:

- `_scan` passa a omitir, de forma genérica, as chaves do `scan` que não existiam quando a versão 2 do cálculo nasceu (`_LEGACY_SCAN_KEYS` = as nove atuais) **enquanto estiverem no valor padrão**. `include_outcomes: []` (ou ausente) dá a mesma impressão digital de antes; qualquer classe muda a impressão digital do bloco `scan` e exige aprovar de novo. A versão do cálculo (`FINGERPRINT_VERSION = 2`) **não muda**.
- A chave, quando presente, entra **ordenada e sem repetição** (conjunto: a ordem em que o perfil a escreve não pode mudar a impressão digital).
- O resumo legível de `hdast profile approve` (`domain/scope_approval_summary.py`) ganha a linha acima quando a lista não é vazia.

### 4. A flag só reduz

`ScanRequest.include_outcomes` passa de `tuple[str, ...] = ()` para `tuple[str, ...] | None = None`:

- `None` (nenhuma flag): vale a lista do perfil. É o caso do `run` e do `scan` sem flag.
- `--include-outcome X` (repetível) no `scan`: **escolhe um subconjunto** do que o perfil lista. Classe que o perfil não lista é recusada com `ConfigError` ("a classe X não está em scan.include_outcomes do perfil; só a carta pode autorizá-la; peça ao dono do produto"), saída 2, nada enviado.
- `--no-include-outcomes` (nova, no `scan` e no `run`): reduz a lista a vazia, só `success`. No `run`, `RunRequest.include_outcomes: bool = True` e `RunOptions.include_outcomes` (`domain/run_summary.py`, aditivo) registram a escolha em `run.json`.
- **Mudança de contrato, declarada:** hoje `--include-outcome` funciona sem o perfil. Depois deste ADR ela precisa do perfil. É um endurecimento (nenhuma trava afrouxa), mas quebra quem a usava sozinha: entra no `CHANGELOG.md` e em `docs/reference/scan.md`.

### 5. Plano, artefato e relatório

- `ScanTarget`, `PlannedScan` e `ScanEntry` (`domain/scan_plan.py`, `domain/scan_result.py`) ganham `seed_outcome: str | None = None`: a classe do `probe` quando **não** é `success` (a "semente" do ataque). `ScanResult` ganha `include_outcomes: tuple[str, ...]`, a lista efetivamente aplicada. Aditivos; `scan.json` antigo continua legível.
- O **fingerprint dos achados do ZAP não muda** (a semente não é ingrediente: ADR 0022, item 8). O mesmo vazamento achado a partir de uma semente 404 e depois de uma 200 é o mesmo achado, e `report --compare` os une.
- `Finding` ganha `seed_outcome` (aditivo, fora do fingerprint), resolvido pela operação da varredura (`build_resolver` em `domain/report_build.py`).
- **O que o relatório diz** (JSON, Markdown e HTML):
  - Em `coverage`, uma lista `seeded_scans` (operação, método, caminho, classe da semente e status do `probe`) e o aviso fixo: "N operações foram varridas a partir de uma resposta que não foi sucesso (por exemplo HTTP 404). O ataque partiu de um pedido que o alvo recusou ou não achou; achado aqui tem menos prova, e 'sem achado' aqui não indica que a operação é segura."
  - Cada achado vindo de semente não sucesso mostra `(semente: not_found)`.
  - A cobertura de alcance (`reachability`, `reachability_all`, `probe_successes`) **não muda**: ela mede o que o `probe` alcançou com sucesso, e incluir uma classe não faz a operação "alcançada".
- **Efeito no ADR 0046:** operações cuja classe está em `include_outcomes` e foram varridas saem da lista de "sem varredura" (têm entrada no `scan`). As que **não** foram incluídas continuam com o status observado e o motivo (`not_success`, `scan_sem_registro`...); a mensagem ganha, só quando o motivo é `not_success` e a classe não está na lista aplicada, a frase "para varrê-la a carta precisa autorizar `scan.include_outcomes: not_found` (peça ao dono do produto; o agente não liga isso)". Operação incluída que continua sem varredura por outro motivo (`not_learned`, `denied`, `scope`...) mantém o motivo próprio.

### 6. Contrato (aditivo, exceto a flag)

- `target.yml`: `scan.include_outcomes`. `carta.yml`: `attack.include_outcomes`. Envelope do `init --from-letter`: aviso `OUTCOMES_ATTACK_EXTENDED` e o bloco gerado `scan.include_outcomes`.
- `scan.json`: `include_outcomes`, `seed_outcome` por varredura e por plano. `findings.json`: `coverage.seeded_scans`, `findings[].seed_outcome`.
- CLI: `hdast scan --no-include-outcomes`, `hdast run --no-include-outcomes`; `--include-outcome` só dentro do perfil.
- Sem mudança de `schema_version`, de códigos de saída, de `FINGERPRINT_VERSION` do achado nem do cálculo da aprovação.

## Alternativas consideradas

- **Exigir `source: carta` e `quote`, como `allow_authz_writes`.** É a mais rígida e a mais coerente com "escrita só com a carta". Fica a dúvida do dono (relatório da tarefa): a carta típica não diz "pode atacar rota que deu 404", e o recurso quase nunca seria ligado. O custo de ligar por engano é menor que o de escrever em outra conta, e a aprovação humana mostra a lista. Descartada, mas é reversível por ADR novo sem mudar o perfil.
- **Deixar só a flag.** O `run` não a usa; o agente teria de lembrar de passá-la (a lição da V1.4 foi exatamente esta) e nada a travaria. Descartada.
- **Ligar por padrão `not_found` para todos.** Muda o comportamento de todo perfil existente e aumenta a escrita sem ninguém pedir. Descartada; o padrão continua `[]`.
- **Campo por operação (`include_outcomes` por `operationId`).** Mais fino, mas mistura alcançabilidade (que o agente ajusta) com proteção (que a pessoa aprova). Descartada; `scan.only` e `--only` já reduzem por operação.
- **Subir `FINGERPRINT_VERSION` do cálculo da aprovação.** Invalidaria toda aprovação existente à toa. Descartada, como no ADR 0038.
- **Atacar com um corpo "consertado" em vez do corpo que falhou.** É regra de dados e alcançabilidade (`fix-reachability`), não deste ADR.
- **Manter a flag sem o perfil por compatibilidade.** Deixaria a brecha "flag que amplia". Descartada, com o aviso da quebra no `CHANGELOG.md`.

## Consequências

- Operações que respondem 404 por causa de um id sorteado passam a ser atacadas quando a carta quer isso, e o relatório distingue o achado que partiu de uma semente fraca.
- O `run` passa a usar a lista sem flag nova. Perfis existentes não mudam (padrão `[]`, mesma impressão digital, mesmas aprovações).
- Quem usava `scan --include-outcome` sem perfil agora recebe `ConfigError` com a dica de pedir a carta. Atualizar: `docs/reference/scan.md`, `docs/reference/target-yml.md`, `docs/reference/cli.md`, `docs/guides/` e as skills `run-scan` e `test-product` (que passam a orientar a pergunta da entrevista sobre a classe de operação).
- Mais varredura quando ligado: o prazo único e os limites do perfil continuam valendo, e operações do `POST` criam mais dado sintético (o `cleanup` apaga; o aviso diz isso).
- Alvo que responde 404 a tudo (rota errada, base_url errada) leva o `scan` a atacar uma superfície vazia; o aviso de `seeded_scans` e o limite de tempo já protegem, e o `probe` continua o lugar certo de descobrir isso.

## Casos de teste obrigatórios

Unitários (degrau 2):

- `domain/test_scan_config.py`: padrão `()`; cada classe aceita; classe fora da lista (`auth_error`, `server_error`, `success`, vazio, `"NOT_FOUND"`) recusada com o caminho do campo; classe repetida; texto no lugar de lista, nulo, número, lista com elemento não textual; mais de cinco itens; campo desconhecido continua recusado.
- `domain/test_scope_fingerprint.py`: perfil sem a chave e com `include_outcomes: []` têm **a mesma** impressão digital de um perfil anterior (valor gravado no teste); uma classe muda só o bloco `scan`; ordem diferente dá a mesma impressão digital; classe repetida não existe (já recusada); aprovação antiga continua `approved`.
- `domain/test_scope_approval_summary.py`: linha do resumo com e sem a lista.
- `domain/test_letter_outcomes.py`: ausente, nulo, `desconhecido`, lista vazia (nenhuma pendência, `[]`); lista válida com `source: carta` e com `source: pessoa`; classe desconhecida, valor que não é lista, elemento não textual, texto solto (`"not_found"`), lista com classe repetida; a mensagem de erro não repete o valor.
- `domain/test_letter_review.py`: `target.yml` gerado com e sem a lista; com força e lista juntas; **só** `scan.include_outcomes` sem força; `blocks` lista a chave certa (o defeito corrigido); perfil gerado sem o campo é byte a byte igual ao de antes; carta gerada com a lista passa por `ProductProfile.from_data`.
- `domain/test_letter_warnings.py`: o aviso `OUTCOMES_ATTACK_EXTENDED` só com lista não vazia.
- `domain/test_scan_plan.py`: com `{"not_found"}` a operação 404 vira candidata e a de `validation_error` continua `not_success`; `DELETE`, login, `deny_paths` e `PUT` sem recurso criado continuam puladas **mesmo com** a classe incluída; `seed_outcome` preenchido só para não `success`; sem lista nada muda.
- `application/test_scan.py`: sem flag vale o perfil; flag dentro do perfil reduz; flag fora do perfil é `ConfigError` e nada é enviado; `--no-include-outcomes` reduz a vazio; lista do perfil vazia e flag pedida é erro; `ScanResult.include_outcomes` gravado; `--dry-run` mostra `seed_outcome`.
- `application/test_run.py` e `tests/contract/test_cli_run.py`: o `run` passa a lista do perfil ao `scan`; `--no-include-outcomes` e o registro em `run.json`; o envelope não muda.
- `tests/contract/test_cli_scan_report.py`: `--include-outcome` fora do perfil sai com 2; dentro, com 0.
- `tests/contract/test_cli_init_letter.py`: carta com a lista; carta com classe inválida; aviso no envelope.
- `domain/test_report_build.py`, `test_report_markdown.py`, `test_report_html.py`: `seeded_scans` e o aviso fixo; `seed_outcome` no achado; relatório antigo sem os campos; a mensagem do ADR 0046 com e sem a classe na lista aplicada; o status 404 continua aparecendo.

## Como provar no laboratório (degrau 3)

Teste `tests/integration/test_lab_include_outcomes.py`, marcadores `integration` e `lab_fast`, na pasta descartável, com a cópia do perfil da Clínica Piloto **aprovada em código** (`approval_for`/`approve_installed_products`) antes de cada comando:

1. Cópia do perfil com `scan.include_outcomes: [not_found]` e uma regra de dados que faça uma operação de leitura por id (`buscarPaciente`) usar um id que não existe (`generator: constant`, em `data-rules.yml` da cópia). `probe --only buscarPaciente` devolve `not_found` (confirmado em `probe.json`, não presumido).
2. `scan --run <id> --dry-run`: o plano traz `buscarPaciente` com `seed_outcome = "not_found"`. A mesma execução com `--no-include-outcomes` e com o perfil **sem** a lista traz a operação pulada por `not_success`.
3. `scan --run <id> --include-outcome validation_error --dry-run` com o perfil que lista só `not_found`: `ConfigError`, saída 2, nenhuma linha nova no `audit.jsonl` do proxy.
4. Varredura real pequena: `scan --run <id> --only buscarPaciente --max-minutes 3`; `scan.json` traz `entries[].seed_outcome = "not_found"`; o proxy mostra pedidos `GET /api/pacientes/...` do varredor, todos dentro da cerca (nenhum `deny`); `report` traz `coverage.seeded_scans` e o aviso.
5. A aprovação: depois de editar o perfil para ligar a lista, o `preflight` falha com `SCOPE_NOT_APPROVED` até a aprovação em código ser refeita; com `include_outcomes: []` a aprovação antiga continua valendo.
6. `run --skip-scan` e `run` curto (`--max-minutes 3`) com a lista: o estágio `scan` usa a lista do perfil (`run.json`).

Não precisa de varredura completa (degrau 4) para este ADR; o fechamento da versão repete o `run` completo uma vez com a lista ligada e registra o número de operações a mais varridas e os achados que partiram de semente não sucesso.

## Limites conhecidos

- Atacar a partir de um 404 só é útil quando o servidor processa os parâmetros antes de procurar o recurso. Se ele devolve 404 logo na rota, o ZAP gasta tempo sem alcançar nada; `seeded_scans` mostra isso, mas a CLI não mede a utilidade.
- A regra de dados (id que existe) continua sendo a forma certa de alcançar a operação; este ADR é o plano B quando ela não resolve.
- Provado só no laboratório local; nenhum produto real.
- A decisão de aceitar `source: pessoa` sem frase é do dono (ver dúvidas do relatório).

## Divisão em tarefas

**T50a. Perfil, carta, aprovação, plano e flags.** Programador 1, onda 1.

- Novos: `src/harness_dast/domain/letter_outcomes.py`, `tests/unit/domain/test_letter_outcomes.py`, `tests/integration/test_lab_include_outcomes.py`.
- Alterados: `src/harness_dast/domain/scan_config.py`, `scan_plan.py`, `scan_result.py`, `scope_fingerprint.py`, `scope_approval_summary.py`, `letter.py`, `letter_review.py`, `letter_warnings.py`, `src/harness_dast/domain/run_summary.py` (`RunOptions`), `src/harness_dast/application/scan.py`, `scan_runner.py` (preencher `seed_outcome` na entrada), `run.py`, `src/harness_dast/cli/commands/scan.py`, `run.py` (as flags), os testes dos itens acima.
- Não toca: arquivos de relatório (`report_*.py`, `finding*.py`): são da T50b, depois da T49.

**T50b. Relatório e cobertura.** Programador 2, onda 2, depois da T49 integrada.

- Alterados: `src/harness_dast/domain/finding.py` e `finding_build.py` (`seed_outcome`), `report_model.py` (`seeded_scans`, `Coverage`), `report_build.py` (`_coverage`, `_not_tested`), `report_markdown.py`, `report_html.py`, `panel_coverage.py` (mostrar a semente), `docs/reference/relatorio.md`, `docs/reference/finding-schema.md`, e os testes do item "relatório".

**T50c. Documentação e skills** (coordenador ou programador de documentação, no fim da onda): `docs/reference/scan.md`, `target-yml.md`, `cli.md`, `docs/guides/modelo-de-autorizacao.md` e `cadastrar-um-produto.md`, `.claude/skills/run-scan/SKILL.md` e `test-product/SKILL.md` (pergunta da entrevista), e o texto da carta em `docs/guides/` que lista os campos de `attack`. `CHANGELOG.md`, `CLAUDE.md`, `docs/roadmap.md` e `docs/adr/README.md` são do coordenador.

Ordem: T50a antes de T50b (o relatório lê `seed_outcome` e `include_outcomes` de `scan.json`); T50a não depende de T49.

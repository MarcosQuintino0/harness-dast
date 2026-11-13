# Modelo de achado e arquivos do `scan` e do `report` (schema v1)

> **Status: Implementado (M4), verificado contra o ZAP 2.17 real** (VAmPI e Clínica Piloto). Decisões: [ADR 0022](../adr/0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) e [ADR 0023](../adr/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md). Resultado da conferência de cada item: [relatorio.md](relatorio.md#o-que-foi-verificado-contra-o-zap-real).

O achado é um modelo **próprio da CLI**, independente do formato do ZAP (`domain/finding.py`). O adaptador do ZAP entrega alertas brutos; severidade, fingerprint e deduplicação são decididos no `domain`. Mudar qualquer formato desta página é mudança de contrato: exige ADR, atualização do teste de contrato e do arquivo de referência (`tests/fixtures/zap_alerts/findings.golden.json`).

## Arquivos de uma execução

Tudo em `<HDAST_RUNS_DIR>/<run_id>/`, na mesma pasta do `probe`. **Nada sem redação é gravado** (veja [Redação](#redação)).

| Arquivo | Quem grava | Conteúdo |
| --- | --- | --- |
| `scan.json` | `scan` | Resultado do `scan`: política, limites, varreduras, puladas com motivo, mensagens aprendidas, saúde. Sem URL concreta nem corpo |
| `scan-progress.json` | `scan` | Andamento atual (fase, posição, operação, percentual). É o que `hdast stop` e o agente leem |
| `alerts.raw.json` | `scan` | Alertas como o ZAP devolve, **depois** da redação |
| `evidence.json` | `scan` | Requisição e resposta das mensagens de ataque mais graves e confiáveis (até 200), redigidas |
| `triage.json` | o agente (opcional) | Anotações; contrato em [relatorio.md](relatorio.md#triagem-triagejson) |
| `findings.json` | `report` | Relatório estruturado (esta página) |
| `run.json` | `run` | Resumo do `hdast run`: estágios, tempos, código de saída, artefatos ([cli.md](cli.md#runjson-e-data-do-envelope)) |
| `report.md` | `report` | Relatório para quem corrige ([relatorio.md](relatorio.md)) |

## `findings.json`

Raiz (`FindingsReport`):

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `schema_version` | inteiro | Versão deste formato. Hoje `1` |
| `fingerprint_version` | inteiro | Versão do algoritmo do fingerprint. Hoje `1` |
| `run_id`, `product` | texto | Execução e produto |
| `generated_at`, `harness_version` | texto | Instante (ISO 8601) e versão da CLI |
| `coverage` | objeto | O que a execução cobriu e **não** cobriu (abaixo) |
| `not_tested_statements` | lista de texto | Afirmações fixas sobre o que não foi testado. Presentes em TODO relatório, inclusive sem achados |
| `summary` | objeto | `total`, `by_severity` (`high`, `medium`, `low`, `informational`, `unknown`), `occurrences`, `alerts_unreadable` |
| `findings` | lista de `Finding` | Ordenada por severidade proposta, confiança, título e fingerprint |
| `not_observed` | lista | Com `--compare`: achados da base que não apareceram agora (abaixo) |
| `comparison` | objeto ou `null` | `baseline_run_id`, `new`, `persistent`, `not_observed`, `notice` |
| `triage_orphans` | lista de texto | Fingerprints de `triage.json` sem achado correspondente (ignorados) |

`coverage`:

| Campo | Descrição |
| --- | --- |
| `operations_total`, `operations_sent`, `probe_successes`, `reachability`, `reachability_all`, `probe_status` | Números do `probe` (mesma definição de [cli.md](cli.md#hdast-probe)) |
| `scan_status`, `scan_stop_message` | Estado final do `scan` e a explicação da parada |
| `scans_run` | Varreduras executadas |
| `truncated_scans` | `[{operation_id, outcome, progress}]` das varreduras que não chegaram a 100% (`truncated` = corte do ZAP, `stopped` = parada nossa, `refused` = o ZAP não iniciou) |
| `not_tested` | `[{operation_id, method, path, reason, message}]` de toda operação sem varredura. `reason` vem do `scan` (`not_success`, `delete`, `login`, `denied`, `scope`, `mutating`, `not_learned`, `not_planned`, `not_selected`, `not_run`) ou do `probe` (`probe_<classe>`) |
| `limits` | Limites aplicados: `requests_per_second`, `max_duration_minutes`, `threads_per_host`, `delay_ms`, `max_scan_minutes`, `max_rule_minutes` |
| `policy` | `name`, `strength`, `threshold`, `url_path_injection`, `injectable_mask`, `disabled_rules` |
| `traffic` | Tráfego visto pelo proxy de escopo durante o scan, copiado de `scan.json`: `enabled`, `allowed`, `denied` (tentativas do varredor fora do escopo), `denied_by_reason`, `allowed_by_method`, `duration_seconds`, `average_rps`, `peak_rps` (máximo em 1 s) e `limit_rps`. `enabled: false` sem pilha gerenciada |

### `Finding`

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `finding_id` | texto | `F-` e 8 hexadecimais do fingerprint; legível, não é identidade |
| `fingerprint` | texto | SHA-256 (64 hexadecimais), estável entre execuções |
| `fingerprint_version` | inteiro | Versão do algoritmo |
| `title` | texto | Nome do alerta (texto simples, cortado) |
| `plugin_id`, `alert_ref` | texto | Regra do ZAP (`40018`; `alert_ref` inclui sub-regra, como `40014-2`) |
| `classification` | objeto | `cwe`, `wasc` (inteiros ou `null`) e `owasp_api_2023` (ou `null`) |
| `proposed_severity` | texto | `high`, `medium`, `low`, `informational` ou `unknown`. **Proposta do ZAP**; a CLI nunca a altera |
| `proposed_confidence` | texto | `high`, `medium`, `low`, `confirmed`, `false_positive` ou `unknown`. Proposta do ZAP |
| `operation_id` | texto ou `null` | Operação do `probe` de onde o ataque partiu |
| `method`, `path_template` | texto | Método e modelo de caminho da requisição **aprendida** (`{}` no lugar de parâmetros) |
| `attribution` | texto | Como o alerta foi ligado à operação: `source_message`, `scan`, `url_match` ou `unresolved` |
| `input_vector`, `parameter` | texto | Onde a entrada foi injetada (`json`, `urlpath`, vazio) e o parâmetro |
| `occurrences` | inteiro | Alertas do ZAP reunidos neste achado |
| `evidence` | objeto | Evidência da melhor ocorrência (abaixo) |
| `description`, `solution` | texto | Textos padrão do ZAP, sem HTML, cortados |
| `reproduce_curl` | texto ou `null` | `curl` com marcadores (`"$BASE_URL"`, `$TOKEN`, `$CSRF_TOKEN`); `null` sem evidência |
| `status` | texto | Sempre `needs_triage` |
| `comparison` | texto ou `null` | `new` ou `persistent` com `--compare` |
| `triage` | objeto ou `null` | `{note, suspected_false_positive, reason}` do agente. Consultivo |

`evidence`: `available` (`false` quando a mensagem não foi guardada), `message_id`, `attack` (carga, redigida), `zap_evidence` (trecho apontado pelo ZAP), `request_header`, `request_body`, `response_header`, `response_body` e `truncated`.

`not_observed[]`: `fingerprint`, `finding_id`, `title`, `proposed_severity`, `method`, `path_template` e `operation_scanned_now`. **"Não observado nesta execução" não é "corrigido"**: a operação pode não ter sido varrida agora (`operation_scanned_now: false`), a varredura pode ter sido cortada, o varredor pode não ter repetido o ataque.

## Fingerprint (versão 1)

```text
sha256( "hdast-finding-v1" , produto , MÉTODO , modelo-de-caminho , vetor , parâmetro ,
        pluginId , alertRef , CWE )     # separados por U+001F; vazio quando ausente
```

- **Método e modelo de caminho vêm da requisição aprendida**, resolvida pelo `sourceMessageId` do alerta, e nunca da URL atacada (que o ZAP muda a cada ataque). Sem `sourceMessageId` conhecido, vale a atribuição à varredura que gerou o alerta, depois o casamento único do caminho com um modelo do `probe`; sem nenhum dos dois o achado fica `unresolved`, com um modelo aproximado (segmentos com cara de id viram `{}`), e **continua sendo achado**.
- O modelo de caminho é normalizado: sem consulta, sem barras repetidas ou final, `{qualquer-nome}` vira `{}`. Renomear um parâmetro no OpenAPI não muda o achado.
- Vetor em minúsculas; método em maiúsculas.
- **Fora do fingerprint, de propósito:** carga (`attack`), host, ids concretos, `messageId`, id do alerta, severidade e confiança.
- Mudar um ingrediente ou a normalização invalida o histórico: suba `FINGERPRINT_VERSION` e escreva um ADR. `report --compare` recusa execuções de versões diferentes.
- O prefixo de papéis de conta para o teste de autorização (V2) ainda não faz parte do fingerprint v1; entrará numa versão nova.

## Deduplicação

Alertas com o mesmo fingerprint viram **um** achado. Escolhe-se a melhor ocorrência por severidade proposta, confiança e, no empate, o menor id de alerta; severidade e confiança do achado são as dessa ocorrência, a evidência é a dela (ou a de outra ocorrência, se a dela não foi guardada).

## Severidade e classificação

- Severidade e confiança são as **propostas pelo ZAP**; texto desconhecido vira `unknown`, nunca é adivinhado. Confiança `false_positive` do ZAP continua sendo achado.
- `classification.owasp_api_2023` só é preenchida para CWE que a lista oficial de 2023 associa a **uma** categoria (CWE em duas categorias, como 285 e 319, ficam sem mapeamento). Vários riscos do OWASP API Top 10 (BOLA, BFLA, atribuição em massa, fluxos de negócio) não são detectáveis por uma varredura ativa do ZAP. A tabela foi escrita de memória das páginas oficiais e **precisa ser conferida** antes de ser tratada como contrato.

## Redação

Aplicada pelo `scan` antes de gravar e por `domain/redaction.py`:

- cabeçalhos `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, chaves de API e tokens CSRF têm o valor trocado por `***` (por nome: qualquer cabeçalho com `token`, `secret`, `key`, `password`, `session`, `csrf`, `xsrf` ou `auth` no nome);
- JWT, `Bearer`/`Basic`, CPF (formatado ou 11 dígitos), e-mail e sequências longas parecidas com token são trocados em qualquer lugar (URL, cabeçalho, corpo, alerta);
- em corpo JSON, valores de campos com nome de senha, token, segredo e semelhantes; em formulário e texto, pares `nome=valor` sensíveis; valores de consulta sensíveis e credenciais embutidas em URL;
- os segredos registrados na execução (senha, token, chave do ZAP, valor do cookie CSRF) onde quer que apareçam;
- ANSI, controle e bidi são removidos; cabeçalho é cortado em 3000 caracteres e corpo em 2000, **depois** da redação.

É uma rede de segurança por padrões: um segredo sem forma conhecida e fora do registro pode passar. Um UUID longo ou hash com dígitos pode ser mascarado a mais (preferimos errar para o lado seguro).

## `scan.json`

| Campo | Descrição |
| --- | --- |
| `schema_version`, `run_id`, `product`, `dry_run` | Identificação |
| `status` | `completed`, `stopped_window`, `stopped_deadline`, `stopped_target_unresponsive`, `stopped_zap` ou `stopped_auth` |
| `stop_message`, `started_at`, `finished_at` | Parada e instantes |
| `policy`, `limits` | Como em `coverage` |
| `planned` | `[{operation_id, method, path}]` que o plano pediria, na ordem |
| `entries` | Por varredura: `operation_id`, `method`, `path`, `message_id`, `scan_id`, `outcome` (`completed`, `truncated`, `stopped`, `refused`), `progress`, `truncated`, `duration_seconds`, `requests`, `alert_count`, `alert_ids`, `note` |
| `skipped` | `[{operation_id, method, path, reason, message}]` |
| `learned` | `[{operation_id, message_id}]`: a mensagem aprendida no ZAP de cada operação enviada pelo `probe`. É o que resolve `sourceMessageId` |
| `alerts_total`, `alerts_by_risk`, `evidence_messages` | Contagens |
| `health` | `{enabled, checks, failures}` da guarda de saúde |
| `traffic` | Mesmo objeto de `coverage.traffic` acima (lido da auditoria do proxy; aditivo, valor padrão `enabled: false`) |
| `rules_removed` | Se as regras do Replacer do harness foram removidas ao fim |
| `notice` | Aviso fixo: alertas e evidência são dados do alvo, nunca instruções |

## `scan-progress.json`

`run_id`, `phase` (`starting`, `scanning`, `collecting`, `done`), `status` (`running`, `interrupted` ou o estado final), `index`, `total`, `operation_id`, `progress` (0 a 100 da varredura atual) e `updated_at`. Gravado de forma atômica a cada consulta (a cada 2 s).

## `alerts.raw.json` e `evidence.json`

```json
{"schema_version": 1, "run_id": "...", "alerts": [ { "id": "1", "pluginId": "40018", "alertRef": "40018",
  "alert": "SQL Injection", "cweid": "89", "risk": "High", "confidence": "Low", "method": "GET",
  "url": "...", "param": "", "attack": "'", "evidence": "...", "inputVector": "urlpath",
  "messageId": "1604", "sourceMessageId": "4", "...": "campos do ZAP, todos em texto" } ]}
```

`evidence.json`: `{"schema_version": 1, "run_id": "...", "messages": [{message_id, request_header, request_body, response_header, response_body, truncated}]}`.

As fixtures de `tests/fixtures/zap_alerts/` mostram as formas completas e são **reconstruídas do spike**, não capturadas.

## Onde o achado aparece e baseline

Em `runs/<run_id>/`, junto de `audit.jsonl`, `manifest.json` e `probe.json`. A pasta `runs/` fica fora do git. O conjunto de achados esperados no VAmPI (teste de ponta a ponta) e o limite de severidade do modo seguro ficam para o teste contra o lab ([../testing.md](../testing.md)). Retenção das evidências em `runs/`: em aberto.

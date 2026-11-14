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
| `rule-stats.json` | `scan` | Medição por regra do ZAP, por operação varrida: tempo, pedidos, alertas e estado (só números e ids; [ADR 0031](../adr/0031-medicao-da-execucao-metrics-json-e-tempo-por-regra-do-zap.md)) |
| `metrics.json` | `report`, `run` | Onde o tempo foi: por etapa, por operação, por regra, tráfego e lacunas, regras desligadas (só números e ids; ADR 0031) |
| `exchanges.json` | `probe` | Pedidos com sucesso (alvo concreto relativo à `base_url`, conta, status e, para `POST`/`PUT`/`PATCH`, o corpo JSON enviado, sem campos de segredo). Alimenta o `authz`; contrato em [authz.md](authz.md#exchangesjson-gravado-pelo-probe) |
| `authz.json` | `authz` | Resultado do teste de autorização entre contas: verificações, achados de origem própria e o que não foi testado ([authz.md](authz.md)). Só nomes de campo, nunca valores |
| `triage.json` | o agente (opcional) | Anotações; contrato em [relatorio.md](relatorio.md#triagem-triagejson) |
| `findings.json` | `report` | Relatório estruturado (esta página) |
| `run.json` | `run` | Resumo do `hdast run`: estágios, tempos, código de saída, artefatos ([cli.md](cli.md#runjson-e-data-do-envelope)) |
| `report.md` | `report` | Relatório para quem corrige ([relatorio.md](relatorio.md)) |
| `report.html` | `report` | O mesmo relatório numa página única, sem JavaScript nem recurso externo ([ADR 0029](../adr/0029-relatorio-agrupado-pagina-html-e-skill-de-um-pedido-so.md)) |
| `panel/*.html` | `report`, `run`, `panel` | O painel da execução: seis páginas (`summary`, `stages`, `findings`, `coverage`, `terminal`, `time-and-tokens`), sem JavaScript nem recurso externo. Não é contrato de leitura por máquina: leia os arquivos acima ([ADR 0032](../adr/0032-painel-da-execucao.md), proposto) |

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
| `summary` | objeto | `total`, `by_severity` (`high`, `medium`, `low`, `informational`, `unknown`), `occurrences`, `alerts_unreadable`; `total` e `by_severity` são só do ZAP. Aditivo (ADR 0027): `authz_by_severity` (mesmas cinco chaves, achados de autorização entre contas; `{}` quando o estágio não rodou) |
| `findings` | lista de `Finding` | Ordenada por severidade proposta, confiança, título e fingerprint |
| `groups` | lista de `FindingGroup` | Visão agrupada pela causa provável (abaixo). Aditivo (ADR 0029): todo achado de `findings` está em exatamente um grupo; arquivos antigos sem o campo continuam válidos |
| `not_observed` | lista | Com `--compare`: achados da base que não apareceram agora (abaixo) |
| `comparison` | objeto ou `null` | `baseline_run_id`, `new`, `persistent`, `not_observed`, `notice` |
| `triage_orphans` | lista de texto | Fingerprints de `triage.json` sem achado correspondente (ignorados) |
| `authz` | objeto ou `null` | Aditivo (ADR 0027). O `authz.json` da execução, quando o estágio rodou: achados de autorização entre contas, de origem própria e técnica própria (`origin: authz`, `technique`), **separados** de `findings` (que são do ZAP). Contrato em [authz.md](authz.md). O gate (`--fail-on`) conta os dois |

`coverage`:

| Campo | Descrição |
| --- | --- |
| `operations_total`, `operations_sent`, `probe_successes`, `reachability`, `reachability_all`, `probe_status` | Números do `probe` (mesma definição de [cli.md](cli.md#hdast-probe)) |
| `scan_status`, `scan_stop_message` | Estado final do `scan` e a explicação da parada |
| `partial` | `true` quando o `probe` ou o `scan` pararam antes do fim (prazo, janela, login, ZAP ou alvo): o relatório cobre só o que foi coletado e o que não foi varrido não deve ser lido como seguro. Aditivo (ADR 0025) |
| `scans_run` | Varreduras executadas |
| `truncated_scans` | `[{operation_id, outcome, progress}]` das varreduras que não chegaram a 100% (`truncated` = corte do ZAP, `stopped` = parada nossa, `refused` = o ZAP não iniciou) |
| `not_tested` | `[{operation_id, method, path, reason, message}]` de toda operação sem varredura. `reason` vem do `scan` (`not_success`, `delete`, `login`, `denied`, `scope`, `mutating`, `not_learned`, `not_planned`, `not_selected`, `not_run`) ou do `probe` (`probe_<classe>`) |
| `limits` | Limites aplicados: `requests_per_second`, `max_duration_minutes`, `threads_per_host`, `delay_ms`, `max_scan_minutes`, `max_rule_minutes` |
| `policy` | `name`, `strength`, `threshold`, `url_path_injection`, `injectable_mask`, `disabled_rules` |
| `traffic` | Tráfego visto pelo proxy de escopo durante o scan, copiado de `scan.json`: `enabled`, `allowed`, `denied` (tentativas do varredor fora do escopo), `denied_by_reason` (recusa por forma agrupada em `malformed_request`), `denied_by_detail` (o código granular: `path_encoded_slash`, `url_forbidden_char`, `deny_path`...), `path_shape_denied` (recusas por forma do caminho, a base do aviso de cobertura parcial de injeção em caminho), `allowed_outside_allow` (modo amplo: liberados com leitura fora de `scope.allow`), `path_mode` (`strict` ou `wide`; ADR 0026), `allowed_by_method`, `duration_seconds`, `average_rps`, `peak_rps` (máximo em 1 s) e `limit_rps`. `enabled: false` sem pilha gerenciada |

### `Finding`

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `finding_id` | texto | `F-` e 8 hexadecimais do fingerprint; legível, não é identidade |
| `fingerprint` | texto | SHA-256 (64 hexadecimais), estável entre execuções |
| `fingerprint_version` | inteiro | Versão do algoritmo |
| `title` | texto | Nome do alerta (texto simples, cortado) |
| `plugin_id`, `alert_ref` | texto | Regra do ZAP (`40018`; `alert_ref` inclui sub-regra, como `40014-2`) |
| `classification` | objeto | `cwe`, `wasc` (inteiros ou `null`) e `owasp_api_2023` (ou `null`) |
| `proposed_severity` | texto | `high`, `medium`, `low`, `informational` ou `unknown`. **Proposta do ZAP**; a CLI nunca a altera. `unknown` aciona qualquer `--fail-on` diferente de `none` |
| `proposed_confidence` | texto | `high`, `medium`, `low`, `confirmed`, `false_positive` ou `unknown`. Proposta do ZAP |
| `operation_id` | texto ou `null` | Operação do `probe` de onde o ataque partiu |
| `method`, `path_template` | texto | Método e modelo de caminho da requisição **aprendida** (`{}` no lugar de parâmetros) |
| `attribution` | texto | Como o alerta foi ligado à operação: `source_message`, `scan`, `url_match` ou `unresolved` |
| `input_vector`, `parameter` | texto | Onde a entrada foi injetada (`json`, `urlpath`, vazio) e o parâmetro |
| `occurrences` | inteiro | Alertas do ZAP reunidos neste achado |
| `evidence` | objeto | Evidência da melhor ocorrência (abaixo) |
| `description`, `solution` | texto | Textos padrão do ZAP, sem HTML, cortados |
| `reproduce_curl` | texto ou `null` | `curl` com marcadores (`"$BASE_URL"`, `$TOKEN`, `$CSRF_TOKEN`); `null` sem evidência |
| `technique` | texto | Aditivo (ADR 0027). Técnica que produziu o achado; aqui sempre `zap_active_scan`. Os achados de autorização têm as suas em `authz.findings[].technique` |
| `status` | texto | Sempre `needs_triage` |
| `comparison` | texto ou `null` | `new` ou `persistent` com `--compare` |
| `triage` | objeto ou `null` | `{note, suspected_false_positive, reason}` do agente. Consultivo |

`evidence`: `available` (`false` quando a mensagem não foi guardada), `message_id`, `attack` (carga, redigida), `zap_evidence` (trecho apontado pelo ZAP), `request_header`, `request_body`, `response_header`, `response_body` e `truncated`.

`not_observed[]`: `fingerprint`, `finding_id`, `title`, `proposed_severity`, `method`, `path_template` e `operation_scanned_now`. **"Não observado nesta execução" não é "corrigido"**: a operação pode não ter sido varrida agora (`operation_scanned_now: false`), a varredura pode ter sido cortada, o varredor pode não ter repetido o ataque.

### `FindingGroup` (`groups[]`)

Visão **a mais**: nenhum achado some, nenhuma severidade muda. Chave do grupo (versão 1 da regra): `alert_ref`, `input_vector`, `parameter` e `proposed_severity`, iguais. Regra em `domain/finding_group.py`.

| Campo | Descrição |
| --- | --- |
| `group_id` | `G-` e 8 hexadecimais da chave; estável entre execuções, legível, não é identidade |
| `title`, `plugin_id`, `alert_ref`, `parameter`, `input_vector`, `cwe` | Do achado mais bem classificado do grupo (a chave garante regra, vetor e parâmetro iguais) |
| `proposed_severity` | Igual à de todos os membros |
| `findings_count`, `occurrences` | Achados no grupo e soma dos alertas do ZAP deles |
| `finding_ids` | Achados do grupo, na ordem de `findings` |
| `locations` | `[{finding_id, method, path_template, operation_id, occurrences}]`: onde aparece |
| `expected_note` | Nota fixa do código (texto nosso) quando o padrão costuma ser esperado, como o cookie de XSRF por duplo envio; `null` sem padrão. Não altera severidade nem tira o achado da lista |

Ordem: severidade, tamanho (maior primeiro), título, `group_id`.

## Fingerprint (versão 1)

```text
sha256( "hdast-finding-v1" , produto , MÉTODO , modelo-de-caminho , vetor , parâmetro ,
        pluginId , alertRef , CWE )     # separados por U+001F; vazio quando ausente
```

- **Método e modelo de caminho vêm da requisição aprendida**, resolvida pelo `sourceMessageId` do alerta, e nunca da URL atacada (que o ZAP muda a cada ataque). Sem `sourceMessageId` conhecido, vale a atribuição à varredura que gerou o alerta, depois o casamento único do caminho com um modelo do `probe`; sem nenhum dos dois o achado fica `unresolved`, com um modelo aproximado (segmentos com cara de id viram `{}`), e **continua sendo achado**.
- O modelo de caminho é normalizado: sem consulta, sem barras repetidas ou final, `{qualquer-nome}` vira `{}`. Renomear um parâmetro no OpenAPI não muda o achado.
- Vetor em minúsculas; método em maiúsculas.
- Se algum ingrediente contém o separador U+001F (dado do ZAP), o hash usa uma forma com o tamanho de cada parte, que começa com U+001E e nunca coincide com a forma simples; sem o separador o valor é o de sempre (ADR 0025).
- **Fora do fingerprint, de propósito:** carga (`attack`), host, ids concretos, `messageId`, id do alerta, severidade e confiança.
- Mudar um ingrediente ou a normalização invalida o histórico: suba `FINGERPRINT_VERSION` e escreva um ADR. `report --compare` recusa execuções de versões diferentes.
- O fingerprint v1 é o dos achados do ZAP e não leva papéis de conta. Os achados do teste de autorização (V1.1) têm fingerprint próprio, `hdast-authz-v1`, sem contas nem códigos HTTP (veja [authz.md](authz.md)).

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

## `rule-stats.json` e `metrics.json` (medição, ADR 0031)

**Só números e identificadores**: nenhuma URL, caminho, corpo, mensagem do alvo ou segredo. Servem para decidir, com dado, quais regras do ZAP não fazem sentido para um produto. A medição nunca derruba a varredura nem o relatório: se não puder ser feita, o motivo vai para o log (`rule_stats_unavailable`, `rule_stats_write_failed`, `metrics_not_written`) e o campo fica marcado como indisponível, nunca zero.

`rule-stats.json` (gravado pelo `scan`, uma coleta de `ascan/view/scanProgress` ao fim de cada varredura de operação):

```json
{"schema_version": 1, "run_id": "...", "zap_version": "2.17.0",
 "operations": [{"operation_id": "buscarConvenio", "scan_id": "0", "unavailable_reason": null,
   "rules": [{"plugin_id": 40018, "name": "SQL Injection", "state": "completed",
              "time_ms": 1273, "requests": 38, "alerts": 0, "skip_reason": null}]}]}
```

`state`: `completed`, `skipped` (com `skip_reason` `max_rule_time` ou `other`), `interrupted` (ainda rodava quando a varredura acabou ou foi parada), `pending`, `unknown`. Operação cuja coleta falhou tem `rules: []` e `unavailable_reason`.

`metrics.json` (gravado pelo `report`; o `run` o refaz no fim com o tempo de cada estágio, inclusive o `preflight`):

| Campo | Descrição |
| --- | --- |
| `schema_version` | `1`; só cresce com campos aditivos |
| `run_id`, `product`, `harness_version`, `zap_version`, `path_mode` | Identificação. `zap_version` é `null` sem ZAP |
| `started_at`, `finished_at`, `generated_at` | Início e fim da execução (`finished_at` `null` se não há fim conhecido) e instante da gravação (ISO 8601) |
| `stages_seconds` | `preflight`, `probe`, `scan`, `authz`, `report` em segundos; `null` quando a etapa não rodou, foi pulada ou não foi medida. O `preflight` só existe dentro do `hdast run` |
| `scan_status` | Estado final do `scan` (`completed` ou o motivo da parada), ou `null` |
| `operations[]` | `operation_id`, `outcome`, `duration_seconds` e `requests` (os de `scan.json`), `rules_available`, `rules_unavailable_reason`, `rules[]` (como em `rule-stats.json`) |
| `rules` | `operations_measured`, `operations_unavailable`, `totals[]`: uma linha por regra somada na execução (`plugin_id`, `name`, `time_ms`, `requests`, `alerts`, `operations`, `completed`, `skipped`, `interrupted`, `pending`, `unknown`), da mais lenta para a mais rápida |
| `traffic` | `available`, `allowed`, `denied`, `denied_by_reason`, `denied_by_detail` (os de `scan.traffic`) e `gaps`: `threshold_seconds` (10), `count`, `total_seconds`, `longest_seconds` dos silêncios entre dois pedidos do proxy dentro do `scan`; `gaps` é `null` sem a auditoria do proxy (pilha derrubada) |
| `disabled_rules[]` | Regras desligadas pela política: `plugin_id`, `name`, `reason`, `source` (`default` ou `profile`) |

Um `scan` anterior a esta versão não tem `rule-stats.json`: cada operação sai com `rules_available: false` e o motivo.

## Onde o achado aparece e baseline

Em `runs/<run_id>/`, junto de `audit.jsonl`, `manifest.json` e `probe.json`. A pasta `runs/` fica fora do git. O conjunto de achados esperados no VAmPI (teste de ponta a ponta) e o limite de severidade do modo seguro ficam para o teste contra o lab ([../testing.md](../testing.md)). Retenção das evidências em `runs/`: em aberto.

### Sinais passivos de erro interno

`internal_error_signals` é aditivo e pode ser `null` ou ausente em relatórios anteriores. Em relatórios novos, `messages_examined` conta mensagens distintas de evidência já redigidas; `truncated_messages` conta mensagens com algum campo cortado. `counts` contém as categorias fixas `http_5xx`, `stack_trace` e `sql_error`, cada uma contando mensagens distintas com o sinal, não ocorrências textuais. Uma mensagem pode aparecer em várias categorias. Nenhum trecho ou identificador é incluído. São indícios sujeitos a falsos positivos e omissões; zero não demonstra ausência de erro ou cobertura completa. Veja ADR 0045.

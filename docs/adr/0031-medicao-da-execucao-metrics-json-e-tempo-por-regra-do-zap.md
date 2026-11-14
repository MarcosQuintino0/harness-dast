# 0031. Medição da execução: `metrics.json` e o tempo por regra do ZAP

- **Status:** Aceito
- **Data:** 2026-11-14
- **Origem:** pergunta do dono do projeto: onde o tempo de uma varredura vai, e quais regras do ZAP não fazem sentido para um produto. Estende o [ADR 0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) (`scan`), o [ADR 0024](0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md) (`run.json`) e o [ADR 0026](0026-cerca-com-motivo-granular-e-modo-amplo-de-caminho.md) (tráfego do proxy)

## Contexto

Hoje a CLI mede o tempo de cada operação varrida (`scan.json`, `entries[].duration_seconds`) e de cada estágio do `run` (`run.json`), mas não sabe dizer qual **regra** do ZAP consumiu o tempo. Sem isso não dá para decidir com dado quais regras desligar para um produto (por exemplo, a XSS baseada em DOM, que precisa de um navegador que a imagem não tem, ou as de injeção por tempo, que dormem). Também não há como ver, depois, quando o tráfego ficou parado por muito tempo, que é o rastro de uma regra esperando uma resposta externa que o proxy de escopo nega.

Restrições: a medição não pode virar um caminho para vazar dado do alvo; não pode derrubar uma varredura; e a regra de cálculo não pode ser escrita duas vezes (duração e pedidos por operação já existem em `scan.json`, o total de tráfego já existe em `scan.traffic`).

## Decisão

Vamos gravar, em toda execução que chegue ao `report` ou ao `run`, o arquivo `runs/<run_id>/metrics.json`: **só números e identificadores** (ids de regra, nomes de regra do ZAP, operation_id, contagens, segundos). Nenhuma URL, caminho, corpo, mensagem do alvo ou segredo.

### Dois arquivos novos, um por etapa que o produz

1. **`rule-stats.json`**, gravado pelo `scan`: o dado bruto por regra, por operação varrida (`operations[]` com `operation_id`, `scan_id`, `rules[]` ou `unavailable_reason`) e a versão do ZAP. A coleta é feita ao fim de CADA varredura de operação, com `ascan/view/scanProgress` (antes de o `scan` seguir adiante). Se a coleta falhar, a varredura **não** falha: a operação fica com `unavailable_reason` (texto da CLI, no máximo 300 caracteres) e a falha vai para o log estruturado (`rule_stats_unavailable`). Falha ao gravar o arquivo também só é registrada (`rule_stats_write_failed`).
2. **`metrics.json`**, gravado pelo `report` e refeito pelo `run` no fim. Cada chamada refaz o arquivo inteiro a partir do que existe na pasta (`manifest.json`, `probe.json`, `scan.json`, `authz.json`, `rule-stats.json`) e da auditoria do proxy; chamar de novo é seguro. Quem grava nunca levanta erro do harness: se a medição não puder ser montada ou gravada, o comando segue e o motivo vai para o log (`metrics_not_written`).

`scan.json` **não muda** (contrato intacto). Um `scan` rodado antes desta versão não tem `rule-stats.json`: o `metrics.json` diz isso em cada operação, em vez de mostrar regras vazias ou tempo zero.

### Formato real de `ascan/view/scanProgress` (ZAP 2.17.0, medido em 2026-11-14)

Uma lista; o primeiro item é o host (texto) e o segundo um objeto `HostProcess`, lista de objetos `Plugin` com **sete textos**: nome, id, qualidade, estado, tempo em ms, pedidos, alertas. Estados vistos: `Complete`, `Skipped, failed to start or connect to the browser.`; pelo código do ZAP existem também `Pending`, `Running` e `Skipped, exceeded max rule time.`. A resposta vira modelo pydantic ao entrar (`adapters/zap/scan_progress.py`); qualquer desvio de forma é `ExternalToolError` (métrica indisponível, varredura segue). O texto do motivo de pulo **nunca** é guardado: vira um código fechado (`max_rule_time` ou `other`). Estados: `completed`, `skipped`, `interrupted` (ainda rodava quando a varredura terminou ou foi parada), `pending`, `unknown`.

### Esquema do `metrics.json` (`schema_version: 1`; só cresce com campos aditivos)

- Identificação: `run_id`, `product`, `harness_version`, `zap_version` (de `rule-stats.json`, senão do manifesto, senão `null`), `path_mode`, `started_at`, `finished_at` (`null` se não há fim conhecido), `generated_at`. O relógio entra por porta.
- `stages_seconds`: `preflight`, `probe`, `scan`, `authz`, `report`, em segundos. Etapa que não rodou (ou foi pulada) é `null`, nunca zero. Dentro do `run`, vale o `run.json` (inclui o preparo de cada etapa e é a única fonte do `preflight`); fora dele, vêm de `probe.json`, `scan.json`, `authz.json` e da medição do próprio `report`. `scan --dry-run` e `probe --dry-run` não contam como etapa medida.
- `scan_status`: estado final do `scan` (`completed` ou o motivo da parada).
- `operations[]`: `operation_id`, `outcome`, `duration_seconds` e `requests` (copiados de `scan.json`), `rules_available`, `rules_unavailable_reason` e `rules[]` (`plugin_id`, `name`, `state`, `time_ms`, `requests`, `alerts`, `skip_reason`).
- `rules`: `operations_measured`, `operations_unavailable` e `totals[]`, uma linha por regra somada na execução (`time_ms`, `requests`, `alerts`, `operations`, e quantas vezes terminou, foi pulada, interrompida, pendente ou desconhecida), da mais lenta para a mais rápida.
- `traffic`: `available`, `allowed`, `denied`, `denied_by_reason`, `denied_by_detail` (copiados de `scan.traffic`) e `gaps` (`threshold_seconds` = 10, `count`, `total_seconds`, `longest_seconds`). Lacuna é um silêncio maior que o limite ENTRE dois pedidos que passaram pelo proxy (liberados ou negados) dentro da janela do `scan`; o tempo antes do primeiro e depois do último não conta. Sem a auditoria do proxy, ou com uma auditoria que não tem nenhuma linha dentro do `scan` (outra pilha), `gaps` é `null`, não zero.
- `disabled_rules[]`: `plugin_id`, `name`, `reason` e `source` (`default`: política do harness, com o motivo escrito em `DEFAULT_DISABLED_RULES`; `profile`: `scan.disable_rules` do perfil, sem nome).

### Onde cada parte mora

- `domain`: `rule_stats.py` (modelos e soma por regra), `run_metrics.py` (modelo e montagem, sem I/O), `traffic.py` (`find_gaps`, cálculo das lacunas).
- `application`: `metrics.py` (`MetricsRecorder`: lê, monta, grava, nunca derruba); `scan_runner.py` coleta por operação; `scan.py` grava `rule-stats.json`; `report.py` e `run.py` chamam o gravador.
- `adapters`: `zap/scan_progress.py` e `ZapScanClient.scan_rules`; `reporting/run_files.py` lê e grava os arquivos.
- `cli`: só monta (`build_metrics`); `hdast report` cita `metrics.json` na saída humana. Não há comando novo.

### Porta

Uma porta nova, pequena: `RunMetricsRecorder` (declarada em `application/scan_ports.py`, consumida por `report` e `run`), para que os dois chamem o gravador sem importar a classe concreta e para os testes usarem um falso. `ScanControl` ganha `scan_rules` e `RunArtifacts` ganha `write_rule_stats`, `read_rule_stats` e `write_metrics` (mesmos arquivos de execução, mesma fronteira). Nenhuma dependência nova.

## Alternativas consideradas

- **Pôr as regras dentro de `scan.json`.** Muda um contrato que o agente lê inteiro (dezenas de regras por operação engordam o arquivo) e mistura medição com resultado. Descartada.
- **Só `metrics.json`, sem `rule-stats.json`.** O `scan` e o `report` são processos diferentes; o dado por regra só existe no ZAP durante o `scan`, então alguém precisa guardá-lo. Um arquivo bruto por etapa mantém cada etapa dona do que produz.
- **Cada etapa atualiza o `metrics.json` ao terminar.** Obrigaria `preflight`, `probe` e `authz` a conhecer a medição. Derivar tudo dos arquivos que já existem (e do `run.json` no `run`) deixa as etapas intactas.
- **Calcular o tempo por regra com os pedidos da auditoria do proxy.** O proxy não sabe qual regra enviou o pedido. O ZAP sabe.
- **Guardar o texto do estado das regras.** O texto do motivo é do ZAP e pode mudar de versão; um código fechado é estável e não tem como carregar dado do alvo.
- **Comando para ver as métricas.** Não pedido agora; o arquivo é lido por quem analisa.

## Consequências

- Dá para listar, por produto, as regras mais lentas, as que sempre são puladas (a XSS baseada em DOM, nesta imagem, por falta de navegador), as que não levantam alerta e as que deixam o tráfego parado. A decisão de desligar uma regra continua sendo humana e vai em `scan.disable_rules` do perfil.
- `scanProgress` foi conferido só contra o ZAP 2.17.0. Outra versão com outra forma deixa a métrica indisponível (registrada), nunca a varredura parada.
- A coleta custa uma chamada de API por operação varrida (e uma resposta de poucos KB).
- O estado `interrupted` de uma regra mede "ainda rodava quando a CLI olhou": numa varredura que terminou normalmente não aparece.
- O `metrics.json` de um `report` rodado em outra máquina, depois de `stack down`, não tem `gaps` (a trilha do proxy some com a pilha). O restante vem dos arquivos da execução.
- Mudança de contrato aditiva: dois arquivos novos na pasta da execução (listados em `run.json` quando existem) e um campo `metrics_file` no resultado do caso de uso `report` (não vai ao envelope JSON). O teste `test_cli_paths_never_read_the_path_mode` passa a conhecer `application/metrics.py` e `domain/run_metrics.py`, que só COPIAM o modo para o arquivo de medição.

# Quanto do ZAP usamos

Tabela de consulta para revisar, de tempos em tempos, se a ferramenta aproveita bem o ZAP. Atualize a tabela a cada versão que mudar o uso do ZAP. Na atualização, diga a data, a versão do ZAP e de onde veio cada resposta (código ou execução).

**Última conferência:** 2026-11-17, fim da V1.12 (passo F9). ZAP 2.17.0, imagem `hdast/zap:2.17.0-alpha54-beta64` (ADR 0103), derivada da `zaproxy/zap-stable` fixada por digest em `compose.yaml`, com `ascanrulesBeta` 64 e `ascanrulesAlpha` 54 fixados por SHA-256 em `docker/zap/Dockerfile`.

**Fontes da conferência:**
- código: `src/harness_dast/adapters/zap/`, `src/harness_dast/domain/scan_policy.py`, `src/harness_dast/domain/experimental_rules.py`, `docker/zap/Dockerfile` e `compose.yaml`;
- execução no laboratório (Clínica Piloto, VAmPI e crAPI): `rule-stats.json` das provas da V1.12, com os `run_id` no [relatório da V1.12](../arquivo/reviews/relatorio-v1.12.md); e, para a base anterior, a rodada cega da V1.9.3 (`2026-11-17T00-37-09Z-clinica-piloto-e0d5`).

**Correção registrada na F9.** O ADR 0099 (F2) afirma que a imagem não tem regra de SSRF. Isso valia para a `zap-stable` 2.17.0 pura. Com a imagem derivada do ADR 0103 a regra de SSRF 40046 existe (complemento beta) e liga junto com `scan.oast` e `extra_checks.experimental_rules`. Os ADRs não foram editados; vale esta tabela. A injeção de comando cega com OAST continua sem regra.

| Recurso do ZAP | Usamos? | Detalhe |
| --- | --- | --- |
| Varredura ativa com política própria (força, limiar, regras desligadas) | Sim | Política `hdast-scan`, recriada a cada varredura; cerca de 45 regras por operação na Clínica |
| Injeção em parâmetros de consulta, corpo e JSON | Sim | Máscara `TargetParamsInjectable` 35, o padrão medido do ZAP |
| Injeção em segmentos de caminho | Sim, por padrão | Bit 16 (máscara 51). `scan.url_path_injection` vem ligado por padrão e pode ser desligado no perfil |
| Regras passivas sobre o tráfego | Sim | Alertas lidos de `alert/view/alerts` |
| Injeção em cabeçalhos e cookies | Só com `scan.inject_headers` (carta) | Bits 4 e 8 (máscara 63) mais `setOptionScanHeadersAllRequests=true` (ADR 0097); desligado, máscara 51 e opção `false`. H11 da Clínica achada no laboratório |
| Regras "alpha" e "beta" (experimentais) | Só com `extra_checks.experimental_rules` (carta) | A imagem `hdast/zap` (ADR 0103) acrescenta `ascanrulesBeta` 64 e `ascanrulesAlpha` 54 (SHA-256 fixado no Dockerfile) à `zap-stable` 2.17.0: 26 regras novas, todas desligadas na política. A chave liga NoSQL MongoDB 40033 e 90039 e, com `scan.oast`, o SSRF 40046 (beta). Achados saem com `experimental: true`. A imagem oficial não traz nenhum dos dois complementos; **não existe regra de SQLite por tempo** na 2.17.0. Execução no laboratório: no crAPI as regras NoSQL rodaram e **não acharam o C12**; na Clínica segura deram 5 alarmes falsos de gravidade alta em 1383 pedidos. Origem da resposta: execução (`ascan/view/scanners` das duas imagens, 53 contra 79 regras; `rule-stats.json`) e código (`domain/experimental_rules.py`, `adapters/zap/scan_client.py`) |
| OAST (detecção fora de banda, com servidor de retorno) | Só com `scan.oast` (carta) e ponte disponível | `oast/action/setCallbackOptions` (Callback em `oast-gateway:8090`, ADR 0095), `setActiveScanService=Callback` e `ascan/action/enableScanners` das regras que usam retorno: Log4Shell 40043, XXE 90023 e SSTI cega 90036 (ADR 0099). O SSRF 40046 existe só na imagem derivada (ADR 0103) e liga com OAST mais `extra_checks.experimental_rules`; na `zap-stable` pura não havia (correção da F9 ao ADR 0099). Injeção de comando cega com OAST: sem regra. Além do ZAP, a CLI faz o SSRF guiado pelo contrato (ADR 0100). Na V1.12.1, `stack up crapi` monta a ponte isolada e conecta o workshop com perfil aprovado e OAST autorizado; `stack down` remove ambos. Produto comum não ganha ponte. Sem ponte disponível, OAST do ZAP e SSRF guiado ficam **não verificáveis**, com motivo em `scan.json.oast_verification`, relatório e painel (ADR 0105); zero retornos não indica verificação limpa. Origem: código (`domain/scan_policy.py`, `adapters/zap/scan_client.py`) e execução (SSRF do crAPI achado pela CLI; sem a chave, contador do Callback e histórico de OAST em zero). Log4Shell, XXE e SSTI cega não foram provadas contra falha real |
| Regras ativas por script próprio | Não | A regra 50000 ("Script Active Scan Rules") roda sem nenhum script carregado |
| XSS baseado em DOM (40026) | Não | Exige navegador; exclusão pré-existente, pouco relevante para API |
| Spider e AJAX spider | Não | Desnecessários: as rotas vêm do OpenAPI e o `probe` alimenta o histórico |
| Complemento de JWT do ZAP | Não | O JWT é feito pela CLI no `authz` (ADR 0098): `alg none`, assinatura retirada, claims alteradas e chave HMAC fraca offline com prova re-assinada. `kid`, `jku` e confusão de algoritmo ficam de fora. Origem: código e execução (crAPI aceitou `alg_none` e claims alteradas) |
| Fuzzer do ZAP | Não | Os testes `negative` e `authz` cobrem casos guiados pelo contrato; o limite de consumo (página enorme e tentativas repetidas) é a F5 da CLI, com `extra_checks.allow_rate_tests` (ADR 0101), e o inventário de versões e documentação é a F8, com `extra_checks.inventory` (ADR 0102) |

## Como conferir de novo

1. Liste as chamadas à API do ZAP: `rg -o '"[a-zA-Z]+/(action|view)/[a-zA-Z]+"' src/harness_dast/adapters/zap`.
2. Confira a máscara e a política em `src/harness_dast/domain/scan_policy.py`.
3. Numa execução recente, abra `runs/<run_id>/rule-stats.json` e veja quais regras rodaram, quantos pedidos cada uma fez e quais foram puladas, com o motivo.
4. Confira os complementos instalados na imagem do ZAP fixada em `compose.yaml`.

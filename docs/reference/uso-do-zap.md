# Quanto do ZAP usamos

Tabela de consulta para revisar, de tempos em tempos, se a ferramenta aproveita bem o ZAP. Atualize a tabela a cada versão que mudar o uso do ZAP. Na atualização, diga a data, a versão do ZAP e de onde veio cada resposta (código ou execução).

**Última conferência:** 2026-11-17, ZAP 2.17.0 (`zaproxy/zap-stable`, fixado por digest em `compose.yaml`).

**Fontes da conferência:**
- código: `src/harness_dast/adapters/zap/`, `src/harness_dast/domain/scan_policy.py` e `compose.yaml`;
- execução: `rule-stats.json` da rodada cega da V1.9.3 na Clínica Piloto (`2026-11-17T00-37-09Z-clinica-piloto-e0d5`).

| Recurso do ZAP | Usamos? | Detalhe |
| --- | --- | --- |
| Varredura ativa com política própria (força, limiar, regras desligadas) | Sim | Política `hdast-scan`, recriada a cada varredura; cerca de 45 regras por operação na Clínica |
| Injeção em parâmetros de consulta, corpo e JSON | Sim | Máscara `TargetParamsInjectable` 35, o padrão medido do ZAP |
| Injeção em segmentos de caminho | Sim, por padrão | Bit 16 (máscara 51). `scan.url_path_injection` vem ligado por padrão e pode ser desligado no perfil |
| Regras passivas sobre o tráfego | Sim | Alertas lidos de `alert/view/alerts` |
| Injeção em cabeçalhos e cookies | Só com `scan.inject_headers` (carta) | Bits 4 e 8 (máscara 63) mais `setOptionScanHeadersAllRequests=true` (ADR 0097); desligado, máscara 51 e opção `false`. H11 da Clínica achada no laboratório |
| Regras "alpha" (experimentais) | Não | Só as regras estáveis e beta da imagem oficial |
| OAST (detecção fora de banda, com servidor de retorno) | Só com `scan.oast` (carta) | `oast/action/setCallbackOptions` (Callback em `oast-gateway:8090`, ADR 0095), `setActiveScanService=Callback` e `ascan/action/enableScanners` das regras da imagem que usam retorno: Log4Shell 40043, XXE 90023 e SSTI cega 90036 (ADR 0099). **A imagem 2.17.0 não tem regra de SSRF nem de injeção de comando cega** (ids lidos de `ascan/view/scanners` e dos pacotes `ascanrules` 84); o SSRF é feito pela CLI, guiado pelo contrato (ADR 0100). Origem da resposta: código (`domain/scan_policy.py`, `adapters/zap/scan_client.py`) e execução no laboratório (SSRF do crAPI achado; sem a chave, contador do Callback e histórico de OAST em zero). Log4Shell, XXE e SSTI cega não foram provadas contra falha real |
| Regras ativas por script próprio | Não | A regra 50000 ("Script Active Scan Rules") roda sem nenhum script carregado |
| XSS baseado em DOM (40026) | Não | Exige navegador; exclusão pré-existente, pouco relevante para API |
| Spider e AJAX spider | Não | Desnecessários: as rotas vêm do OpenAPI e o `probe` alimenta o histórico |
| Complemento de JWT | Não | O teste de token adulterado do `authz` cobre só parte |
| Fuzzer do ZAP | Não | Os testes `negative` e `authz` cobrem casos guiados pelo contrato; o limite de consumo (página enorme e tentativas repetidas) é a F5 da CLI, com `extra_checks.allow_rate_tests` (ADR 0101), e o inventário de versões e documentação é a F8, com `extra_checks.inventory` (ADR 0102) |

## Como conferir de novo

1. Liste as chamadas à API do ZAP: `rg -o '"[a-zA-Z]+/(action|view)/[a-zA-Z]+"' src/harness_dast/adapters/zap`.
2. Confira a máscara e a política em `src/harness_dast/domain/scan_policy.py`.
3. Numa execução recente, abra `runs/<run_id>/rule-stats.json` e veja quais regras rodaram, quantos pedidos cada uma fez e quais foram puladas, com o motivo.
4. Confira os complementos instalados na imagem do ZAP fixada em `compose.yaml`.

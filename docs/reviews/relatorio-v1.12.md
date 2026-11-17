# Relatório da V1.12: mais achados

Data: 2026-11-17. Branch `feat/v1-12-mais-achados`, versão 1.12.0.
**Estado: implementada e provada só no laboratório (Clínica Piloto, VAmPI e crAPI). Rodada cega e validação independente: pendentes. Sem produto real, sem PR e sem merge.**

Quem fez: o Codex foi recusado pelo filtro do provedor no primeiro minuto (diário do coordenador, 10:53 e 10:54, sem commit). O trabalho foi feito por agentes Sonnet 5.5, passo a passo, coordenados pelo Claude Code.

## 1. O que entrou, por passo

| Passo | O que entrou | ADR | Commits |
| --- | --- | --- | --- |
| F1 | Seção `attack` da carta: `pacing`, `inject_headers`, `oast`, `allow_rate_tests`, `experimental_rules`, `inventory`, todas desligadas se ausentes; só a carta liga; impressão digital só muda quando uma chave é ligada | 0096 | `b293e55`, `7613085` |
| F4 | JWT no `authz`: chave HMAC fraca quebrada offline com lista fixa e prova re-assinada, até 10 operações por execução | 0098 | `d14986d`, `493ab4a`, `0038f2b`, `464b3da`, `d54ee96` |
| F6 | Injeção em cabeçalhos e cookies (máscara 63 e `ScanHeadersAllRequests`) com `scan.inject_headers` | 0097 | `706102c`, `2f9b479`, `668783c`, `c36116f` |
| F2 | OAST na varredura (`scan.oast`), com Log4Shell, XXE e SSTI cega | 0099 | `e9a7590`, `0f6d85d`, `a3ee18a` |
| F3 | SSRF guiado pelo contrato, teto de 10 pedidos, achado pela prova do retorno | 0100 | `e9a7590`, `219adeb`, `7f20f3b`, `d54ee96` |
| F7 | Imagem derivada `hdast/zap:2.17.0-alpha54-beta64`; regras NoSQL e SSRF por `extra_checks.experimental_rules`; achados marcados `[experimental]` | 0103 | `e94e19d`, `b01ad79`, `5abd8b4`, `2de9a72` |
| F5 | Limite de consumo (página enorme e tentativas repetidas), teto de 66 pedidos | 0101 | `47341ca`, `feb5a22`, `c68cf91`, `a9e6ec7` |
| F8 | Inventário de versões irmãs e documentação exposta, até 40 `GET` pela cerca | 0102 | `47341ca`, `feb5a22`, `a9e6ec7` |
| Junções | F4 e F5+F8 trazidas para a trilha F | n/a | `2ef9189`, `9e75b29` |
| F9 | Versão, CHANGELOG, tabela do ZAP, skills, roadmap, caso `crapi-foco` v2 e este relatório | n/a | commits deste passo |

A trilha L (ADRs 0092 a 0095: H11 na Clínica, vigia, crAPI na pilha e ponte de retorno) veio antes e está no CHANGELOG.

## 2. Provas no laboratório

| Prova | `run_id` | Resultado |
| --- | --- | --- |
| F6, H11 com a chave | `2026-11-17T14-40-40Z-clinica-piloto-41fe` | achada; 519 pedidos sem a chave e 1089 com ela na operação (cerca de 2,1 vezes) |
| F6, sem a chave | `…14-43-19Z-clinica-piloto-6add` | zero |
| F6, Clínica segura com a chave | `…14-45-39Z-clinica-piloto-1aa3` | zero |
| F4, crAPI (C15) | `2026-11-17T14-55-25Z-crapi-a379` | aceitou `alg_none` e claims alteradas; recusou assinatura retirada |
| F4, Clínica segura | `…14-57-46Z-clinica-piloto-cb37` | zero |
| F2 e F3, crAPI (C11) com `oast` | `2026-11-17T15-32-14Z-crapi-7b43` e `…15-45-19Z-crapi-11fa` | 1 pedido de SSRF, 1 retorno, achado alto no campo `mechanic_api` |
| F2 e F3, sem a chave | `…15-50-44Z-crapi-0efe` | 0 interações |
| F7, crAPI (C12) | `2026-11-17T16-46-08Z-crapi-d197` | NÃO achado (força baixa) |
| F7, Clínica segura | `…16-52-36Z-clinica-piloto-b3de` | 5 alarmes falsos altos da regra 40033, marcados experimentais (1383 pedidos) |
| F7, chave desligada | `…16-50-06Z-crapi-416b` | 0 pedidos das regras novas |
| F5, crAPI ligado (C3) | `2026-11-17T17-32-00Z-crapi-338a` | `check_otp_v2` achado (20 tentativas, sempre HTTP 500); `check_otp_v3` também achado |
| F5 e F8, desligado | `…17-36-50Z-crapi-4689` | zero pedidos |
| F5 e F8, Clínica segura | `…17-39-33Z-clinica-piloto-b907` | 1 achado baixo (`/v3/api-docs` exposto) |

Os gates de cada passo (`gates-f1`, `gates-f4`, `gates-f6b`, `gates-f2f3b`, `gates-f7`, `gates-f5f8` e os das junções) passaram com `all_passed`.

## 3. O que NÃO foi provado

- Injeção em cookie: sem alvo plantado; só o cabeçalho (H11) foi provado.
- Log4Shell, XXE e SSTI cega: sem alvo plantado; as regras ligam, mas nenhuma falha real foi achada.
- Chave HMAC fraca de JWT: exercida só em teste de unidade; o crAPI já aceita `alg_none`, então o envio não foi necessário.
- C12 (NoSQL do crAPI): as regras rodaram e não acharam em força baixa. O gabarito mantém `detectable: false`.
- Regra 40033 na Clínica segura: 5 alarmes falsos de gravidade alta. Por isso os achados experimentais saem marcados e passam pela verificação.
- `check_otp_v3`: achado provável falso positivo (sem OTP emitido); o achado se baseia em `5xx` constante. A v3 está fora do escopo do caso `crapi-foco`.
- Página enorme: só em unidade; no crAPI a lista veio vazia e o resultado foi inconclusivo.
- Asserção da Clínica do teste de integração das regras experimentais: não executada.
- `kid`, `jku` e confusão de algoritmo no JWT: fora.
- O compose passa a construir a imagem do ZAP; a primeira construção depende de rede.
- O diário da cerca trata `5xx` como rejeição conhecida para a intenção `rejection-attempt:`; a validação independente deve conferir que vale só para ela.
- Produto real, rodada cega e validação independente (F10): pendentes.

## 4. Correção à tabela do ZAP

O ADR 0099 diz que a imagem não tem regra de SSRF (40046). Isso valia para a `zap-stable` pura. Com a imagem derivada do ADR 0103 a regra existe e liga junto com `scan.oast` e `extra_checks.experimental_rules`. Os ADRs não foram editados; a correção está na tabela de [uso do ZAP](../reference/uso-do-zap.md) e aqui.

## 5. Casos de avaliação

- **`crapi-foco`, versão 2:** a carta liga `attack.pacing: proxy` e as cinco capacidades, cada uma com `quote`, e autoriza só o POST da verificação de OTP da v2. Gabarito: C3, C11 e C15 `detectable: true` (pelas provas acima); C1, C6, C10 e C12 `false`. Controles C1 e C10 mantidos. A cópia cega e o teste de vazamento passam; nenhum agente foi rodado.
- **`clinica-piloto`:** não mudou. A H11 continua `detectable: false`, porque a carta da Clínica não autoriza cabeçalhos.
- Rodada cega do `crapi-foco` (Sonnet 5.5 medium) e, no fim, a de Haiku 5.5 high: pendentes.

## 6. Pendências

Rodada cega, validação independente (F10), PR e merge. Itens da seção 3.

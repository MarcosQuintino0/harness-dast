# 0097. Injeção em cabeçalhos e cookies

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** F6 da V1.12 ([plano](../arquivo/plans/2026-11-17-v1-12-mais-achados.md)); [ADR 0096](0096-bloco-attack-da-carta-liga-capacidades-v1-12.md); [ADR 0092](0092-operacao-de-cabecalho-na-clinica-piloto.md)

## Contexto

A política do ZAP injeta só em consulta, corpo e JSON (máscara `TargetParamsInjectable` 35) e, por padrão do perfil, em segmentos de caminho (bit 16, máscara 51). Falhas em parâmetros `in: header` (H11 da Clínica Piloto, `X-CRM`) e em cookies não são alcançadas. A carta liga a capacidade por `attack.inject_headers`, que vira `scan.inject_headers` ([ADR 0096](0096-bloco-attack-da-carta-liga-capacidades-v1-12.md)); até aqui nada a consumia.

## Decisão

Vamos consumir `scan.inject_headers` na política de varredura (`domain/scan_policy.py`):

- **Máscara.** Com a chave ligada, somam-se o bit 4 (cookies) e o bit 8 (cabeçalhos): 35 + 16 + 4 + 8 = 63 (ou 47 sem injeção em caminho). Desligada, a máscara é idêntica à de antes (35 ou 51). `ScanPolicy.header_injection` carrega a decisão; o adaptador só traduz.
- **Opção do ZAP.** O adaptador também fixa `ascan/setOptionScanHeadersAllRequests` (`true` com a chave ligada, `false` desligada, explícito nos dois sentidos). Medido no laboratório: só com a máscara 63 o ZAP enviou mais pedidos, mas **não achou** a H11; com esta opção a H11 foi achada. Sem ela o ZAP só varre cabeçalhos de alguns pedidos.
- **Pedido que o ZAP varre.** Nada muda na montagem: o `probe` já envia os parâmetros `in: header` do contrato com valores das regras de dados (`data-rules.yml`) ou do exemplo/esquema, e o ZAP aprende o pedido pelo histórico. Ficam de fora, como antes, `Authorization`, `Content-Type`, `Accept` e `Cookie` (que o harness injeta) e os cabeçalhos de roteamento (`Host` etc., nunca enviados). O ZAP injeta nos cabeçalhos do pedido aprendido; o `Authorization` e o cookie de sessão são repostos pelo mecanismo de autenticação do harness em cada pedido, então a injeção neles é recusada pelo servidor ou substituída, e a sessão não quebra. A cerca (proxy de escopo) continua decidindo cada pedido; nenhum DELETE passa.
- **Contrato.** O envelope JSON, o schema do perfil e os códigos de saída não mudam; `scan.json` já registra `injectable_mask` na política aplicada (63 mostra a chave ligada).

## Alternativas consideradas

- **Só a máscara.** Medido: não achou a H11 (519 -> 632 pedidos, zero achado, run `2026-11-17T14-28-58Z-clinica-piloto-ffc4`).
- **Lista de cabeçalhos tirada do contrato para o ZAP.** Descartada: o `probe` já os envia; o ZAP varre os do pedido aprendido.
- **Ligar por padrão.** Descartado: amplia o tráfego (cerca de o dobro de pedidos na operação medida) e só a carta liga.

## Consequências

- Custo na operação da H11 (laboratório, `rule-stats.json`): `buscarMedicoPorCabecalho` fez 519 pedidos sem a chave e 1089 com ela (cerca de 2,1 vezes); no proxy, 182 contra 758 linhas no caminho. A varredura da operação passou de 19 s para 37 s.
- A H11 passa a ser detectável com a chave ligada pela carta; o gabarito do caso `clinica-piloto` segue `detectable: false` até um ADR ou nota de versão do caso mudar o valor (ADR 0092).
- Provado só na Clínica Piloto (modo vulnerável com a chave, sem a chave, e modo seguro com a chave); cookies não têm falha plantada, então a injeção em cookie não foi provada.

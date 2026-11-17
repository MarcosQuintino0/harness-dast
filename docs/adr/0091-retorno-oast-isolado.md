# 0091. Retorno OAST isolado no laboratório

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** V1.12, trilha L2

## Contexto

O workshop do crAPI precisa alcançar um retorno HTTP, sem dar ao ZAP acesso direto à rede do alvo nem ao alvo uma rota de internet. A integração com a varredura pertence à trilha F.

## Decisão

Vamos usar o serviço Callback do complemento OAST do ZAP, que recebe HTTP no próprio processo, em porta separada da API. A ponte socat existente como imagem fixada escuta na rede interna de retorno e encaminha exclusivamente para `zap:8090` na rede interna do ZAP. O workshop entra na rede de retorno pelo overlay; o ZAP não entra nela nem na rede do crAPI. A ponte registra conexões em seu log; o ZAP registra os acessos à URL de teste. Não há porta publicada. A configuração do Callback e a prova são manuais e não ativam regras de varredura.

## Alternativas consideradas

- BOAST e Interactsh: exigem instância e protocolo próprios; DNS e operação adicionais não são necessários para este teste HTTP.
- Servidor HTTP genérico: não implementa o protocolo de registro e consulta do BOAST ou Interactsh.
- Colocar o ZAP na rede do alvo: permitiria contornar a cerca e foi descartado.

## Consequências e aceites

A ponte possui duas interfaces e constitui uma fronteira adicional; o destino fixo e os logs não substituem a prova de isolamento nem protegem contra comprometimento da própria ponte. Falta provar a topologia efetiva, retorno e tentativa externa negativa no Docker do laboratório, sob a trava. Também falta conferir que o complemento está presente na imagem fixada. Callback cobre HTTP, não prova interações DNS. O índice do ADR pertence à coordenação.

Fontes primárias: [opções Callback](https://www.zaproxy.org/docs/desktop/addons/oast-support/services/callbacks/options/), [API OAST](https://www.zaproxy.org/docs/desktop/addons/oast-support/api/) e [serviço Callback](https://www.zaproxy.org/docs/desktop/addons/oast-support/services/callbacks/).

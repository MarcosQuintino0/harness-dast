# 0007. ZAP alimentado por requisições válidas

- **Status:** Aceito. O mecanismo exato depende do spike do M0 e ainda não foi confirmado.
- **Data:** 2026-11-13
- **Origem:** AD-07, P-10

## Contexto

O ganho central da V1 é fazer o ZAP chegar à lógica da API, e não parar na validação (400), na autenticação (401) ou na duplicidade (409). O import cru do OpenAPI no ZAP gera valores genéricos.

## Decisão

Vamos alimentar o ZAP com requisições válidas. O comando `probe` envia uma requisição válida por operação através do proxy do ZAP. O ZAP aprende essas requisições e a varredura ativa parte delas. O mesmo comando mede a alcançabilidade (percentual de operações que respondem 2xx) e devolve os erros 400 e 409 para o agente ajustar as regras de dados.

**O que está decidido e o que não está.** A direção (probe por proxy, com medição de alcançabilidade) está aceita. O mecanismo concreto não foi validado: o comportamento do ZAP precisa ser confirmado em um teste técnico curto (spike do M0), que também define como o token chega ao ZAP e é renovado e como o plano de varredura é executado (P-10). O resultado será registrado em ADR novo, que complementa ou substitui este.

## Alternativas consideradas

- **Import do OpenAPI no ZAP com substituição de valores pelo add-on de formulários.** Menos controle sobre unicidade e encadeamento.
- **Reescrever o Swagger com exemplos antes de importar.** Não resolve dependência entre chamadas.

## Consequências

- Todo o tráfego passa por um único ponto, o que simplifica escopo e auditoria.
- O ZAP vira o único ponto de tráfego; motores que abram conexão própria precisarão passar pelo proxy de saída ([ADR 0008](0008-escopo-em-tres-camadas.md)).
- Se o spike mostrar que o mecanismo não funciona, este ADR é substituído por um ADR novo.
- O comando `probe` chega no M3 e não existe hoje.

## Nota de 2026-11-14 (estado; o texto da decisão não mudou)

O mecanismo que este ADR deixava para o spike do M0 foi confirmado. O spike ([relato](../spikes/2026-11-13-m0-zap.md), 2026-11-13) mostrou que requisições enviadas pelo proxy do ZAP aparecem no histórico e servem de ponto de partida da varredura ativa, e respondeu a entrega do token e a execução do plano (P-10). As decisões que dele saíram estão nos ADRs [0017](0017-proxy-de-escopo-com-scopeguard.md), [0018](0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md), [0019](0019-pilha-gerenciada-politica-por-execucao-e-login-pelo-proxy.md), [0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) e [0023](0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md), e o `probe` existe desde o M3, verificado contra o ZAP 2.17 real ([relatório](../reviews/2026-11-13-e2e-lab.md)). Este ADR não foi substituído. Não foram medidos no spike: Oracle de testes, skill chamando um comando e a taxa de bloqueio do provedor (P-08); o Oracle foi verificado depois, no M5.

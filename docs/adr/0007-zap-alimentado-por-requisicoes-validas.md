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

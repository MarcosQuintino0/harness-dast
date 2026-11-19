# Proposta para fechar a lacuna de prova da rodada 3

Data: 2026-11-16. **Proposta não executada**, posterior às medições. Não muda o
protocolo congelado, não reclassifica suas diferenças e não aprova a promoção.
O [novo parecer](../reviews/2026-11-16-v1-8-validacao-rodada3.md) exige evidência
comparável antes do aceite global. O PR permanece em rascunho.

## Problema concreto

- SSTI 90035 na Clínica: 47 pedidos históricos, 61 nas novas A e B.
- Parameter Tampering 40008 no VAmPI: 4 pedidos históricos e na nova A, 28 na nova B.

Todas essas execuções terminaram sem alertas nessas regras. Os resumos não guardam
corpos/vetores suficientes para explicar as diferenças; não é possível recuperá-los
retroativamente por inferência. Mais pedidos não comprovam perda nem equivalência.

## Investigação recomendada

1. Revisar a implementação da versão instalada dessas duas regras no ZAP e
   identificar condições que variam o número de pedidos, sem concluir a causa
   apenas pela possibilidade teórica.
2. Definir antecipadamente quais metadados de vetor, ponto de entrada, decisão da
   regra e resposta bastam para distinguir essas condições. A lista exportável
   deve excluir credenciais, cookies, tokens, corpos e valores secretos; só dados
   sintéticos do laboratório podem ser usados. Não reutilizar sessões brutas como
   evidência pública. A captura deve ser suporte de teste, sem ampliar autoridade
   do produto ou relaxar a cerca.
3. Congelar operações, regras, força, limites, dados e ordem A/B antes de uma prova
   dirigida das duas regras nas respectivas operações. Registrar todas as
   repetições e falhas; não substituir T4 anteriores nem selecionar a melhor
   contagem. Não realizar outra T4 sem justificar por que a prova dirigida não basta.
4. Comparar vetores e decisões observados, além das contagens e achados. Se a causa
   for demonstrada, explicar exatamente a relação com a evidência original e o que
   continua sem prova; se não for, manter a lacuna. Corrigir produto apenas se um
   defeito for demonstrado e repetir as camadas afetadas.
5. Submeter a nova evidência a validador Terra medium novo e aos gates aplicáveis.
   `init` continua `legacy` até aceite explícito da condição de promoção.

## Decisão do coordenador geral

A recomendação é executar a investigação dirigida. A alternativa é uma decisão
explícita de escopo para avaliar a correção do guard/base V1.8 separadamente da
equivalência global, preservando a não promoção e todas as lacunas documentadas.
Essa alternativa não transforma o parecer atual em `continuar` nem retira o PR do
rascunho automaticamente.

# ADR 0045 — Sinais passivos de erro interno

- Estado: Proposto
- Data: 2026-11-14

## Contexto

Respostas já coletadas e redigidas podem conter sinais de falha interna, mas não representam todas as respostas do alvo e podem estar cortadas. É necessário apresentá-los sem ampliar a coleta ou reproduzir conteúdo sensível.

## Decisão

O relatório classifica passivamente as mensagens de evidência já fornecidas ao montador: resposta HTTP 5xx, possível rastreamento de exceção e possível erro de banco. Cada categoria conta mensagens distintas pelo identificador da mensagem; uma mensagem pode integrar várias categorias. Contam-se também mensagens examinadas e mensagens com algum campo cortado. O resultado contém apenas contagens e categorias fixas, sem trechos nem identificadores. Não altera achados, severidade ou limiares. A análise é determinística e não executa rede nem coleta adicional. O campo aditivo é opcional ao ler relatórios anteriores.

## Consequências

Os padrões são heurísticos, podem produzir falsos positivos e perder sinais, inclusive por redação e corte. Zero significa apenas ausência de sinal nas evidências disponíveis, não ausência de falhas nem cobertura completa. O resultado pede triagem humana e não confirma vulnerabilidade.

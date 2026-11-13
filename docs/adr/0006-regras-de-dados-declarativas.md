# 0006. Regras de dados declarativas

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** AD-06, P-02, P-12

## Contexto

Importar o Swagger direto no ZAP gera valores genéricos. As requisições param na validação (400) ou na duplicidade (409). É preciso gerar dados válidos e únicos por campo. A ideia original era o agente gerar scripts de substituição, mas código gerado por IA e executado na máquina do QA é superfície de ataque e difícil de revisar.

## Decisão

Vamos usar regras declarativas em YAML (`data-rules.yml`), por exemplo "o campo `cpf` usa o gerador `br.cpf`, único". A CLI tem um catálogo de geradores testados. Script Python escrito pelo agente fica como saída de emergência, com revisão humana obrigatória.

## Alternativas consideradas

- **Scripts livres por produto.** Máxima flexibilidade, mas risco e manutenção altos.
- **Apenas exemplos fixos no Swagger.** Não resolve unicidade.

## Consequências

- Cada formato novo vira um gerador no catálogo, com teste. O catálogo cresce de forma controlada.
- Regra declarativa é validada por schema.
- Fluxos de negócio muito específicos podem não caber; a saída por script existe, com revisão.
- O encadeamento entre chamadas (`flows.yml`) é limitado a dependências diretas de um nível na V1: criar A e usar o id em B (P-12).
- Catálogo, regras e encadeamento chegam no M3 e não existem hoje.

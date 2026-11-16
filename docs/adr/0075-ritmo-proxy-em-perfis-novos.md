# 0075. Ritmo proxy em perfis novos, condicionado à prova

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

O [ADR 0067](0067-ritmo-unico-e-medicao-do-executor.md) conserva `legacy` como padrão enquanto a equivalência e a previsão da varredura completa não forem demonstradas. A V1.7 não demonstrou esses critérios; suas medições e limitações permanecem históricas na [referência de desempenho](../reference/scan-performance.md). A V1.8 precisa revalidar a aprovação a cada concessão no proxy, independentemente da escolha de ritmo.

## Decisão proposta

Somente após a prova abaixo, `hdast init --from-letter` gerará `scan.pacing: proxy` em perfis novos. A pessoa continua aprovando o perfil antes da execução. O valor padrão do modelo permanece `legacy`; perfis existentes e aprovações anteriores não são alterados. Alterar um perfil existente de `legacy` para `proxy` exige nova aprovação. A proposta não amplia escopo, força, regras, contas, janela ou limites.

Antes das novas T4 B completas em ambas as APIs vulneráveis, congele uma previsão prospectiva derivada das medições T3 e T4 A da V1.7, incluindo fórmula, fontes, exclusões, hash, instante e revisão. Por API, a razão é a mediana da duração de scan T3 B dividida pela mediana T3 A; o tempo B previsto é essa razão multiplicada pela duração T4 A, e a redução prevista é `100 × (1 − razão)`. Este estimador agregado é distinto do estimador por regra da V1.7 e não comprova retroativamente aquela previsão. A 40026, já não executada, não contribui ao tempo de parede. Compare cada B com sua A em trabalho planejado e executado, regras, entradas, contas, limites e achados, além de estados, interrupções e recusas. Reproduza T2 B seguro para SQL, travessia, autorização, CORS e negative, com referência comparável e sem novos falsos positivos. A promoção depende da equivalência comprovada, inclusive controles aplicáveis, e erro absoluto da redução prevista de no máximo 10 pontos percentuais em cada API. Ausência, divergência ou dado não comparável torna o aceite inconclusivo; não se promove.

A regra 40026 (DOM XSS) requer navegador e permanece uma exclusão pré-existente, com `skipped` e `skip_reason: other`, quando assim observada também na referência comparável. Ela não constitui perda nova nessa comparação, mas continua lacuna explícita: não se declara sua cobertura nem se liga navegador. Outras lacunas, ou divergência de estado ou motivo, não são automaticamente dispensadas. A classificação e sua evidência são documentadas separadamente, preservando as avaliações datadas.

## Alternativas e consequências

Manter `legacy` na geração evita mudar o ritmo antes da prova, mas mantém a sobreposição de atrasos. Migrar perfis antigos implicitamente mudaria o significado de uma aprovação anterior e foi rejeitado. A prova e a mudança de geração são condicionais, não demonstram ganho em produto real e não eliminam a lacuna DOM XSS. Os resultados serão registrados após sua execução; este ADR não afirma sucesso.

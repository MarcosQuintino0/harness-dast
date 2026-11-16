# 0075. Ritmo proxy em perfis novos, condicionado ? prova

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

O [ADR 0067](0067-ritmo-unico-e-medicao-do-executor.md) conserva `legacy` como padr?o enquanto a equival?ncia e a previs?o da varredura completa n?o forem demonstradas. A V1.7 n?o demonstrou esses crit?rios; suas medi??es e limita??es permanecem hist?ricas na [refer?ncia de desempenho](../reference/scan-performance.md). A V1.8 precisa revalidar a aprova??o a cada concess?o no proxy, independentemente da escolha de ritmo.

## Decis?o proposta

Somente ap?s a prova abaixo, `hdast init --from-letter` gerar? `scan.pacing: proxy` em perfis novos. A pessoa continua aprovando o perfil antes da execu??o. O valor padr?o do modelo, perfis existentes e aprova??es anteriores permanecem `legacy` e inalterados; alterar um perfil existente para `proxy` exige nova aprova??o. A proposta n?o amplia escopo, for?a, regras, contas, janela ou limites.

Antes das novas T4 B completas em ambas as APIs vulner?veis, congele uma previs?o prospectiva derivada das medi??es T3 e T4 A da V1.7, incluindo f?rmula, fontes, exclus?es, hash, instante e revis?o. Por API, a raz?o ? a mediana da dura??o de scan T3 B dividida pela mediana T3 A; o tempo B previsto ? essa raz?o multiplicada pela dura??o T4 A, e a redu??o prevista ? `100 ? (1 ? raz?o)`. Este estimador agregado ? distinto do estimador por regra da V1.7 e n?o comprova retroativamente aquela previs?o. A 40026, j? n?o executada, n?o contribui ao tempo de parede. Compare cada B com sua A em trabalho planejado e executado, regras, entradas, contas, limites e achados, al?m de estados, interrup??es e recusas. Reproduza T2 B seguro para SQL, travessia, autoriza??o, CORS e negative, com refer?ncia compar?vel e sem novos falsos positivos. A promo??o depende da equival?ncia comprovada, inclusive controles aplic?veis, e erro absoluto da redu??o prevista de no m?ximo 10 pontos percentuais em cada API. Aus?ncia, diverg?ncia ou dado n?o compar?vel torna o aceite inconclusivo; n?o se promove.

A regra 40026 (DOM XSS) requer navegador e permanece uma exclus?o pr?-existente, com `skipped` e `skip_reason: other`, quando assim observada tamb?m na refer?ncia compar?vel. Ela n?o constitui perda nova nessa compara??o, mas continua lacuna expl?cita: n?o se declara sua cobertura nem se liga navegador. Outras lacunas, ou diverg?ncia de estado ou motivo, n?o s?o automaticamente dispensadas. A classifica??o e sua evid?ncia s?o documentadas separadamente, preservando as avalia??es datadas.

## Alternativas e consequ?ncias

Manter `legacy` na gera??o evita mudar o ritmo antes da prova, mas mant?m a sobreposi??o de atrasos. Migrar perfis antigos implicitamente mudaria o significado de uma aprova??o anterior e foi rejeitado. A prova e a mudan?a de gera??o s?o condicionais, n?o demonstram ganho em produto real e n?o eliminam a lacuna DOM XSS. Os resultados ser?o registrados ap?s sua execu??o; este ADR n?o afirma sucesso.

# ADR 0069: estratégia e limites da prova de desempenho

Status: proposta para V1.7, sem alegação de prova concluída. Data: 2026-11-16.

## Contexto

A redução de atraso pode afetar tráfego, cobertura executada e detecção. A soma dos tempos por regra não é tempo de parede: há sobreposição e custos de preparo, espera, identidade e rede. Um subconjunto não representa automaticamente toda a API; uma declaração de tecnologia pode estar errada sem produzir contradição observável.

## Decisão

Manter A (`legacy`) como padrão e B (`proxy`) como opção sujeita a aprovação. Comparar o mesmo trabalho, força, regras e limites por T1 sem alvo, T2 controles direcionados, T3 pares no subconjunto fixo pré-registrado e T4 completas comparáveis A e B por API. Registrar método, estratos, estimador e ausência de dados antes dos pares. Regra ausente, interrompida ou truncada é lacuna, não tempo zero. Uma T4 B isolada não confirma redução relativa. Sem A comparável, ou com diferença superior a 10 pontos percentuais entre previsão e redução observada, a alegação para a completa é inconclusiva. Meta e condições estão no [plano](../plans/2026-11-16-personalization-and-scan-performance.md), especialmente seções 12.1 e 12.2; o [guia](../reference/scan-performance.md) descreve execução e métricas.

A declaração de tecnologia permanece consultiva e não exclui regras ([ADR 0068](0068-tecnologias-consultivas.md)). Não há rodada cega nesta versão por decisão do briefing. O teto de quatro horas inclui preparo, resets, reprodução T2 do validador e descarte, com parada por falta de reserva.

## Consequências

A prova de planejamento não substitui detecção ou cobertura executada. Estratos e controles ausentes limitam a conclusão, e ganho no subconjunto não garante ganho na completa ou em produto real. A falta de prova, a divergência dos pares ou o descumprimento da meta conserva o padrão A; não se afirma equivalência antes dos resultados. As decisões sobre ritmo, medição e declaração estão nos ADRs 0066 a 0068.

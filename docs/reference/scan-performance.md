# Ritmo e prova de desempenho da varredura

Esta referência descreve o mecanismo e o protocolo da V1.7, sem afirmar resultados. A variante A usa `scan.pacing: legacy`, padrão; B usa `proxy`, opcional e sujeita a nova aprovação humana. Em B o atraso configurado no ZAP é zero e a cerca continua limitando a saída. A comparação mantém força, regras, operações, contas, pontos de entrada, escopo, janela e demais limites. Veja [target.yml](target-yml.md), [ADR 0066](../adr/0066-concessao-real-e-medicao-do-proxy.md) e [ADR 0067](../adr/0067-ritmo-unico-e-medicao-do-executor.md).

O proxy limita a fila, espaça concessões pelo instante real, confere trava e prazo após esperas e libera a fila em cancelamento. Um 429 remoto causa recuo temporário compartilhado pela instância; aceita `Retry-After` em segundos ou data HTTP entre zero exclusivo e 60 segundos inclusivo, ou espera um segundo para valor ausente, inválido ou fora da faixa. O proxy não repete pedidos, inclusive mutações; outro 429 pode renovar o recuo, sem prorrogar prazo nem aumentar taxa. Pedidos negados são contados à parte. A repetição de outros componentes é independente deste recuo.

A declaração `technologies.value` vem da carta e é **consultiva**: nenhuma regra é excluída por tecnologia. A ausência de contradição observada não confirma a declaração. Exclusão efetiva está adiada ([ADR 0068](../adr/0068-tecnologias-consultivas.md)).

## Métricas

`metrics.json` reúne duração por etapa, operações e regras, tráfego e `timing`; `scan.json` registra limites e resultados; `rule-stats.json` conserva estados por regra.

| Campo de `timing` | Interpretação |
| --- | --- |
| `local_queue_seconds` | Soma das esperas individuais desde o início do executor serial até o preparo de cada trabalho. |
| `authentication_seconds` | Ativação, troca e renovação de identidade e Replacer. |
| `proxy_grant_wait_seconds` | Soma das esperas de concessão dos pedidos liberados no scan. |
| `proxy_network_seconds` | Soma dos tempos entre concessão e resposta ou erro, incluindo DNS, conexão e processamento do servidor. |
| `zap_delay_seconds` | Atraso efetivo do ZAP, indisponível quando não medido; `scan.json` → `limits.delay_ms` é o atraso configurado. |
| `cpu_seconds` | CPU da CLI entre amostras; não inclui ZAP nem proxy. |
| `memory_peak_bytes` | Pico residente histórico da CLI observado nas amostras, não apenas do scan nem dos contêineres. |

Os tempos podem se sobrepor e não se somam para obter tempo de parede. `null` significa indisponível, não zero. As somas do proxy ficam nulas sem linhas elegíveis ou se faltar a medida em qualquer linha elegível. Medidas de contêineres do suporte de testes são separadas da CLI. Verifique disponibilidade, estados, interrupções e recusas antes de interpretar totais.

## Preparar a comparação

O laboratório é compartilhado. Antes de subir pilha ou executar integração, adquira exclusivamente `C:\harness-dast-artefatos\lab.lock`, registre versão, hora UTC e trabalho; se já existir, não remova trava alheia. Ao fim do bloco, derrube a pilha, confira `docker compose ls -a` e só então retire a própria trava. Reconstrua a imagem do proxy quando sua fonte mudar. Autorização, perfis e segredos seguem [CLAUDE.md](../../CLAUDE.md): aprovação é feita por pessoa; agente não aprova nem manipula segredos. Use apenas o laboratório local.

Antes dos pares, registre por API versão e configuração, perfil e aprovação, modo, matriz fixa, seleção por mecanismo, contas, autenticação, pontos de entrada, parâmetros, dependências, estratos e classes de controle. A matriz está em [v17_matrix.py](../../tests/integration/v17_matrix.py); estratos ausentes são limitações. Compare trabalho planejado e executado, pedidos, regras indisponíveis, paradas e resultados; alertas ou hash não substituem essa comparação. Registre ordem, resets, prazo, diretório de artefatos e estimador antes da coleta. Preserve artefatos sanitizados.

O teto desta execução é quatro horas de laboratório, incluindo preparo, resets, reprodução T2 do validador e encerramento. Após os primeiros pares, revise o tempo restante com reserva conservadora e não inicie cenário que não caiba. Sem espaço para pares adicionais ou T4, registre inconclusão. Não rode gates intensivos de CPU durante medições. Consulte as seções 12.1 e 12.2 do [plano](../plans/2026-11-16-personalization-and-scan-performance.md) e o [briefing](../plans/2026-11-16-execucao-v1-7-velocidade.md).

## Executar e julgar T1–T4

1. **T1 — sem alvo:** execute testes unitários e de contrato pertinentes, inclusive matriz, política, aprovação, relógio e proxy. Compare item a item operações, contas, regras, força, pontos de entrada e pré-condições de A e B. T1 prova planejamento, não detecção.
2. **T2 — controles direcionados:** `uv run pytest -m lab_fast` executa o conjunto rápido disponível. `uv run pytest -m integration tests/integration/test_v17_performance.py -k test_v17_t2_sql` compara SQL genérica e seu controle em ambos os modos e variantes. Este teste não cobre todas as classes: execute e registre controles adicionais necessários, seguros e vulneráveis, ou declare lacunas.
3. **T3 — subconjunto fixo:** `uv run pytest -m integration tests/integration/test_v17_performance.py -k test_v17_t3` agenda três pares A/B por API na ordem AB, BA, AB, com pilha limpa por cenário. Use a mesma política e força da completa. O resultado vale para estratos exercitados; classe ausente, operação não executada ou regra interrompida limita a conclusão. Se pares divergirem no sinal ou mais de 10 pontos percentuais, planeje dois pares adicionais se couberem; senão, resultado inconclusivo. O teste cobre três pares; extras exigem execução e identificação explícitas sem sobrescrever evidências.
4. **T4 — completa:** `uv run pytest -m integration tests/integration/test_v17_performance.py -k test_v17_t4` agenda A e B em cada API no modo vulnerável. Compare condições equivalentes e confirme detecção dos controles e cobertura executada. B isolada mede duração B, não redução relativa. Referência A ausente ou não comparável torna o ganho inconclusivo.

Os testes V1.7 exigem `HDAST_IT_METRICS_DIR` para diretório externo e `HDAST_V17_DEADLINE_EPOCH` com prazo absoluto em segundos Unix. O suporte verifica reserva mínima antes de cada cenário. Veja o arquivo de teste para parametrizações e limites atuais. Não execute sem trava e pré-requisitos. O briefing dispensa rodada cega nesta versão; T1–T4 não demonstram autonomia do agente.

## Estimador e limites da alegação

Antes dos pares, registre fórmula, dados necessários, exclusões e tratamento de ausências. Uma opção, somente com medições A completas comparáveis por operação e regra, é calcular para cada regra presente e concluída a razão entre a mediana dos tempos B e A no subconjunto, ponderar essa razão pelo tempo da mesma regra na referência A completa e dividir pela soma dos pesos. A redução prevista é `1 - razão ponderada`. Registre regras e estratos que sustentam a projeção e a parte do tempo de parede não explicada. Regra ausente, truncada ou interrompida nunca vale zero: sem dados ou representatividade, não há estimativa confiável. Esta ponderação é modelo de previsão, pois regras podem se sobrepor e não representam fila, login, preparo e rede de forma aditiva.

Na T3, registre redução mediana por API e critérios de qualidade da seção 3 do plano; a meta prévia é ao menos 15%. Na T4, calcule redução medida entre A e B completas comparáveis. Se a diferença em relação à previsão superar 10 pontos percentuais, a alegação para a completa é inconclusiva. Trabalho não executado, detecção perdida, falso positivo reproduzível, falha de autorização ou troca de identidade impedem alegar equivalência. Sem prova ou meta, mantenha `legacy` como padrão e registre o motivo. Uma previsão válida não demonstra ganho em produto real.

A decisão sobre V1.10 exige medir a fração do tempo que poderia ser paralelizada sem regras de tempo, mutação compartilhada ou dependências. A API do ZAP não fornece intervalos por regra: sem linha do tempo verificável e sem separar sobreposições, não se pode somar durações de regras nem calcular essa fração com confiança. Registre a medida como indisponível e a decisão como bloqueada por falta de evidência; não invente intervalos. Abaixo de 40% medidos, o plano não inicia V1.10.

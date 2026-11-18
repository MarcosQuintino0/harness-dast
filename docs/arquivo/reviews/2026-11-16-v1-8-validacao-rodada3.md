# V1.8 — validação independente da rodada 3

Data: 2026-11-16. Validador novo GPT 6.1 Terra medium; sem implementação anterior nesta rodada. Base examinada: `d200826`, incluindo código de produção `59078a1`. Parecer limitado ao laboratório local e aos artefatos disponíveis.

## Decisão: corrigir a lacuna de prova

Não autorizar a promoção de `proxy` no `init` nem declarar a equivalência global exigida pelo protocolo. As metas numéricas de desempenho passaram, mas há diferenças de pedidos não DOM sem explicação e faltam dados para demonstrar igualdade dos vetores e das pré-condições. Isso é uma insuficiência de evidência, não um defeito de produto demonstrado. A execução com `legacy` preservado pode ser avaliada separadamente; este parecer não libera o PR como pronto sob o gate de qualidade integral. Investigar as diferenças e produzir evidência comparável antes de voltar a pedir aceite; não inferir perda nem equivalência pelo aumento de contagem. Não repetir T4 automaticamente sem protocolo justificado.

## Desempenho e previsão

A previsão foi congelada antes das novas T4; o conhecimento de B anteriores implica risco declarado de seleção. A clarificação também precedeu as T4. A divergência de hash CRLF/LF foi tratada por equivalência de conteúdo com normalização exclusiva de finais de linha; os arquivos congelados não foram reescritos. Veja [protocolo e medições](../../evals/measurements/v1-8/round3/README.md) e [matriz](../../evals/measurements/v1-8/round3/t4-comparison.json).

| API | A histórica (s) | A nova (s) | B nova (s) | Erro ganho com A nova / histórica |
| --- | ---: | ---: | ---: | ---: |
| Clínica | 619,491791 | 593,680062 | 311,032483 | 2,522 / 4,705 p.p. |
| VAmPI | 133,769327 | 126,310181 | 49,884473 | 0,454 / 1,748 p.p. |

As duas A ficaram abaixo de 1,05 da histórica e os quatro erros ficaram até 10 p.p. A mediana do `_detect` no microbenchmark do proxy no bind mount caiu de 5,7759215 ms para 0,026176 ms; p95 de 6,389762 para 0,042773 ms. O teste posterior usou 100 aquecimentos e 1.000 amostras e não comprova, sozinho, equivalência de T4. Houve testes unitários curtos em paralelo durante a reserva da coordenação, além de outra atividade reportada por ela; não há prova de efeito sobre o tempo.

## Seis critérios de qualidade

| Critério | Evidência e limite |
| --- | --- |
| Autorização | Testes da vigia, fila e aprovação passaram; a corrida real independente no VAmPI observou `allow`, remoção da aprovação sintética e `deny/approval_changed`, sem concessão posterior. O T2 seguro verificou host permitido, ausência de DELETE e `allowed_outside_allow == 0`. Contagens isoladas não comprovam cada janela e limite em toda T4. Não executei aprovação humana, operações de segredo nem limpeza. |
| Cobertura planejada | T1 histórico compara matriz; nas T4 as operações e regras observadas coincidem. Política e versão disponíveis coincidem; campos de plano, pontos de entrada e pré-condições não estão integralmente disponíveis. Igualdade integral não demonstrada. |
| Cobertura executada | Clínica A/B novas coincidem nos campos comparados, mas em `atualizarPaciente`/90035 foram 61 pedidos contra 47 históricos. No VAmPI B nova fez 28 pedidos em `api_views.books.get_by_title`/40008 contra 4 na A nova e B histórica. Não há vetores sanitizados suficientes para explicar; igualdade completa inconclusiva. A 40026 foi dispensada comparativamente só por `skipped/other/0` igual por operação; DOM XSS continua sem cobertura. |
| Detecção | Achados e alertas disponíveis coincidem nas comparações; controles anteriores em `closure/` registram detecção por API. Eles são históricos, não nova reprodução. Não se infere identidade de todos os vetores a partir de títulos e contagens. |
| Falsos positivos | Controles seguros anteriores nas duas APIs são evidência histórica. Reproduzi Clínica segura com estratégia e `legacy`: sem achado de severidade alta, authz concluído sem achados e nove negativos de leitura rejeitados. Isso não prova ausência universal de falsos positivos nem repete o VAmPI seguro nesta rodada. |
| Estado e identidade | No T2 independente, 2.043/2.043 mensagens do scanner tinham Authorization e 658/658 escritas tinham cabeçalho e cookie CSRF; zero rejeições CSRF, sem regras restantes ou segredo detectado. Presença do cabeçalho não atesta identidade efetiva por pedido; criação e estado completo não são provados pelos resumos T4. |

## Reprodução independente

- `uv run pytest -q tests/unit/adapters/scope_proxy/test_gate_watch.py tests/unit/adapters/scope_proxy/test_guard_cost_acceptance.py tests/unit/adapters/scope_proxy/test_approval_watch.py`: **15 passaram**.
- `uv run pytest -q tests/unit/test_v18_round3_comparison.py`: **3 passaram**.
- Após fast-forward e aquisição exclusiva de `lab.lock`, `uv run pytest -q -o addopts='' tests/integration/test_v18_revocation.py 'tests/integration/test_lab_strategy.py::test_strategy_preserva_controles_direcionados[legacy-secure-clinica-piloto]'`: **2 passaram em 374,97 s**. Corrida `2026-11-16T11-42-59Z-vampi-42ff`, saída 4, recusa observada em 1,015 s incluindo ritmo de 1 pedido/s e polling. T2 `2026-11-16T11-44-45Z-clinica-piloto-e90e`. Evidências sanitizadas em `C:\harness-dast-artefatos\v1-8\round3\validator3`.
- Após os testes, `docker compose ls -a` não listou pilhas; removi apenas a minha trava depois de conferir sua identificação. Não refiz T4, rodada cega ou suíte completa.

A vigia espera 50 ms após cada checagem, além da E/S, e a concessão trava se o snapshot tiver mais de 200 ms desde o início da última checagem bem-sucedida. Os unitários com relógio controlado e leitura bloqueada sustentam esse contrato; a corrida real sustenta revogação observada e latch. Nenhum dos dois garante visibilidade do sistema de arquivos em prazo rígido ou cancela concessões já encaminhadas. A revisão humana exigida por `CONTRIBUTING.md` não é substituída por este parecer.

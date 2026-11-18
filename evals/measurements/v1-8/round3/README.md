# V1.8, rodada 3: custo do guard e nova comparação A/B

Provas locais após a regressão de velocidade identificada na rodada 2. Os registros
anteriores em `../closure/` permanecem históricos. Nenhum produto real foi testado.

## Ordem e congelamento

1. A [nova previsão](forecast-frozen.json) foi integrada em `4c5dc94`, às
   10:54:58 UTC, antes da medição inicial e das quatro T4. É o mesmo blob Git
   `c5044213473f96969c3d86301acd93fec9e9f20b` do commit original `ed7f00b` da
   worktree do agente. A referência a esse commit no arquivo congelado é preservada;
   `4c5dc94` é sua revisão integrada e durável.
2. A medição inicial foi registrada em `cb66f17`, antes da implementação `59078a1`.
3. A [clarificação do protocolo](protocol-clarification.json) foi integrada em
   `97429b8`, às 11:06:56 UTC, antes das quatro T4. Exige erro de até 10 pontos
   percentuais usando tanto A histórica quanto A nova, além dos outros gates.
4. A medição posterior foi integrada em `55e17b9`. As quatro T4 começaram depois,
   no mesmo laboratório e sem outra pilha concorrente.

A fórmula congelada é `T4_A_histórica × mediana(T3_B) / mediana(T3_A)`:
340,181947 s para a Clínica e 52,223020 s para o VAmPI. O conhecimento das B
anteriores é declarado; este experimento não reabilita retroativamente a previsão
da V1.7. Pequenos defeitos textuais do JSON congelado não foram corrigidos após o
congelamento. Fórmula, números, hashes e arquivo original permanecem preservados.

## Microbenchmark no bind mount real

O suporte `tests/integration/test_v18_guard_cost.py` executa o benchmark dentro do
contêiner real do proxy e instancia o mesmo `ScopeProxyEngine` gerenciado da
operação. Faz 100 aquecimentos e 1.000 amostras, separadas por 2 ms fora do trecho
cronometrado, com aprovação válida e sem medir uma recusa já travada. As fontes,
imagem, montagens, run IDs e amostras estão nos JSONs; os hashes publicados não
contêm os documentos de aprovação ou credenciais.

| Caminho | Antes: mediana / p95 | Depois: mediana / p95 |
| --- | ---: | ---: |
| `_detect` | 5,7759215 / 6,389762 ms | 0,026176 / 0,042773 ms |
| Alternativa só metadados | 1,6170575 / 3,726572 ms | 1,628963 / 1,881520 ms |

Fontes: [antes](guard-before-vampi.json) e [depois](guard-after-vampi.json). Como
apenas metadados também excedeu a meta de 1 ms, foi escolhido o fallback autorizado
de vigia. Ela conserva hash completo, verificação inicial síncrona e espera de
50 ms entre verificações; a E/S se soma à espera. Cada concessão consulta estado
em memória e recusa snapshot com mais de 200 ms desde o início da última
verificação bem-sucedida. Erro, encerramento ou alteração observada trava a saída.
Autorização, janela e prazo permanecem verificados por concessão. O limite não é
garantia rígida de visibilidade do sistema de arquivos nem cancela pedidos já
concedidos.

## Comparação e limites

`compare_round3.py` confere A histórica contra A nova, B histórica contra B nova e
A nova contra B nova. Compara operações, desfechos, regras, contagens por regra,
achados por origem e atributos disponíveis, além de registrar contexto, campos
ausentes e diferenças observadas. Presença de Authorization não atesta identidade;
ausência de diferença em dados incompletos não prova igualdade integral.

A regra 40026 só é excluída da comparação quando conserva `skipped/other/zero`
por operação, como na linha de base. Continua sem cobertura DOM XSS. Não se liga
navegador. T4 vulnerável não comprova falsos positivos no modo seguro: os controles
seguros e suas limitações são avaliados separadamente.

Os artefatos brutos desta rodada ficam em
`C:\harness-dast-artefatos\v1-8\round3`. Somente resultados revisados são
versionados; estado descartável, credenciais e documentos brutos não são copiados.
Tempos T4 são os intervalos `scan.started_at`–`scan.finished_at`, distintos do tempo
total de pytest, build e preparação.

## Resultados

As quatro T4 passaram em 1.463,09 s. A Clínica fez A em 593,680062 s e B em
311,032483 s; VAmPI fez A em 126,310181 s e B em 49,884473 s. Ambas as A
atenderam ao teto de regressão de 5% e ambas as B passaram a previsão nas duas
fórmulas congeladas. A [matriz completa](t4-comparison.json) preserva a divergência
histórica de 47 para 61 pedidos de SSTI na Clínica e de 4 para 28 de Parameter
Tampering na nova B do VAmPI frente à nova A e à referência histórica.
**Não promover** o init: o aumento não prova perda, mas os dados disponíveis não
explicam a diferença nem atestam equivalência dos vetores.

A [corrida real](revocation-vampi.json) passou: concessão, revogação da aprovação
temporária e recusa `approval_changed`, sem concessão posterior. A observação de
1,031 s inclui a taxa do cliente e não mede a validade de 200 ms do snapshot.

Na primeira chamada, o comparador recusou o hash do congelamento: o protocolo
registrava bytes CRLF da worktree original, enquanto o blob Git e o checkout
principal usavam LF. O comparador passou a verificar a reconstrução exata das
terminações, preservando hash registrado e observado e recusando alteração de
conteúdo ou terminações mistas. O SHA-256 LF é
`d548396364f7a6aed57c3c400bd862344a2058eece93857a51fc9e86d17847c5`;
o CRLF reproduz exatamente o hash congelado
`243fb1b0ec5d8b63b6dc5149327f49faff0ef7f59f81ad7348cc3942eeb7d597`.
Nenhum arquivo congelado foi modificado.

Os limites dos controles anteriores, concorrência offline observada, nova
validação e entrega estão no [relatório da rodada 3](../../../../docs/arquivo/reviews/relatorio-v1.8-rodada3.md).

# V1.8, rodada 3: correção do custo por concessão

Data: 2026-11-16. Este relatório complementa o [fechamento anterior](relatorio-v1.8-fechamento.md), preservado como registro histórico. A regressão de velocidade foi corrigida: o microbenchmark e as quatro T4 atingiram as metas temporais. **Não promover `proxy` no init**: a equivalência de contagens não foi demonstrada em todas as comparações. Não houve teste em produto real, navegador no ZAP, aprovação humana executada pelo agente ou merge do PR.

## Passos 1 a 8 do briefing

| Passo | Estado | Arquivos, testes e prova |
| --- | --- | --- |
| 1. Inventário e ADRs | Feito | Inventário e ADRs 0070–0075 preservados; [0072](../../decisoes/0072-compilacao-sem-trafego.md) e [0075](../../decisoes/0075-ritmo-proxy-em-perfis-novos.md) descrevem a vigia e a condição de promoção. A previsão e sua clarificação foram commitadas antes das T4. |
| 2. Domínio | Feito | Modelos congelados de envelope/estratégia, validações e fingerprint conservam o contrato entregue. O padrão de `ScanConfig` continua `legacy`; nenhuma aprovação antiga muda. |
| 3. Aplicação e CLI | Feito nos limites declarados | Consultas, diff, migração, captura pública e prévia continuam como no fechamento anterior. A prévia é simbólica; não afirma catálogo instalado, alcance ou cobertura executada. |
| 4. Execução pelo plano | Feito | Plano concreto congelado e executor serial preservados. `scope_proxy/gate_watch.py`, `gate.py`, `engine.py` e `docker/scope-proxy/addon.py` retiram E/S da concessão gerenciada e invalidam a vigia no encerramento. Testes cobrem leitura bloqueada, erro, expiração, encerramento e mutação com tamanho/mtime preservados. |
| 5. Migração e compatibilidade | Feito | Cópia explícita e nenhuma ativação automática. A preparação de promoção foi arquivada sem aplicação; init, modelo, perfis e aprovações existentes permanecem como estavam. |
| 6. Skills e avaliação | Feito | Contratos e separação da cópia cega preservados; guias e referência descrevem a vigia. Não houve rodada cega nesta versão, conforme o briefing. |
| 7. Provas | Feito com limite comparativo | Micro antes/depois, quatro T4 A/B vulneráveis e corrida real concluídos. Controles seguros e captura pública da rodada anterior continuam identificados como provas anteriores, sem apresentá-los como repetição desta rodada. |
| 8. Validação independente | Feito; parecer corrigir | [Novo Terra medium](2026-11-16-v1-8-validacao-rodada3.md) revisou código, documentos e matrizes; 18 testes offline e duas provas reais passaram. A lacuna de equivalência impede o aceite global e a retirada do rascunho. |

## Contratos, falha fechada e aprovação

Os arquivos públicos continuam `target.yml`, `strategy.yml` versão 1 e os documentos referenciados. `strategy validate`, `strategy diff`, `strategy migrate`, `strategy capture` e `plan --dry-run` aceitam `--products-dir`. O envelope JSON v1 usa `schema_version`, `ok`, `data` ou erro estruturado. Saídas: sucesso 0, configuração 2, aprovação/escopo 3, ferramenta externa 5 e pilha ocupada 8. A corrida de `probe` interrompida durante autenticação conserva a saída 4 da etapa. Migração e captura criam cópias exclusivas, sem ativação, nova autoridade ou alteração da aprovação.

O proxy gerenciado continua vinculando aprovação e perfil por hash completo e assinatura estável, sem consulta de rede. A verificação inicial é síncrona. Uma vigia verifica fontes e arquivo de stop e espera 50 ms após cada verificação; a E/S se soma à espera. Cada concessão lê o estado publicado sob lock curto e recusa snapshot com idade **superior a 200 ms desde o início da última verificação bem-sucedida**, mesmo se a vigia estiver bloqueada. Erro, encerramento ou mudança observada trava a saída. Autorização, janela e prazo são verificados em cada concessão. Alterações exigem recriar a pilha; a aprovação só precisa ser renovada se o fingerprint protegido mudar.

Este é um limite de idade do estado, não garantia de visibilidade imediata do bind mount nem de agendamento rígido de 50 ms pelo sistema operacional. Pode haver concessões entre a mudança e sua detecção/expiração; pedidos já concedidos não são cancelados. As raízes dos mounts devem permanecer estáveis. A versão observada do ZAP também não autentica criptograficamente sua instância. Reutilização executável de conhecimento permanece para a V1.9.

## Microbenchmark antes e depois

O [suporte e a proveniência](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/round3/README.md) identificam imagens, fontes, montagens e amostras. O benchmark instancia o engine real dentro do contêiner do proxy, com binds reais, 100 aquecimentos e 1.000 amostras válidas, separadas por 2 ms fora do trecho medido.

| Caminho | Mediana antes | p95 antes | Mediana depois | p95 depois |
| --- | ---: | ---: | ---: | ---: |
| `RunGate._detect` | 5,775922 ms | 6,389762 ms | 0,026176 ms | 0,042773 ms |
| Só metadados | 1,617058 ms | 3,726572 ms | 1,628963 ms | 1,881520 ms |

Somente metadados também excedeu 1 ms; por isso foi escolhido o fallback de vigia autorizado pelo dono. A verificação conserva SHA-256 completo fora da concessão, incluindo a detecção de conteúdo alterado com tamanho e mtime preservados. As duas execuções de benchmark passaram. Seus resultados são micro medições locais, sem extrapolação para outros sistemas.

## Previsão congelada e T4

A [previsão](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/round3/forecast-frozen.json) foi integrada em `4c5dc94`, às 10:54:58 UTC; a [clarificação](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/round3/protocol-clarification.json) em `97429b8`, às 11:06:56 UTC. Ambas antecedem as quatro T4, iniciadas às 11:14 UTC. Fórmula mantida: `T4_A_histórica × mediana(T3_B) / mediana(T3_A)`. Ganhos previstos: 45,086932% e 60,960393%. O conhecimento das B anteriores está declarado; a previsão histórica da V1.7 não recebe aceite retroativo.

| API | A V1.7 | A nova | B V1.7 | B rodada 2 | B prevista | B nova |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Clínica Piloto | 619,491791 s | 593,680062 s | 312,545142 s | 436,801836 s | 340,181947 s | 311,032483 s |
| VAmPI | 133,769327 s | 126,310181 s | 51,584607 s | 82,231248 s | 52,223020 s | 49,884473 s |

As A novas ficaram 4,166597% e 5,576126% mais rápidas que as respectivas A históricas, atendendo ao limite de regressão de 5%. Os ganhos B frente a A nova foram 47,609411% e 60,506372%, com erros de previsão de **2,522479 e 0,454021 pontos percentuais**. Usando A histórica, os erros foram **4,705383 e 1,748194 pontos**. Ambos os denominadores passaram no teto prospectivo de 10 pontos por API. As quatro T4 passaram em **1.463,09 s** de suíte. Os tempos da tabela são somente `scan.started_at`–`scan.finished_at`, sem build, preparação e demais etapas.

O comparador inicialmente recusou a previsão porque o protocolo continha o SHA-256 dos bytes CRLF da worktree do agente, enquanto o blob Git e o checkout principal tinham LF. Não se alterou nenhum arquivo congelado: a reconstrução exclusiva das terminações reproduziu exatamente o hash registrado. O comparador registra ambos os hashes/variantes, recusa conteúdo alterado e terminações mistas; nove testes dirigidos passaram. A ordem de commits e o blob original continuam verificáveis.

## Qualidade e decisão de promoção

A [matriz completa](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/round3/t4-comparison.json) preserva fontes, hashes, run IDs, diferenças, achados e campos ausentes nas seis comparações. Operações, desfechos, regras, alertas e achados disponíveis coincidem; as contagens de pedidos têm duas diferenças:

- Clínica: as novas A e B coincidem entre si, mas `atualizarPaciente`/90035 (SSTI) fez **61 pedidos**, contra **47** nas duas referências da V1.7. A operação passou de 1.274 para 1.288 pedidos.
- VAmPI: `api_views.books.get_by_title`/40008 (Parameter Tampering) fez **28 pedidos na B nova**, contra **4** na A nova e nas referências A/B históricas. A operação passou de 467 para 491 pedidos.

Essas regras terminaram `completed`, com zero alertas e sem truncamento. Política, força e limites correspondentes coincidem; entre A e B, as diferenças esperadas são `scan.pacing` e o atraso de 20 para 0 ms. Os artefatos sanitizados não contêm corpos/vetores suficientes para explicar os pedidos adicionais. As diferenças não provam perda de cobertura nem defeito, mas impedem afirmar igualdade integral de trabalho. **Não promover**: o init permanece `legacy`, assim como o padrão do modelo. Não houve migração ou alteração de aprovação antiga. A preparação não aplicada ficou em arquivo externo, SHA-256 `c0d5351127a17d06baa34d18e069d1d0d3e96f00c58770911354f5db7ee9c22f`.

| Critério | Clínica vulnerável | Clínica segura | VAmPI vulnerável | VAmPI seguro |
| --- | --- | --- | --- | --- |
| Autorização | T4 A/B; nenhuma concessão fora do allow observada | T2 B anterior; reprodução independente selecionada nesta rodada | T4 A/B e revogação real; sem allow posterior à recusa | T2 B anterior, sem afirmar nova T4 segura |
| Cobertura planejada | 28 operações e política correspondentes; prévia/corpos têm limites | T2 anterior de SQL/travessia e controles separados | 10 operações e política correspondentes; vetores incompletos | T2 anterior e CORS separado |
| Cobertura executada | 1.204 pares não DOM; +14 pedidos históricos não explicados | T2 anterior concluído | 430 pares não DOM; +24 pedidos B não explicados | T2 anterior concluído |
| Detecção | 98 ZAP, 4 authz, 0 negative, atributos/fingerprints disponíveis iguais | Controles anteriores limpos nos limites do fechamento | 30 ZAP, 3 authz, 0 negative, atributos/fingerprints disponíveis iguais | Zero negativos de leitura elegíveis não conta como sucesso |
| Falsos positivos | T4 vulnerável não conclui modo seguro | Controles B anteriores: zero altos ZAP; baixos de escrita já existiam em A | T4 vulnerável não conclui modo seguro | Controles anteriores: zero altos ZAP; anônimos também existiam em A |
| Estado e identidade | 17.968/17.968 mensagens com Authorization em A/B; 5.050 escritas com par CSRF | Evidência anterior e reprodução selecionada, sem atestar cada identidade | A: 4.272/4.272; B: 4.296/4.296 com Authorization | Evidência anterior de aliases, com limitações explícitas |

A regra DOM XSS 40026 conserva `skipped/other/zero` em cada operação de todas as comparações: é exclusão pré-existente, não perda comparativa nova, e continua sem cobertura. Nenhuma outra diferença foi dispensada. Presença de Authorization não prova validade ou identidade efetiva. Campos nulos/ausentes não viram prova automática de igualdade; o comparador é instrumento de revisão, não aprovação automática. Os controles seguros, CORS, authz, negative e captura pública anteriores estão no [fechamento](relatorio-v1.8-fechamento.md), com suas falhas e limitações preservadas.

## Corrida, limitações temporais e entrega

A coordenação repetiu a [corrida real](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/round3/revocation-vampi.json): `allow`, remoção da aprovação temporária, `deny/approval_changed`, sem allow posterior; `probe` terminou com saída 4. O teste passou em 46,91 s. A primeira recusa foi observada 1,031 s após a remoção, incluindo espera do cliente a 1 pedido/s e polling; isso não mede isoladamente o limite de 200 ms. Testes com relógio controlado e leitura bloqueada verificam o fail-closed por idade e a fila não bloqueada.

O validador repetiu a corrida (1,015 s de observação, saída 4, sem allow posterior) e o T2 Clínica segura com estratégia e `legacy`: **2/2 em 374,97 s**. O T2 teve zero achados altos, authz concluído sem achados, nove negativos de leitura rejeitados e 2.043/2.043 mensagens com Authorization; 658/658 escritas tinham cabeçalho e cookie CSRF, sem rejeição CSRF. Também passaram 15 testes da vigia/aprovação e três do comparador. A [proveniência independente](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/round3/validator3/provenance.json) identifica as cinco evidências sanitizadas. O parecer **corrigir** distingue ausência de defeito demonstrado no guard de ausência de prova de equivalência global: a não promoção cumpre o fallback pedido, mas não libera o PR como pronto.

Houve somente uma pilha de laboratório e scans seriais. Durante a primeira A da Clínica, ocorreram testes offline dirigidos de agentes: grupos de 3,99 s e 1,36 s, outros grupos menores que 8 s e uma cópia cega interrompida com atividade observada de pelo menos 18,88 s, entre 11:23:29 e 11:23:48 UTC. Os horários exatos de início/fim de todos os grupos não foram cronometrados. Essa concorrência de CPU/E/S é uma limitação da medição; não se atribui a ela causa para tempos ou contagens. Não houve nova suíte concorrente nas B após a orientação de cessar testes. As execuções originais não foram substituídas nem selecionadas pelo resultado.

O rebase sobre a V1.7 em `a267ae2` já havia sido concluído na rodada anterior, preservando métricas, ritmo e sampler da V1.7 e estratégia/compilação da V1.8. Os conflitos resolvidos e as provas anteriores estão no relatório de fechamento. Esta rodada não alterou `main`, `develop` ou o checkout `C:\harness-dast`.

Os oito gates completos estão no [manifesto final](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/round3/gates-final.json), com fonte, comandos, saídas e tempos: Ruff check/format, mypy Windows/Linux, import-linter, Vulture, pytest completo e gitleaks sem afrouxamento. Logs, JUnit e estado descartável ficam em `C:\harness-dast-artefatos\v1-8\round3`. A conferência do CI remoto e o último SHA publicado constam na entrega e no [PR #24](https://github.com/MarcosQuintino0/harness-dast/pull/24).

O PR permanece **em rascunho e sem merge** porque o novo validador não decidiu continuar. As worktrees auxiliares são removidas após conferir limpeza e equivalência dos commits; a única preparação não aplicada, `733f3d9`, foi preservada no patch externo antes de remover sua branch. As pilhas foram desmontadas e cada reserva removeu apenas sua própria trava. A decisão pendente é resolver a lacuna de prova antes do aceite global, seguindo a [proposta de investigação dirigida](../plans/2026-11-16-v1-8-prova-pendente-rodada3.md), ou obter decisão explícita do coordenador geral sobre avaliar a base separadamente. Nenhuma T4 adicional foi executada para selecionar um resultado favorável.

Programação e suporte de desempenho: `/root/proxy3` e `/root/perf3`, GPT 6.1 Terra high. QA independente: `/root/qa3`, Terra high. Documentação: `/root/docs3`, Terra high. Validação nova: `/root/validator3`, Terra medium, sem implementação. Cada agente usou sua própria worktree. A coordenação permaneceu nesta sessão Codex.

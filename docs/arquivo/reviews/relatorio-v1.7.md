# Relatório da V1.7 — velocidade serial

Registro de 2026-11-16, finalizado em 2026-11-16T08:51:18.115102+00:00. Versão no projeto: **1.7.0**. Entrega **parcial**, com `legacy` como padrão e tecnologias apenas consultivas. O validador independente decidiu **corrigir para o aceite integral**; a entrega parcial pode seguir para revisão humana. Não há equivalência integral de qualidade nem previsão de ganho da completa confirmadas.

O trabalho foi integrado em `feat/v1-7-velocidade`, na worktree `C:\harness-dast-wt\v1-7`. O checkout `C:\harness-dast`, as branches `main`/`develop` e as worktrees V1.8 não foram alterados. O destino do PR é `develop`; não há merge autorizado. Este registro fecha as provas e gates antes da publicação do PR; URL e HEAD publicado são informados na entrega da coordenação.

## 1. Passos do briefing

| Passo | Resultado | Arquivos, testes e prova |
| --- | --- | --- |
| 0. Crítica | Feito | Crítico Terra 6.1 medium novo, em árvore própria. Seção 12.1 do plano: limites de representatividade, estimador prospectivo e risco de tecnologia errada sem sinal incorporados antes de programar. |
| 1. Medição | Feito em parte | `run_metrics.py`, `scan_runner.py`, `scan_process.py`, proxy e coletores em `tests/integration/v17_*`. Fila, autenticação, concessão e resposta separados; CPU da CLI e picos amostrais dos contêineres registrados. Atraso efetivo acumulado do ZAP continua `null`; resposta do proxy inclui DNS, conexão e servidor, não mede rede pura. |
| 2. Controle versionado | Feito em parte | `v17_matrix.py`, `test_v17_performance.py` e pré-registro fixam 10/7 operações por mecanismo. Executaram-se 9/6 por exclusões de mutação preexistentes. Estratos e classes ausentes são explícitos; a amostra não comprova todas as classes. |
| 3. Ritmo único | Feito em parte | `scan.pacing`, `scan_policy.py`, fila/concessão e recuo do proxy. T1 compara matrizes item a item e relógio falso cobre espera, parada, janela e prazo; 12 T2 direcionados aprovados e 12 scans T3 válidos. Ganhos descritivos sem aceite integral; A continua padrão. |
| 4. Tecnologia | Feito em parte | Carta, perfil, fingerprint, entrevista e caso/régua da avaliação preparados; ADR 0068. Declaração protegida pela aprovação, sem exclusão ativa. Seleção efetiva adiada porque ausência de contradição não confirma declaração correta. |
| 5. Prova T1–T4 | Feito em parte | Campanha executada, incluindo quatro completas A/B e controles complementares. Há lacunas de regras, classes, identidade e previsão; não se declara a seção 5.4 aceita. Nenhuma rodada cega ou prova em produto real, conforme o briefing. |
| 6. Validação | Feito | Terra 6.1 medium novo, sem implementação, em árvore própria: revisão, 49 T1 dirigidos e dois T2 SQL B da Clínica reproduzidos, 2/2 em 281,64 s. Parecer `corrigir`, commit d5bed3d; não substitui revisão humana. |

Os ADRs 0066–0069 permanecem propostos. O [parecer independente](validacao-v1.7.md) e o [QA anterior ao laboratório](qa-v1.7.md) são registros distintos; o segundo não foi reescrito como prova final.

## 2. Tempos e previsão

Tempo de parede do **scan**, separado de `run`, preparação e desmontagem. T3 usou três pares por API em ordem AB, BA, AB. A redução é a mediana dos percentuais por par; não é automaticamente a razão entre as duas medianas de duração.

| API | T3 A, mediana | T3 B, mediana | Redução mediana pareada | Amplitude entre pares |
| --- | ---: | ---: | ---: | ---: |
| Clínica Piloto | 218,032712 s | 119,728451 s | 45,0995% | 0,08285 pp |
| VAmPI | 78,952229 s | 30,822640 s | 60,9604% | 2,59652 pp |

Todos os pares tiveram sinal positivo e amplitude inferior a dez pontos percentuais. O critério prévio não exigia pares extras; eles não foram executados para perseguir resultado.

| API | T4 A | T4 B | Redução descritiva | Previsão / confirmação |
| --- | ---: | ---: | ---: | --- |
| Clínica Piloto | 619,491791 s | 312,545142 s | 49,5481% | Indisponível; B ocorreu antes do congelamento por erro de filtro. Sem previsão prospectiva válida. |
| VAmPI | 133,769327 s | 51,584607 s | 61,4376% | Previsão vazia congelada antes de B, por inventário incompleto de regras. Nenhum número confirmado. |

Na T4 executaram-se 28/28 entradas planejadas da Clínica e 10/10 do VAmPI, após exclusões anteriores ao plano. Em cada operação, 43 regras ficaram `completed` e DOM XSS 40026 ficou `skipped`: Clínica 1.204/28 e VAmPI 430/10 regras concluídas/puladas por execução. Progresso 100% não elimina a lacuna. As quatro saídas reais de relatório exibiram **RELATÓRIO PARCIAL**.

O estimador pré-registrado não foi alterado para contornar dados ausentes. O [congelamento](../../../evals/measurements/v1.7/forecast-freeze.json), às 07:19:58 UTC, conserva previsão vazia e o desvio: `-k A-` também casou com `clinica-piloto`, incluindo B da Clínica. B VAmPI foi selecionado depois pelo node ID exato. O guia agora usa IDs completos em dois blocos, com congelamento entre eles. Ausência de previsão não significa ganho previsto de zero.

## 3. Qualidade — cada critério eliminatório

As células abaixo se referem a A/B quando explicitado. Os controles adicionais de autorização, CORS, valores proibidos e fast usam **legacy/A**; não são prova de B. A [matriz detalhada](../../../evals/measurements/v1.7/quality-evidence.md) discrimina as oito combinações API × modo × variante e os hashes.

| Critério | Clínica vulnerável | Clínica segura | VAmPI vulnerável | VAmPI seguro |
| --- | --- | --- | --- | --- |
| Autorização | Parcial: timestamps registrados válidos; pico observado dentro do teto; caminhos crus não inteiramente reconstruíveis. | Mesmos limites de interpretação nos controles A/B. | Parcial, mesmas restrições de auditoria. | Parcial nos controles A/B. |
| Cobertura planejada | Matrizes T1 e políticas/contas/operações T3/T4 A/B coincidem nos campos aferidos; faltam prova integral de payloads e pontos de entrada. | SQL e travessia A/B direcionados, sem completa segura. | Equivalência dos campos aferidos, com estratos omitidos. | SQL A/B de uma operação, demais classes não cobertas. |
| Cobertura executada | Parcial: DOM 40026 pulada, mutação excluída e recusas contadas. | Regra SQL/caminho concluída; DOM pulada. | Parcial: DOM pulada e mutações excluídas. | Regra SQL concluída; DOM pulada. |
| Detecção | SQL e travessia A/B preservados; A adicional achou horizontal, massa e CORS. B não repete todos esses controles. | SQL/travessia ausentes A/B; autorização/CORS A sem achados correspondentes. | SQL A/B; A adicional achou horizontal em livro. Massa V4 e par novo continuam não comprovados. | SQL ausente A/B; controles A de autorização sem achados. CORS zero observado, sem assert geral de ausência no VAmPI. |
| Falsos positivos | Sem avaliação universal; assinaturas e atribuições observadas são separadas de veredito. | Ausência nos controles selecionados não prova modo inteiro limpo. | Sem avaliação universal e sem todos os controles B. | Mesma limitação; os nove aceites de tipo proibido por modo em A exigem triagem. |
| Estado e identidade | Aliases e contagens aferidos; T4 teve autorização em 17.954/17.954 mensagens e XSRF em 5.036/5.036 escritas, sem rejeição CSRF observada. Isso não comprova identidade/dono por pedido. | Controles dirigidos, sem prova de estado integral da API. | T4 teve autorização em 4.272/4.272 mensagens; um evento de login adicional em A. Não prova troca nem igualdade integral de identidade. | Sem prova integral de titularidade e estado. |

Nas 47.931 linhas `allow` auditadas dos 28 registros, a validade da autorização e a janela estavam abertas. A reconstrução offline confirmou 42.903 caminhos normalizados e não pôde confirmar 5.028, por perda da representação crua e dos valores de query: isso não prova nem violação nem conformidade dessas linhas. Nos 16 scans T3/T4, o pico por segundo registrado ficou entre 28 e 48, até 50; nenhum intervalo entre liberações foi inferior a 19 ms, com tolerância de 1 ms para o timestamp. Não se prova tráfego sem linha ou ausência de ajuste do relógio.

Recusas `rate_backoff`, regras puladas e desconhecidas não foram contadas como execução. Os quatro ledgers T4 confirmam contêineres vazios antes, serviços esperados depois da subida, `down` bem-sucedido e vazio ao fim. Não provam semeadura; não existem retroativamente para T3. Os resets anteriores usavam recriação de contêineres, mas a prova individual é mais limitada.

## 4. Fração paralelizável e V1.10

O cálculo conserva sobreposição: por operação serial, a união dos intervalos das seis regras temporais pré-registradas é pelo menos a maior de suas durações. Sob relógios consistentes, execução serial sem sobreposição e exclusividade integral desses intervalos, obtém-se apenas o limite superior `1 - soma(dos máximos temporais) / parede do scan`; o limite inferior é zero.

| API | A | B |
| --- | --- | --- |
| Clínica | 0–87,06% | 0–82,79% |
| VAmPI | 0–91,02% | 0–90,36% |

São limites condicionais do trabalho executado, não estimativa nem intervalo de confiança. Não classificam mutações, dependências, outras exclusividades ou trabalho omitido. **Não comprovam pelo menos 40% paralelizável; a condição para iniciar V1.10 permanece não demonstrada.** Fórmula, fonte primária ZAP 2.17 e hashes: [parallelizability-bound.json](../../../evals/measurements/v1.7/parallelizability-bound.json).

## 5. Decisões, incidentes e pendências

- Teto fechado replanejado para quatro horas antes da primeira prova, sem aumentar limites: 50 pedidos/s, oito threads e 30 minutos dos perfis existentes. O controle fast 5/2 ficou separado do benchmark.
- Reserva do coordenador iniciada às 05:01:48 UTC; após `hdast stack down` e Compose vazio, a própria trava foi removida para o validador. Ele adquiriu outra exclusivamente e preservou o prazo global 09:01:48 UTC; terminou, confirmou vazio e removeu só a sua. Nenhuma trava alheia foi apagada.
- Somente comandos `hdast` e suporte de testes no laboratório, com cópias descartáveis aprovadas pelo suporte. Nenhum comando manual de aprovação, limpeza ou gravação de segredo; nenhum `.env` ou cofre foi lido pelo agente.
- Uma T2 inicial falhou antes do scan após 429 e timeout. Reprodução sintética com `Retry-After: 58` demonstrou incompatibilidade entre reter a conexão e o timeout do cliente; o valor remoto real não foi registrado. A causalidade exata do episódio é inferência. O proxy passou a recusar imediatamente durante o recuo, sem repetir mutações ou reduzir o recuo.
- Um preparo T3 VAmPI retornou 500 em `/createdb`, antes do scan, com causa desconhecida. A tentativa e sua duração foram preservadas; houve uma repetição em pilha nova.
- O primeiro bloco de controles complementares terminou 11/1 em 1.277,71 s: um assert confundia qualquer recusa com escopo. A correção aceita só `deny/rate_backoff/429` correlacionado um a um com decisão permitida e resultado 429 da CLI, mesmo método/origem/caminho/query e janela. Os 13 testes negativos da correlação preservam rejeição dos demais casos. O reteste separado passou 18/18 em 859,16 s; fast passou 6/6 em 319,28 s. Sete casos por orçamento e dois `wrong_type` inconclusivos por modo continuam lacunas.
- O fechamento encontrou quatro expectativas antigas de relatório e depois uma de HTML. Foram corrigidas com 259 testes dos módulos de relatório e 444 de contrato. Também se corrigiu texto que atribuía parada a qualquer parcial e classificava toda recusa como escopo. O código de tráfego medido não mudou; os relatórios originais das provas foram preservados.

Para aceite integral, faltam investigar a regra 40026, completar os controles/atribuição ausentes e executar nova prova prospectiva com orçamento e pré-registro próprios. Alternativas pendentes do dono: corrigir e repetir a prova (recomendação), ou encerrar esta entrega como parcial com A padrão e aceite da aceleração pendente. Não ativar B por padrão nem exclusões por tecnologia com os dados atuais.

## 6. Gates e integração

Commit do candidato de código/testes verificado: **44f45df**. Gates finais locais: Ruff check e format, mypy Windows e Linux, seis contratos de importação, vulture e pytest: **9.604 passaram, 4 pulados, 211 desmarcados, 328,64 s**. Pisos e cobertura diferencial: **domínio 98,4311% (piso 95%), aplicação 96,7813% (piso 85%); diferencial 294/297 = 98,9899% (piso 90%)**. `gitleaks` sem afrouxamento: zero achados; `pip-audit` sobre dependências travadas: zero vulnerabilidades conhecidas. Resultados e hashes ficam em [gates-final.json](../../../evals/measurements/v1.7/gates-final.json); as duas execuções anteriores com falhas permanecem nos logs externos.

As alterações foram juntadas serialmente na feature, sem merge em `develop`. Todas as worktrees e branches auxiliares desta execução foram removidas após integração e conferência de limpeza; artefatos externos foram preservados. A publicação será por push da feature e PR rascunho para `develop`, sem merge. O estado remoto do CI é conferido na entrega; gates locais não são apresentados como execução do GitHub.

## 7. Subagentes e modelos

| Papel | Modelo e esforço | Isolamento |
| --- | --- | --- |
| Crítico inicial novo | GPT 6.1 Terra medium | Worktree própria, sem herdar a conversa |
| Proxy, motor e tecnologia | GPT 6.1 Terra high, até três programadores simultâneos | Arquivos e worktrees próprios |
| Correções de recuo, lacunas e orientações | GPT 6.1 Terra high | Worktrees próprias, integração pela coordenação |
| QA independente e correção de expectativas | GPT 6.1 Terra high | Worktrees próprias, sem Docker pelos autores de código |
| Documentação | GPT 6.1 Terra high | Worktree própria e blocos V1.7 nos documentos compartilhados |
| Validador final novo | GPT 6.1 Terra medium | Worktree e evidência próprias, sem implementar; dois controles escolhidos reproduzidos |

Índice dos dados e método: [evals/measurements/v1.7](../../../evals/measurements/v1.7/README.md). Originais sanitizados e logs: `C:\harness-dast-artefatos\v1.7-velocidade`.

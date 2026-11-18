# Validação independente da V1.7

Data: 2026-11-16. Validador novo, GPT 6.1 Terra medium, sem participação na implementação, em worktree própria. Decisão: **corrigir** para o aceite integral da V1.7; a entrega parcial pode seguir para revisão humana com ritmo `legacy` como padrão. A execução não demonstrou equivalência integral nem confirma o ganho previsto para a varredura completa. Este parecer não substitui a revisão humana do `CONTRIBUTING.md`.

## Revisão e controles reproduzidos

Revisei o diff integrado em relação a `origin/develop`, os ADRs 0066–0069, o plano e suas seções 12.1 e 12.2, testes e artefatos. Executei 49 testes dirigidos sem Docker para fila, limitador, matriz de ritmo, Retry-After, tecnologia e análise: passaram. No laboratório exclusivo, executei os dois node IDs exatos de `test_v17_t2_sql` da Clínica, variante B, modos vulnerável e seguro: **2 passaram em 281,64 s**. Os testes reconstruíram a pilha e a desmontaram; `docker compose ls -a` retornou lista vazia antes de eu liberar minha trava. A regra SQL 40018 e a operação terminaram; SQL Injection apareceu no vulnerável e não no controle seguro. Os artefatos redigidos estão em `C:\harness-dast-artefatos\v1.7-velocidade\validator-t2`.

O monitor teve uma amostra ociosa e nenhuma com scan ativo em cada caso; portanto B foi configurada, mas seu atraso aplicado não foi diretamente observado na minha reprodução. Cada scan teve uma lacuna de regra. Não extrapolo esses dois controles para outras classes ou para cobertura completa.

## Evidências integradas e decisão

A matriz [de qualidade](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1.7/quality-evidence.md) relata 12 controles SQL e travessia A/B em modos vulnerável e seguro aprovados, mais controles existentes de autorização, CORS e valores proibidos em A. O teste negativo original falhou ao exigir ausência de toda recusa; a reexecução separada passou 18 testes, preservando lacunas de orçamento, resultados inconclusivos e nove aceites de tipos proibidos a triar por modo. A tentativa original não desaparece com a correção do teste.

Nos três pares T3, a mediana descritiva de redução foi 45,10% na Clínica e 60,96% no VAmPI, em subconjuntos de nove e seis operações executadas, respectivamente. Essas são observações, não ganho aceito: operações de mutação foram puladas, a regra 40026 ficou `skipped` e há limites de identidade, pontos de injeção e auditoria. A leitura de atraso no ZAP é pontual, não demonstra o valor continuamente. Uma tentativa T3 VAmPI falhou no preparo com HTTP 500 antes do scan; foi repetida e mantida como falha separada, sem tempo zero imputado.

As T4 vulneráveis A/B duraram 619,49/312,55 s na Clínica e 133,77/51,58 s no VAmPI. O congelamento contém previsão vazia, pois 40026 estava pulada. Na Clínica, B foi executada antes do congelamento por seleção acidental de teste; não existe previsão prospectiva válida. Consequentemente, nenhuma T4 confirma uma previsão numérica dentro do critério de dez pontos percentuais. Os [dados e o congelamento](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1.7/forecast-freeze.json) preservam o desvio.

A auditoria coletada não comprova concessões sem linha ou caminhos brutos perdidos na normalização. Cabeçalhos de autorização e aliases observados não comprovam identidade e titularidade em cada pedido. Houve 429 e timeout antes do primeiro scan; uma reprodução sintética com Retry-After de 58 segundos demonstrou incompatibilidade, mas o Retry-After real não foi registrado e a causa exata do timeout permanece inferência. A correção e os testes subsequentes são evidência limitada, não prova de recuperação individual de toda regra. As tecnologias são consultivas e não excluem regras. `legacy` permanece padrão; o atraso efetivo do ZAP não é medido continuamente. Sem comprovar os critérios de qualidade e previsão, a meta de desempenho não foi aceita e não se recomenda promover B a padrão.

## Condição de entrada da V1.10

Conferi os quatro registros T4: IDs e operações correspondem, as seis regras temporais selecionadas estão concluídas em cada operação e seus tempos não excedem a duração da entrada. Para cada operação somei o máximo dos tempos das regras 40019, 40020, 40021, 40022, 40027 e 90036, sem somar tempos sobrepostos. O [ZAP 2.17](https://github.com/zaproxy/zaproxy/blob/v2.17.0/zap/src/main/java/org/zaproxy/zap/extension/ascan/ActiveScanAPI.java#L936-L954) calcula o tempo da regra concluída pela diferença entre seus instantes de término e início. Sob as hipóteses de operações seriais sem sobreposição, relógios consistentes e exclusividade integral dos intervalos dessas regras, os intervalos conservadores da fração paralelizável do trabalho **observado** são:

| API | A | B |
| --- | --- | --- |
| Clínica | 0–87,06% | 0–82,79% |
| VAmPI | 0–91,02% | 0–90,36% |

São limites superiores condicionais, não estimativas nem intervalos de confiança. Não classificam trabalho omitido, mutações ou dependências desconhecidas; não demonstram pelo menos 40% paralelizável. A condição para iniciar V1.10 permanece não comprovada. Método e hashes estão em [parallelizability-bound.json](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1.7/parallelizability-bound.json).

## Gates finais

No commit `44f45df`, o coordenador informou: `ruff check`, `ruff format --check`, mypy Windows e Linux, `lint-imports` e `vulture` aprovados; suíte completa com **9.604 passaram, 4 pulados e 211 desmarcados**, em 328,64 s. Cobertura: domínio 98,4% (piso 95%), aplicação 96,8% (piso 85%) e diff 294/297 linhas, 98,99% (piso 90%). Gitleaks não encontrou segredos nos 68 commits examinados e `pip-audit` não encontrou vulnerabilidades conhecidas nas dependências travadas. Logs dos gates estão nos artefatos externos. As duas tentativas anteriores da suíte falharam em expectativas e texto de relatório; foram corrigidas antes desta rodada. Esses resultados foram comunicados pelo coordenador, não repetidos por mim.



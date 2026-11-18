# QA independente V1.7 — parecer estático anterior ao laboratório

Data: 2026-11-16. Este registro descreve o estado antes de qualquer prova de laboratório desta entrega. Não é parecer final e não aprova ativar o ritmo B. A pilha compartilhada estava ocupada pela V1.8 quando este documento foi escrito; o coordenador fará as provas posteriormente e registrará o resultado em documento complementar.

## Escopo e resultado

O QA preparou amostra T3 fixa de dez operações da Clínica e sete do VAmPI por mecanismo, com contas e dependências esperadas em [`preregistro.md`](../../evals/measurements/v1.7/preregistro.md). A amostra não cobre todos os estratos: atualização de senha foi retirada antes de medir para não destruir a identidade no decorrer da execução; multipart, DELETE e login não são cobertos pelo T3. A [matriz de controles](../../evals/measurements/v1.7/matriz-controles.md) registra os controles ausentes ou não demonstrados, incluindo V4 de atribuição em massa no VAmPI, e não transforma ausência de achado em detecção equivalente.

O teste T2 SQL exige operação e regra 40018 concluídas antes de avaliar o achado; uma regra indisponível, `pending` ou interrompida é lacuna de prova, não necessariamente defeito de segurança. O teste de desempenho usa cópias temporárias aprovadas pelo suporte de integração, alterna A/B e reinicia a pilha entre cenários. A análise de regras e contas retorna inconclusivo enquanto pontos de injeção, controles, autorização, limites e atribuição não forem aferidos por evidência. O estimador ponderado por regra exige dados completos e não iguala soma de tempos das regras a tempo de parede. Seu resultado precisa ser congelado antes de T4 B.

## Testes sem Docker

- `tests/unit/domain/test_limits_v17_qa.py` e `tests/unit/evals/test_performance_v17_qa.py`: **19 passaram**; cobrem entradas inválidas de `Retry-After`, teto, recuo já imposto, política consultiva de tecnologia, fingerprint e estimador conservador.
- `tests/unit/adapters/test_scan_process_v17_qa.py` e `tests/unit/adapters/scope_proxy/test_schedule_v17_qa.py`: **6 passaram**; incluem pico de memória do processo Windows real, CPU não negativa, conversão Linux/macOS com recurso injetado, recurso ausente e atraso de escalonamento sem rajada.
- O isolamento de integração foi verificado com teste temporário: somente as variáveis de prazo e diretório de medição foram restauradas e uma terceira variável `HDAST_*` permaneceu removida. Ruff dos arquivos alterados passou; mypy completo Windows e Linux passou antes da inclusão dos últimos testes, e mypy direcionado deles passou.

O sampler de processo mede **a CLI**, não a CPU do ZAP ou proxy. A coleta de memória dos contêineres não substitui CPU dos demais processos. Não há linha do tempo suficiente para concluir a fração paralelizável: sem evidência adicional, o intervalo conservador é de 0% a 100%, insuficiente para decidir o limiar de 40%.

## Pendências eliminatórias

Não houve T2, T3 ou T4 nesta worktree, nem comparação A/B real, conferência de limite pela auditoria do proxy reconstruído, medição por regra, verificação das contas no alvo ou comprovação de detecção por API e modo. A referência V1.5.5 não tem completas comparáveis nem rodada cega: a T4 A desta entrega, se concluída, é referência experimental e não substitui uma referência cega. A previsão, o ganho de 15%, a divergência de 10 pontos percentuais e a qualidade da seção 3 do plano permanecem **inconclusivos**.

O teto global foi replanejado para quatro horas antes da primeira prova, incluindo reinícios e builds. Após o primeiro par por API, deve-se projetar o custo restante e parar se não couber, sem reduzir força, regras ou limites. T4 A deve anteceder a previsão congelada e T4 B. A ausência de prova exige manter A como padrão. Tecnologia segue apenas consultiva, sem exclusão de regras.

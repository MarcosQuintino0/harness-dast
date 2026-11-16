# Ensaio sintético do canal de reuso — 2026-11-16

Teste offline T1: `tests/unit/evals/test_reuse.py::test_synthetic_dry_run_real_case_export`
cria um lacre e uma coleta **fictícios**, com conhecimento sintético idêntico, para
cada caso versionado da Clínica Piloto e do VAmPI. A exportação e a verificação
retornaram o produto correto nos dois casos. Nenhuma pilha, agente, alvo, rodada
cega, varredura ou coleta real foi executada. O modelo de conhecimento usado no teste
foi carregado da worktree de desenvolvimento correspondente, ainda em integração.
Na execução local dirigida, 35 testes passaram e o teste de link simbólico foi
ignorado porque a conta do Windows não pôde criar o link; o teste de hardlink passou.

O ensaio também compara os vínculos sintéticos às fontes sintéticas da origem. Não demonstra
validade das fontes do segundo contexto, motor, alcance, detecção, economia ou reuso real. Esses resultados
dependem de implementação integrada e do estudo futuro em contextos novos.

# Política de limpeza do ambiente de testes

A limpeza é a única ação destrutiva intencional do harness: exige autoria e revisão humanas do SQL,
autorização registrada e dados sintéticos. Só Oracle e `DELETE`. O agente não escreve, altera ou executa o script,
nem amplia `allowed_tables` ou `max_rows` (Parte B do `AGENTS.md`); apenas sugere a limpeza à pessoa.

A pessoa confere DSN, privilégios mínimos (`SELECT` e `DELETE` nas tabelas de teste), contagens e teto antes de
confirmar digitando o nome do produto em terminal interativo. Nenhum atalho, CI ou tarefa agendada substitui o aceite.
O portão SQL é defesa em profundidade: não verifica privilégios, gatilhos, cascatas ou semântica da amarração.
O pseudoterminal é um limite conhecido: regras do agente e usuário restrito completam a proteção.

- Procedimento humano, preparação e diagnóstico: [guia de limpeza](../guides/limpeza-de-dados.md).
- Contrato técnico, transação, portão, variáveis, artefatos e saídas: [referência de limpeza](../reference/cleanup.md).
- Decisões: [ADR 0020](../adr/0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md) e [ADR 0025](../adr/0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md).

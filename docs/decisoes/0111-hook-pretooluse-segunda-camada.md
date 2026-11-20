# 0111. Hook PreToolUse como segunda camada para o agente

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** Pacote 2.4

## Contexto

As regras de permissão do Claude Code em `.claude/settings.json` comparam padrões de texto. Um executável chamado pelo caminho absoluto, um comando dentro de `sh -c` ou código Python inline podem escapar desses padrões. Esses casos abrem caminhos para executar ações reservadas a pessoas, acessar a rede fora da CLI, consultar segredos e alterar arquivos de controle.

## Decisão

Vamos preservar as negações da camada 0 e acrescentar um hook `PreToolUse` que recebe a chamada em JSON e verifica os argumentos das ferramentas de shell e de arquivos. O hook complementa as permissões, a CLI, a Parte B de `AGENTS.md` e o isolamento de rede.

- No shell, o hook normaliza aspas, separadores, nomes de executáveis e prefixos como `uv run` e `python -m harness_dast`. Ele barra `profile approve`, `secret set`, `secret delete`, `finding acknowledge`, `mutation release` e `cleanup`, inclusive `--dry-run`. Também barra os clientes de rede e as formas de código inline enumerados no script.
- O hook barra a leitura de `.env`, `.env.*` e `hdast/stack.json`, exceto `.env.example`. Verifica seletores explícitos de arquivo em `Glob` e `Grep` e formas comuns de listar o ambiente pelo shell.
- O hook barra alterações em qualquer segmento `approvals/`, `human-confirmations.json`, `.claude/settings.json`, `.claude/hooks/` e `.mcp.json`. A camada 0 ganha negações de `Edit` e `Write` para as configurações e o diretório do hook. As skills e os agentes continuam editáveis.

O comando é `uv run --no-project --quiet python "${CLAUDE_PROJECT_DIR}/.claude/hooks/guard.py"`. O Claude Code substitui o marcador `${CLAUDE_PROJECT_DIR}` pela raiz do projeto antes de executar o comando, inclusive após mudança de diretório. A forma é a mesma em Windows e Linux. `--no-project` evita sincronizar as dependências do projeto a cada chamada. O script usa a biblioteca padrão do Python 3.12 e valida manualmente os dados recebidos. Esta é uma exceção à regra de modelo pydantic na entrada do `AGENTS.md`, pois o hook precisa funcionar sem depender do ambiente e das dependências instaladas do projeto.

O código devolve `0` para liberar. Ação barrada, entrada inválida ou exceção durante o processamento devolvem `2`, com uma orientação curta no stderr e sem reproduzir o conteúdo recebido.

## Alternativas consideradas

- Ampliar somente a lista de permissões repetiria padrões por shell, prefixo e variante de aspas, com lacunas a cada nova grafia.
- Confiar somente na CLI deixaria sem esta verificação as chamadas a outros executáveis e ferramentas de arquivo do agente.

## Consequências

O Claude Code v2.1.295 ou posterior é necessário para `onFailure: block`, que bloqueia falhas do lançador, saídas inesperadas e tempo esgotado. O `timeout` é de 30 segundos. O uso pressupõe `uv` no PATH e Python disponível.

Os aceites são testes de unidade com entradas sintéticas para cada regra, variações de sintaxe, chamadas permitidas e falhas fechadas. O teste de contrato preserva as negações anteriores e confere o registro do hook.

## Limite residual

A análise é estática e textual. Variáveis, aliases, scripts gravados em disco e programas próprios podem escapar da inspeção. A barreira física contra tráfego direto ao alvo é o isolamento de rede da pilha. No laboratório, o alvo só é alcançável pelo proxy de escopo.

A validação manual sem pydantic é uma exceção deliberada à regra de entrada do `AGENTS.md`. O hook executa somente com a biblioteca padrão, sem depender das bibliotecas instaladas no ambiente do projeto.

## Lista de escrita na pasta de produtos

O hook identifica o clone pelo nome `harness-dast` em `[project]` no `pyproject.toml` e pela pasta `src/harness_dast/`. Ele consulta `CLAUDE_PROJECT_DIR` e usa o diretório atual quando essa variável está ausente. Fora do clone, as ferramentas de edição e as gravações verificáveis pelo shell só podem usar caminhos literais que permaneçam em `products/`, `runs/` ou `cartas/` após a resolução de links. Os três nomes exigem a grafia exata, inclusive no Windows. Em ambos os modos, o hook protege o cache e os dados do plugin e o diretório de estado do hdast. [ADR 0119](0119-hdast-como-plugin-do-claude-code.md)

Na pasta de produtos, a análise de shell aceita um conjunto explícito de comandos e argumentos. Ela bloqueia destinos dinâmicos, instalação de pacotes, operações do Git que alteram metadados e chamadas MCP sem contrato verificável. Os instaladores podem escrever em caches, diretórios temporários ou executar código transitivo. A operação de shell para gravar um diff de dois caminhos tem saída explícita. Código inline fica limitado às formas de leitura previstas pelo analisador.

O hook pressupõe executáveis e perfis de shell confiáveis. A verificação de caminhos é feita antes da execução. Uma troca concorrente de arquivos, links ou montagens pode mudar o destino depois dessa verificação. Permissões do sistema operacional e isolamento de rede continuam necessários nos respectivos limites.

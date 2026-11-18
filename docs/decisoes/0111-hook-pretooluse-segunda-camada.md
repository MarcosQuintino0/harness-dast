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
- O hook barra alterações em `hdast/approvals/`, `human-confirmations.json`, `.claude/settings.json`, `.claude/hooks/` e `.mcp.json`. A camada 0 ganha negações de `Edit` e `Write` para as configurações e o diretório do hook. As skills e os agentes continuam editáveis.

O comando é `uv run --no-project --quiet python "$CLAUDE_PROJECT_DIR/.claude/hooks/guard.py"`. A variável `CLAUDE_PROJECT_DIR`, que o Claude Code define para os hooks, ancora o script na raiz do projeto mesmo se o agente mudar de pasta; um caminho relativo quebraria nesse caso, e o lançador sairia com código diferente de 2, deixando a chamada passar. A forma é a mesma em Windows e Linux, sem depender da localização do executável dentro de uma `.venv`. `--no-project` evita sincronizar as dependências do projeto a cada chamada e `--quiet` reduz a saída do lançador. O script usa só a biblioteca padrão do Python 3.12.

O código devolve `0` para liberar. Ação barrada, entrada inválida ou exceção durante o processamento devolvem `2`, com uma orientação curta no stderr e sem reproduzir o conteúdo recebido.

## Alternativas consideradas

- Ampliar somente a lista de permissões repetiria padrões por shell, prefixo e variante de aspas, com lacunas a cada nova grafia.
- Confiar somente na CLI deixaria sem esta verificação as chamadas a outros executáveis e ferramentas de arquivo do agente.

## Consequências

O hook é uma inspeção estática de formas conhecidas. Aliases, expansões, links simbólicos e arquivos apontados apenas indiretamente ficam fora da análise. Um script chamado pelo nome, que monta o endereço em tempo de execução, ainda pode escapar da inspeção. A barreira física contra acesso direto ao alvo é o isolamento de rede.

O código de bloqueio depende de o Python iniciar o script. Se o lançador falhar antes disso com código diferente de `2`, o Claude Code trata a falha como erro sem bloqueio. A configuração pressupõe `uv` no PATH, Python disponível e Claude Code aberto na raiz do repositório.

Os aceites são testes de unidade com entradas sintéticas para cada regra, variações de sintaxe, chamadas permitidas e falhas fechadas. O teste de contrato preserva as negações anteriores e confere o registro do hook.

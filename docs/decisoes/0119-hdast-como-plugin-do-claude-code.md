# 0119. O hdast é distribuído como plugin do Claude Code, publicado por tag

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** pergunta do dono durante a reestruturação: o agente que testa um produto pode editar a ferramenta? Como levar o código-fonte inteiro para o GitLab da empresa sem que alguém estrague o que importa? Substitui a versão anterior deste ADR, que propunha um manifesto de integridade e nunca foi aceita.

## Contexto

Hoje a mesma pasta serve para desenvolver a ferramenta e para testar produtos:

- **Os perfis** ficam em `products/<produto>/`, dentro do clone, ou na pasta de `HDAST_PRODUCTS_DIR`.
- **A aprovação** fica fora do clone e guarda a impressão digital dos blocos de proteção ([ADR 0037](0037-aprovacao-humana-do-escopo.md)). O perfil já está protegido.
- **O guard e o `settings.json`** barram uma lista de caminhos ([ADR 0111](0111-hook-pretooluse-segunda-camada.md)). O agente que testa ainda alcança `src/`, `docker/`, `compose.yaml` e as skills.
- **O build local.** O `stack up` usa as imagens publicadas ([ADR 0113](0113-imagens-publicadas-e-conferencia-de-versao.md)), mas `--build` e `HDAST_STACK_BUILD=1` constroem a cerca a partir do clone. Na rodada cega de 2026-11-18, o agente avaliado ligou `HDAST_STACK_BUILD=1` sozinho quando o `stack pull` falhou.

O dono quer:
- levar o código-fonte inteiro para o GitLab da empresa, para outros QAs evoluírem a ferramenta;
- que quem só testa não precise clonar nada;
- que o agente que testa não consiga mexer na ferramenta;
- que uma versão nova saia subindo uma tag.

O Claude Code tem um mecanismo próprio para isso, os plugins. Conferido na documentação oficial em 2026-11-18:
- **O que um plugin leva:** skills, subagentes, comandos e hooks, inclusive `PreToolUse` e `SessionStart`.
- **Onde ele fica:** no cache do Claude Code (`~/.claude/plugins/`), fora da pasta do usuário. O hook usa `${CLAUDE_PLUGIN_ROOT}` para achar os arquivos do plugin, e `${CLAUDE_PLUGIN_DATA}` é uma pasta de dados que sobrevive às atualizações.
- **O marketplace** pode morar num GitLab próprio, pela URL do repositório. A entrada do plugin aceita `ref` e `sha`, e a origem `git-subdir` aponta para uma pasta dentro do repositório.
- **A configuração gerenciada** da organização registra o marketplace (`extraKnownMarketplaces`), liga o plugin (`enabledPlugins`) e restringe os marketplaces aceitos (`strictKnownMarketplaces`).
- **Para desenvolver**, `claude --plugin-dir <pasta>` carrega um plugin local.
- **O que o manifesto não traz:** regras de permissão `allow`/`deny`. O guard faz esse papel, como já faz hoje.

## Decisão

Vamos distribuir o hdast como **plugin do Claude Code**, com o motor (CLI e imagens) publicado pela mesma tag.

### 1. Duas pessoas, dois lugares

| Quem | Onde trabalha | O que tem |
|---|---|---|
| **QA que testa** | Numa pasta de produtos, com o plugin instalado | `products/`, `runs/` e `cartas/`. Não clona a ferramenta. |
| **QA que melhora** | No clone do repositório da ferramenta | Código, laboratório, CI, skills `dev-*` e `claude --plugin-dir plugin/` para provar o plugin |

### 2. O plugin, na pasta `plugin/` do repositório
- `.claude-plugin/plugin.json`, com nome `hdast` e versão igual à do `pyproject.toml`.
- As cinco skills de uso e os subagentes `spec-analyst` e `findings-triager`. A fonte única passa a ser `plugin/`; o repositório as carrega pelo `--plugin-dir`, sem cópia.
- **Hook `PreToolUse`: o guard.**
  - O lançador falha fechado (`onFailure: block`).
  - Na pasta de produtos, ele trabalha por lista permitida: o agente escreve só em `products/`, `runs/` e `cartas/`.
  - Continua barrando os comandos humanos, o HTTP direto ao alvo e a leitura de segredo.
  - Barra a escrita no cache e nos dados do plugin e na pasta de estado do hdast.
- **Hook `SessionStart`: um script de shell, sem Python.** Ele só confere e avisa. Confere três coisas:
  - se há `uv`;
  - se a CLI instalada tem a versão do plugin;
  - se o Docker está aberto e as imagens existem.

  Ele nunca instala nada.
- **Skill `/hdast:preparar`.**
  - Diagnostica a máquina e propõe cada instalação com o comando exato e de fonte fixa:
    - `winget install astral-sh.uv`;
    - `winget install Docker.DockerDesktop`;
    - a CLI da versão do plugin;
    - `hdast stack pull`.
  - Executa só o que a pessoa aprovar e termina com o `hdast doctor` verde.
  - Elevação de administrador, reinício e licença do Docker Desktop são da pessoa ou da TI.
  - Se faltar o `uv`, o guard bloqueia tudo, então a skill orienta a pessoa a rodar a instalação do `uv` no terminal dela.

### 3. O motor sai da mesma tag
- **A CI da tag faz quatro passos, nesta ordem:**
  1. publica as imagens;
  2. lê os digests;
  3. grava os digests num arquivo dentro do pacote da CLI;
  4. publica o pacote: no GitHub, como anexo da release; no GitLab, no registro de pacotes.
- **O `stack up` da CLI instalada** sobe as imagens por `tag@sha256` e não tem a pasta `docker/`.
- **`--build` e `HDAST_STACK_BUILD=1` são recusados fora de um clone de desenvolvimento.** Um clone se reconhece pela presença de `docker/` e `pyproject.toml` do projeto. O agente que testa não tem como construir uma cerca.
- **Versões:** `plugin.json`, `pyproject.toml` e a tag precisam bater. Um teste de contrato confere, e a CI da tag recusa se não baterem.

### 4. O marketplace
- `.claude-plugin/marketplace.json` na raiz do repositório, com o plugin `hdast` em origem `git-subdir` (`plugin/`), `ref` igual à tag e `sha`.
- Depois da tag, a CI abre a mudança que aponta o marketplace para a tag nova. A `main` só recebe essa mudança por revisão.
- Na empresa, a TI registra o marketplace e liga o plugin pela configuração gerenciada. A versão vale para todos, e a TI pode segurar uma versão ruim.

### 5. Proteção do repositório na empresa
- `main` protegida, com merge request e CI verde.
- Tags protegidas.
- `CODEOWNERS` cobrindo o núcleo de segurança: cerca, escopo, aprovação, impressão digital, carta, guard, hooks do plugin e `plugin.json`.

### 6. Fora desta decisão
- **A pipeline por produto e onde a aprovação fica para a pipeline ler.** Terão ADR próprio. Até lá, repetir é pedir ao Claude ou rodar `hdast run` no terminal.
- **A conversão da CI do GitHub Actions para o GitLab CI.** Fica no guia de importação, feito quando a importação acontecer.
- **Um executável único da CLI**, sem `uv`. Fica para depois, se o uso pedir.

## Alternativas consideradas

- **Manifesto de integridade e trava `TOOL_MODIFIED`** (versão anterior deste ADR). Uma conferência que roda no próprio código pode ser desligada por quem edita o código. Com o plugin, o agente nem tem o código na pasta, e o build da cerca deixa de existir fora do clone.
- **Repositório de produtos separado, com a ferramenta instalada por `uv` e o guard copiado nele.** Funciona, mas o guard e as skills viveriam em cópias por time, sem atualização central. O plugin atualiza tudo pela tag.
- **Distribuir só o pacote e as imagens, sem o código.** Impede a empresa de evoluir a ferramenta.
- **Juntar a imagem do ZAP e a da cerca.** A cerca depende de estarem em contêineres e redes separadas, e o ZAP grande mudaria a cada ajuste da cerca. Ficam separadas.

## Consequências

- Quem testa só precisa de Claude Code, Git (que já vem com ele no Windows), `uv` e Docker, este aberto durante o teste. Python avulso não é preciso, porque o `uv` traz o Python que a CLI pede.
- O agente que testa não alcança o código da ferramenta. A brecha do build local fecha.
- As skills de uso mudam de lugar, de `.claude/skills/` para `plugin/skills/`. Mudam junto:
  - a cópia cega ([ADR 0083](0083-copia-cega-por-lista-de-permissao.md)), que passa a carregar o plugin de fora do workspace;
  - os testes de contrato das skills;
  - o `AGENTS.md`.
- O guard ganha um segundo modo, a lista permitida da pasta de produtos, e mantém o modo atual no clone.
- O Codex não lê o manifesto do plugin nem roda hooks. Quem operar com outro agente segue o `AGENTS.md`, sem o guard, como hoje.
- A licença do Docker Desktop em empresa grande e o bloqueio de `winget` em máquinas corporativas são da TI. A skill de preparo só diagnostica nesses casos.

## Plano em fases

| Fase | Entrega | Depende de |
|---|---|---|
| A | Imagens por `tag@sha256` e o arquivo de digests no pacote; build recusado fora do clone | Pedido mínimo (ADR 0120) na integração |
| B | Pacote da CLI publicado pela tag, com versão conferida | A |
| C | Pasta `plugin/`: manifesto, skills, subagentes, guard em lista permitida e lançador fechado | A |
| D | Hook `SessionStart` em shell e skill `/hdast:preparar` | B, C |
| E | `marketplace.json`, CI da tag e teste de versões | B, C |
| F | `CODEOWNERS`, configuração gerenciada de exemplo e guia de instalação para QA e TI | E |
| G | Cópia cega e rodada cega com o plugin numa pasta vazia, pelo pedido mínimo | D, E |

O detalhe de cada pacote, com o modelo do Codex e os aceites, fica no plano da reestruturação.

## Aceites verificáveis

- Numa pasta vazia com o plugin carregado, o agente não consegue escrever fora de `products/`, `runs/` e `cartas/`, por ferramenta de edição nem por shell. O guard tem testes para cada caso.
- Sem `uv` no PATH, toda chamada de ferramenta é bloqueada, e o `SessionStart` diz o que instalar.
- A CLI instalada pelo pacote recusa `--build` e `HDAST_STACK_BUILD=1`. No clone, os dois continuam funcionando.
- O `stack up` da CLI instalada sobe as imagens pelo digest gravado no pacote.
- Com versões diferentes entre `plugin.json`, `pyproject.toml` e a tag, o teste de contrato falha e a CI da tag recusa.
- `claude --plugin-dir plugin/` no clone carrega as cinco skills, os dois subagentes e os dois hooks.
- A rodada cega com o plugin numa pasta vazia chega ao relatório, sem requisição fora do escopo e sem escrita fora da lista permitida.

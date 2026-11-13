# Contribuindo

Este documento vale para pessoas e para agentes de IA. Regras resumidas para agentes estão em [CLAUDE.md](CLAUDE.md). A estratégia de testes está em [docs/testing.md](docs/testing.md).

Muitos itens abaixo são verificados por ferramenta no CI (`.github/workflows/ci.yml`) e no pre-commit. O estado de cada gate está em [docs/roadmap.md](docs/roadmap.md#gates-de-qualidade).

## Ambiente local

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest
```

Rode os cinco comandos antes de abrir um pull request. O CI roda também `uv run vulture` (detecta código sem uso); rode-o localmente se tocar em funções públicas. `uv run pytest` roda os testes unitários e de contrato; os níveis de integração e ponta a ponta pedem Docker e chegam em marcos posteriores.

Para os hooks locais (os mesmos gates, mais `gitleaks` e a checagem da mensagem de commit):

```bash
uv run pre-commit install --install-hooks
uv run pre-commit install --hook-type commit-msg
```

## Branches

Desenvolvimento baseado em tronco (trunk-based): a `main` é protegida e sempre liberável. Todo trabalho acontece em branches curtas, de vida de poucos dias, criadas a partir da `main`.

| Prefixo | Uso |
| --- | --- |
| `feat/` | Funcionalidade nova |
| `fix/` | Correção de defeito |
| `docs/` | Só documentação |
| `chore/` | Ferramentas, CI, manutenção |
| `spike/` | Experimento descartável para aprender algo |

Branches `spike/` **nunca** entram na `main`. O aprendizado vira ADR; o código do spike é descartado.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/) com o pacote como escopo:

```text
feat(zap): inicia varredura com plano validado
fix(scope): rejeita host com usuário embutido
docs(adr): registra decisão sobre o proxy de saída
```

Tipos usuais: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`. Escopos usuais: `domain`, `application`, `adapters`, `cli`, `config`, `observability`, e o nome do adaptador (`zap`, `openapi`, ...) quando couber. A verificação automática da mensagem é feita pelo commitizen no hook `commit-msg` do pre-commit (depois de instalado como acima).

## Pull requests

- Um pull request, um assunto.
- Acima de cerca de 400 linhas alteradas, divida.
- Merge por squash: o título do pull request vira a mensagem do commit, então escreva-o como Conventional Commit.
- Descreva o que mudou, por quê e como foi verificado. Cite o item do roadmap.

## Roteiro de revisão

O autor passa por esta lista antes de pedir revisão; o revisor passa por ela de novo.

1. A mudança respeita as camadas e não cria dependência nova sem ADR?
2. Há regra de negócio em adaptador ou na CLI?
3. Os testes validam comportamento e casos negativos, ou só exercitam linhas?
4. Toda entrada externa é validada na fronteira?
5. Algum segredo ou dado pessoal pode chegar a log, erro ou saída para o agente?
6. A mudança pode ampliar escopo, limites ou o que a limpeza apaga?
7. Nomes, tamanho de função e comentários seguem os padrões de [CLAUDE.md](CLAUDE.md)?
8. Documentação e contrato atualizados?

## Política de revisão para uma equipe de uma pessoa (AD-14)

- Todo pull request recebe **autorrevisão** pelo roteiro acima e **uma revisão por agente de IA**.
- Mudanças em **escopo, segredos, limpeza e permissões do agente** exigem também um **segundo par de olhos humano**, definido em `CODEOWNERS` (`.github/CODEOWNERS`).
- Revisão por IA encontra muita coisa, mas não substitui responsabilidade humana nos pontos que podem causar dano real ao ambiente da empresa.

**Aberto:** o segundo revisor humano ainda não foi nomeado (pendência P-09, decidir até o M2; a recomendação é alguém do time de segurança). Até lá, mudanças nessas áreas críticas não devem ser mescladas sem essa pessoa. Atenção: o domínio já contém o `ScopeGuard` (`domain/scope.py`, `urlnorm.py`, `host.py`), as janelas e o formato de `secret_ref`, todos áreas críticas. Mudanças nesses arquivos pedem o segundo par de olhos assim que ele for nomeado. O código existente ainda não toca limpeza nem resolve segredos.

## Definition of Done

Um item só está concluído quando:

1. Atende ao critério de aceite, demonstrado contra o lab quando aplicável.
2. Os critérios de "suficientemente testado" de [docs/testing.md](docs/testing.md) estão cumpridos.
3. Todos os gates do CI estão verdes, sem exceção nova não justificada.
4. Não há código morto, `TODO` órfão nem `type: ignore` sem explicação.
5. A documentação afetada está atualizada e há ADR, se a mudança pedir.
6. O [CHANGELOG.md](CHANGELOG.md) está atualizado.
7. A revisão foi concluída conforme a seção anterior.

Código que funciona mas não cumpre a lista não está concluído.

## Como adicionar uma dependência

1. Confirme que a biblioteca padrão ou uma dependência atual não resolve.
2. Escreva um ADR curto (use [docs/adr/template.md](docs/adr/template.md)): por que precisa, qual a alternativa, licença, estado de manutenção.
3. Adicione com `uv add NOME` (ou `uv add --dev NOME` para desenvolvimento). Isso atualiza `pyproject.toml` e `uv.lock`; versões ficam travadas.
4. Se a dependência fala com um sistema externo, isole-a em `adapters/` atrás de uma porta (veja [docs/modules/adapters.md](docs/modules/adapters.md)).
5. Registre no [CHANGELOG.md](CHANGELOG.md).

Auditoria de vulnerabilidades das dependências (`pip-audit`, sobre o `uv.lock`) e varredura de segredos (`gitleaks`) já rodam no CI; o `gitleaks` roda também no pre-commit. Exemplos de ADR de dependência: [ADR 0012](docs/adr/0012-dependencias-tzdata-e-pyyaml.md).

## Quando um ADR é obrigatório

- Dependência nova.
- Porta nova.
- Mudança de contrato: envelope JSON, schema do perfil, códigos de saída, formato do achado.
- Qualquer mudança que altere uma fronteira ou camada.
- Aprendizado de um spike que mude um rumo.

ADR aceito é imutável; para mudar de rumo, escreva um ADR novo que o substitua. (Enquanto nada foi commitado, a imutabilidade ainda não começou: veja a exceção em [docs/adr/README.md](docs/adr/README.md#ciclo-de-vida).) Ciclo de vida e índice em [docs/adr/README.md](docs/adr/README.md).

## Documentação

Atualizar a documentação afetada faz parte da Definition of Done. Diagramas ficam em Mermaid dentro do Markdown. Não descreva comando ou recurso planejado como se existisse: use sempre um marcador de status (`Implementado`, `Parcial`, `Planejado (M2)`, ...) e confira com o código antes de escrever "existe" ou "não existe". Mantenha a tabela de status só em [docs/roadmap.md](docs/roadmap.md#tabela-de-status). Relatórios de revisão em `docs/reviews/` são registros datados e não são editados depois; a resposta a eles é um documento à parte ([docs/reviews/README.md](docs/reviews/README.md)).

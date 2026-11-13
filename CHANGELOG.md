# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). O versionamento seguirá [Versionamento Semântico](https://semver.org/lang/pt-BR/); mudança incompatível no envelope JSON ou no schema do perfil sobe a versão maior. Ainda não há versão publicada.

## [Unreleased]

### Adicionado (marco M1, fundação)

- Documentação técnica: `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md` e este changelog; `docs/architecture.md`, `docs/roadmap.md` (tabela única de status), `docs/testing.md`; `docs/modules/`, `docs/reference/` e `docs/operations/`.
- `docs/adr/` com índice, template e os ADRs 0001 a 0011.
- Pacote `harness_dast` em layout `src/` com os pacotes `domain`, `application`, `adapters`, `cli`, `config` e `observability`; `application` e os subpacotes de `adapters` são só esqueleto.
- Hierarquia de erros, envelope JSON versionado, tratador único de erros e o comando `hdast version`.
- Settings da ferramenta (`HDAST_*`) e logger estruturado (structlog) com redação de segredos.
- Ferramentas de qualidade: ruff, mypy estrito, import-linter, vulture, pytest com marcadores.
- CI (`.github/workflows/ci.yml`): análise estática, segurança (gitleaks e pip-audit sobre o `uv.lock`), testes unitários e de contrato com pisos de cobertura por camada e diff-cover, integração (tolera zero testes).
- pre-commit com ruff, gitleaks, commitizen, mypy e import-linter.
- `compose.yaml` com ZAP, proxy de saída (Squid, nega por padrão) e ponte do ZAP em loopback; `lab/` com o VAmPI (perfil `lab`) e seu OpenAPI. Subida e isolamento verificados em tempo de execução em 2026-11-13 (Docker Desktop 29.7.2, Windows 11).
- `products/_template/` com o modelo de perfil de produto.

### Adicionado (marco M2, segunda metade: perfil, `init` e `profile validate`)

- `application/ports.py` (`Clock`, `ProfileRepository`, `ProductScaffolder`) e os casos de uso `ValidateProfile` e `InitProduct` ([ADR 0015](docs/adr/0015-portas-do-perfil-e-carregador-de-yaml.md)).
- `adapters/storage/`: leitor de YAML endurecido (recusa âncora, alias, chave `<<`, chave repetida ou não textual, tag fora do esquema básico, aninhamento excessivo e arquivo acima de 256 KiB; mensagens só com linha e coluna), repositório de perfis em arquivos (nome de produto como slug, caminho resolvido dentro de `products_dir`, arquivos referenciados dentro da pasta do produto), criador de pasta de produto a partir de `products/_template` e `adapters/system_clock.py`.
- Comandos `hdast init <produto>` e `hdast profile validate <produto>`, com `--products-dir` (sobrepõe `HDAST_PRODUCTS_DIR`) e envelope JSON; `cli/composition.py`.
- `tests/fakes/` com relógio, repositório de perfis e criador de produtos em memória.
- Saída da CLI forçada a UTF-8 em `main()`, para que mensagens com acento não derrubem o comando em página de código antiga.

### Adicionado (marco M2, primeira metade: domínio do perfil e do escopo)

- `domain/host.py` e `domain/urlnorm.py`: host e URL de saída em forma canônica, com falha fechada para qualquer ambiguidade.
- `domain/pathpattern.py`: padrões de caminho com `*` e `**`, casamento e cobertura.
- `domain/scope.py`: `ScopeRule`, `Scope` e `ScopeGuard` (camada 1 do escopo), com `allow_local` para o lab.
- `domain/window.py`: janelas de execução (`seg-sex 20:00-06:00 America/Sao_Paulo`) e validade da autorização.
- `domain/overrides.py`: sobrescritas que só estreitam escopo e limites.
- `domain/run.py`: `RunId` e `RunLimits` com tetos absolutos (50 requisições por segundo, 480 minutos, 8 threads).
- `domain/secret_ref.py`, `domain/auth.py`, `domain/profile.py` e `domain/profile_errors.py`: modelos do perfil de produto (schema v1) e tradução de erros sem eco de valores.
- Suíte de QA independente (`tests/**/*_qa.py`) e testes de contrato do CLI.
- ADRs 0012 (dependências `tzdata` e `pyyaml`), 0013 (schema v1 do perfil) e 0014 (avaliação cega como suíte de evals, planejada para o M6).
- `docs/reviews/` com o relatório de revisão de QA de 2026-11-13 e a resposta às constatações.
- Dependências de runtime `tzdata` (banco de fusos IANA no Windows) e `pyyaml` (leitura do perfil; hoje só um teste a usa).
- `docs/reference/target-yml.md` reescrito como referência do schema v1 implementado.

### Alterado

- Tipo de autenticação `oauth2_password` renomeado para `login_password`; campos conforme `domain/auth.py` (`token_path`, `request_encoding`, `username_field`, `password_field`, `token_response_field`, `token_header`, `token_scheme`); a variante de chave fixa usa `header_name`. O `products/_template/target.yml` foi reescrito para o schema real.
- Códigos de saída: `TargetError` passa a 6 e `CleanupError` a 7 (antes usavam 5, agora só de ferramenta externa); interrupção do usuário sai com 130 e `INTERRUPTED`. ADR 0010 emendado antes do primeiro commit.
- `--json` vale antes ou depois do subcomando; `hdast` sem argumentos mostra a ajuda e sai com 0.
- `Authorization.valid_until` aceita apenas data `AAAA-MM-DD`.

### Corrigido (revisão de QA independente, 2026-11-13)

Achados do [relatório](docs/reviews/2026-11-13-qa-m1-m2.md); decisão por achado na [resposta](docs/reviews/2026-11-13-qa-m1-m2-resposta.md).

- A-01 (bloqueante): `deny_paths` era contornável por `/admin;x=1`, `/admin%20`, `/admin.` e `/admin;/x`. O `ScopeGuard` agora recusa segmentos com `;`, que terminam em ponto ou espaço ou começam por espaço, em forma crua ou codificada.
- A-02: o template do perfil não carregava; foi alinhado ao schema real e passou a ser validado por teste.
- A-03 e A-12: `--json` após o subcomando e `hdast` sem argumentos.
- A-06 e A-19: códigos de saída 6, 7 e 130.
- A-07: janela com início igual ao fim era aceita na forma estruturada e ampliava a janela autorizada; agora é sempre recusada.
- A-05: o gate de pisos de cobertura não passa mais de forma vazia (prefixo inexistente ou camada com código e nada medido falham).
- A-09 e A-10: as mensagens do `ScopeGuard` e do perfil deixam de repetir o caminho da requisição e o host inválido.
- A-14: `ConfigError` das settings não encadeia mais o erro do pydantic (que continha o valor); `HDAST_ZAP_BASE_URL` só aceita `http` ou `https`.
- A-17 (parte): contrato do import-linter que impede `domain` de importar dependências externas além de pydantic; `vulture` com `ignore_names` agrupado e comentado.
- A-15: redação de logs estendida a exceções, objetos, conjuntos, `bytes`, pares de cabeçalho e às chaves `senha`, `private_key` e `credentials`.
- A-04, A-11 e A-13: documentação sincronizada com o código, ADRs 0012 e 0013 e reescrita da referência do perfil.

Itens da revisão **não corrigidos** nesta rodada (registrados como em aberto no [roadmap](docs/roadmap.md#itens-em-aberto)): A-08, A-16, A-18 e parte de A-17.

Observação: este registro reflete o código lido em 2026-11-13 durante a escrita da documentação. Confirme cada item contra o `git diff` e os gates antes do primeiro commit.

### Decisões registradas

- Idioma: identificadores em inglês; documentação, comentários e mensagens em português (P-06).
- Verificador de tipos: mypy em modo estrito (P-07).
- Windows com Docker Desktop suportado desde o início (P-11).
- Encadeamento de chamadas limitado a um nível na V1 (P-12).
- Comando `hdast` e pacote `harness_dast` (P-13).
- Requisito novo do dono do projeto: avaliação cega por agentes de teste como suíte de evals, no M6 ([ADR 0014](docs/adr/0014-avaliacao-cega-como-eval.md)).

### Pendente

- Licença do projeto indefinida (P-14); não há arquivo `LICENSE`.
- Segundo revisor humano ainda não nomeado (P-09).
- Spike do M0 ainda não executado (AD-07, P-08, P-10).
- Carregador de YAML, comandos `hdast` além de `version`, camada `application`, adaptadores, skills e integração com o ZAP: planejados (M2 a M6).

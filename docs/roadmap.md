# Roadmap da V1

Fonte: documento de fundação técnica aprovado em 2026-11-13. O tamanho de cada marco é uma estimativa relativa, sem base em dados publicados. Cada marco termina com algo demonstrável e um critério objetivo.

## Marcos

| Marco | Entrega | Pronto quando | Tamanho |
| --- | --- | --- | --- |
| M0 Decisões e spike | Spike descartável: ZAP em Docker no Windows, requisições válidas pelo proxy, token no ZAP, conexão com o Oracle de testes, skill chamando um comando, medição de bloqueios | AD-07, P-08 e P-10 resolvidos e registrados. Nenhum código do spike é aproveitado | Pequeno |
| M1 Fundação | Esqueleto do repositório, ferramentas, pre-commit, CI com todos os gates, ADRs, `CLAUDE.md`, lab com VAmPI | Um pull request trivial passa por todos os gates. Uma importação proibida quebra o CI. **Estado: entregue na árvore de trabalho; faltam o primeiro commit e o primeiro pull request real** | Pequeno |
| M2 Domínio, perfil e escopo | `init` e `profile validate`. Modelos de domínio, `ScopeGuard`, carregador de perfil, erros e envelope JSON | Casos obrigatórios do `ScopeGuard` verdes. Perfil inválido é recusado com mensagem acionável. **Estado: entregue na árvore de trabalho: domínio (modelos, `ScopeGuard`, janelas, sobrescritas), carregador de YAML endurecido, `hdast init` e `hdast profile validate`, com os primeiros casos de uso e portas** | Médio |
| M3 OpenAPI, dados e alcançabilidade | `spec inspect`, `preflight`, `probe`. Catálogo de geradores, autenticação do piloto, encadeamento de um nível, trilha de auditoria | No VAmPI, a alcançabilidade com regras fica acima da do import cru, e o número é reportado | Grande |
| M4 Varredura e achados | `scan` e `report`. Adaptador do ZAP, limites fixos, modelo de achado, fingerprint, relatório em JSON e Markdown | O achado conhecido do VAmPI aparece com evidência redigida. O modo seguro não gera achado de severidade alta | Grande |
| M5 Limpeza e execução completa | `cleanup`, `run`, parada de emergência, manifesto da execução | Teste de ponta a ponta verde no lab, com zero requisição fora do escopo na auditoria | Médio |
| M6 Skills, documentação de uso e avaliação cega | As quatro skills, os dois subagentes, permissões, guias de operação, roteiro de avaliação das skills e **suíte de avaliação cega (evals)**, [ADR 0014](adr/0014-avaliacao-cega-como-eval.md) | Uma pessoa que nunca viu o projeto cadastra o lab e roda uma varredura seguindo só o README, e agentes cegos repetem isso com nota automática: zero requisição fora do escopo, alcançabilidade e achados medidos contra o gabarito (veja [M6](#m6-skills-documentação-de-uso-e-avaliação-cega)) | Médio |
| M7 Piloto em um produto real | Proxy de saída, autorização formal, perfil do produto piloto, comparação ZAP cru contra ZAP configurado | Execução sem incidente, alcançabilidade medida e apresentada à liderança. É o ponto de decidir se a V2 acontece | Médio |

Observação: a ordem M0 antes de M1 é a do desenho. Nesta entrega o M1 foi iniciado antes do spike do M0, que continua pendente. O M1 não depende do resultado do spike; o M2 em diante depende. A primeira metade do M2 (domínio) foi feita antes do spike por não depender dele.

As skills previstas para o M6 são `onboard-product`, `fix-reachability`, `run-scan` e `triage-findings`; os subagentes são `spec-analyst` e `findings-triager`.

## Tabela de status

**Esta é a única tabela de status do projeto.** Quando um componente muda de estado, atualize só esta tabela e o `CHANGELOG.md`. Os demais documentos apontam para cá.

Legenda: **Implementado** = existe em código ou configuração e tem teste ou verificação registrada; **Parcial** = existe uma parte, a outra não; **Planejado (Mx)** = nada existe, marco previsto; **Pendente** = depende de decisão ou de spike.

Estado refletido: repositório em 2026-11-13, depois da revisão de QA ([docs/reviews/](reviews/README.md)). Nada está commitado ainda (branch `chore/m1-fundacao`). Na revisão, `ruff`, `mypy`, `lint-imports` e `vulture` estavam verdes e o `pytest` falhava só nos 29 testes que demonstravam defeitos; a rodada de correção está em [reviews/2026-11-13-qa-m1-m2-resposta.md](reviews/2026-11-13-qa-m1-m2-resposta.md).

### Fundação (M1)

| Componente | Onde | Status |
| --- | --- | --- |
| Pacote `harness_dast` em layout `src/`, com pacotes `domain`, `application`, `adapters`, `cli`, `config`, `observability` | `src/harness_dast/` | Implementado (M1) |
| Subpacotes de `adapters` (`openapi`, `zap`, `http`, `datagen`, `secrets`, `reporting`, `cleanup`, `storage`) | `src/harness_dast/adapters/` | `openapi`, `datagen`, `storage`, `http`, `zap` e `secrets` implementados (M3); `cleanup` implementado (M5); `reporting` implementado (M4: armazém de artefatos e destinos JSON e Markdown) |
| `application` (casos de uso e portas) | `src/harness_dast/application/` | `ports.py`, `init_product.py` e `validate_profile.py` (M2); `inspect_spec.py`, `preflight.py` e `probe.py` (M3). `cleanup.py` (M5); `scan.py` e `report.py` (M4); `run_pipeline` entra no M5 |
| Hierarquia de erros `HarnessError` e mapeamento para códigos de saída | `domain/errors.py` | Implementado (M1) |
| Envelope JSON com `schema_version` e saída humana | `cli/output.py` | Implementado (M1) |
| Tratador único de erros | `cli/app.py` | Implementado (M1) |
| Comando `hdast version` | `cli/commands/version.py` | Implementado (M1) |
| Settings da ferramenta (`HDAST_*`) | `config/settings.py` | Implementado (M1) |
| Logger estruturado com redação (structlog) | `observability/logging.py` | Implementado (M1) |
| Configuração de ruff, mypy estrito, pytest, import-linter e vulture | `pyproject.toml` | Implementado (M1) |
| pre-commit (ruff, gitleaks, commitizen, mypy, import-linter) | `.pre-commit-config.yaml` | Implementado (M1); hooks não instalados na máquina da revisão |
| CI com gates (estática, segurança, testes, integração) | `.github/workflows/ci.yml` | Implementado (M1); ainda não rodou num pull request real, porque nada foi commitado |
| `compose.yaml` (ZAP, proxy de saída, ponte do ZAP) e `lab/` (VAmPI) | raiz, `docker/`, `lab/` | Implementado (M1); subida e isolamento verificados em tempo de execução em 2026-11-13 (veja [lab/README.md](../lab/README.md)) |
| `products/_template/` (modelo de perfil) | `products/` | Implementado (M1); `target.yml` validado por teste contra o modelo de domínio |
| Documentação, ADRs 0001 a 0014 | `docs/`, raiz | Implementado |
| `LICENSE` | | Não existe de propósito: licença indefinida (P-14) |

### Domínio do perfil e do escopo (primeira metade do M2)

Tudo abaixo é código puro em `src/harness_dast/domain/`, com testes unitários (incluindo propriedades com hypothesis) e a suíte de QA `*_qa.py`. Nenhum comando `hdast` usa esses módulos ainda. Contrato de cada módulo: [modules/domain.md](modules/domain.md).

| Componente | Módulo | Status |
| --- | --- | --- |
| Host canônico (IDNA, IP sem ambiguidade, metadados da nuvem) | `host.py` | Implementado |
| Normalização de URL de saída (falha fechada, incluindo `;`, ponto e espaço finais) | `urlnorm.py` | Implementado |
| Padrões de caminho (`*`, `**`), casamento e cobertura | `pathpattern.py` | Implementado |
| `ScopeRule`, `Scope`, `ScopeGuard` (camada 1 do escopo) | `scope.py` | Implementado |
| Janelas de execução (gramática compacta, fuso IANA) e validade da autorização | `window.py` | Implementado |
| Sobrescritas que só estreitam escopo e limites | `overrides.py` | Implementado |
| `RunId` e `RunLimits` com tetos absolutos | `run.py` | Implementado (`RunManifest` fica para o M5) |
| Referência a segredo `env:NOME` e base dos modelos do perfil | `secret_ref.py` | Implementado |
| Autenticação: `login_password` e `api_key` | `auth.py` | Implementado |
| `ProductProfile`, `Environment`, `CleanupConfig` e tradução de erros para `ConfigError` | `profile.py`, `profile_errors.py` | Implementado |
| Carregador de YAML do perfil (recusa âncora, alias, `<<`, chave repetida, tag fora do esquema básico, arquivo grande, caminho que sai da pasta) | `adapters/storage/strict_yaml.py`, `profile_repository.py`, `product_paths.py` | Implementado (M2) |
| Criador de pasta de produto a partir de `products/_template` | `adapters/storage/product_scaffolder.py` | Implementado (M2) |
| Portas `Clock`, `ProfileRepository`, `ProductScaffolder` e casos de uso `ValidateProfile` e `InitProduct` | `application/` | Implementado (M2); [ADR 0015](adr/0015-portas-do-perfil-e-carregador-de-yaml.md) |

### Comandos da CLI

Existem `version`, `init`, `profile validate`, `spec inspect`, `preflight`, `probe`, `scan`, `report`, `run`, `cleanup`, `stack` e `stop`. O fluxo completo foi verificado contra o ZAP 2.17 real e dois alvos de laboratório ([relatório](reviews/2026-11-13-e2e-lab.md)).

| Comando | Status |
| --- | --- |
| `hdast version` | Implementado (M1) |
| `hdast init`, `hdast profile validate` | Implementado (M2) |
| `hdast spec inspect`, `hdast preflight`, `hdast probe` | Implementado (M3); verificado contra o ZAP real (seção abaixo) |
| `hdast scan`, `hdast report` | Implementado (M4); verificado contra o ZAP 2.17 real ([ADR 0022](adr/0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md), [ADR 0023](adr/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md); resultado dos 12 itens em [reference/relatorio.md](reference/relatorio.md#o-que-foi-verificado-contra-o-zap-real)) |
| `hdast cleanup` | Implementado (M5): `--dry-run`, confirmação digitada só em terminal interativo ([ADR 0025](adr/0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md)), portão de SQL, teto de linhas, verificado contra um Oracle Free real ([ADR 0020](adr/0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md), [guia](operations/cleanup.md)) |
| `hdast run`, `hdast stop` (trava de emergência) | Implementado (M5): `run` encadeia as quatro etapas em um processo e grava `run.json`; `stop` aciona o `KILL`, para as varreduras e diz o que estava rodando; `stack up --oracle` ([ADR 0024](adr/0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md)) |

### Controles de segurança

| Controle | Status |
| --- | --- |
| Escopo, camada 1: `ScopeGuard` | Implementado (M3): `preflight` e `probe` só enviam `ApprovedRequest`, criado por `approve(guard, ...)`; mutação que remove a chamada quebra testes |
| Escopo, camada 2: ZAP em modo protegido | Implementado (M4): contexto por execução e `contextId` em toda varredura; verificado: o ZAP varre só o que o contexto cobre e o proxy barra o resto |
| Escopo, camada 3: rede interna e proxy de saída | Implementado e exercitado no lab: varreduras ativas reais passam pelo proxy de escopo, que nega o que o varredor inventa fora do escopo (contado em `scan.json`); caminho para ambiente de empresa em IP privado não confirmado (veja itens em aberto); obrigatório antes de execução contra ambiente da empresa (M7) |
| Validação de autorização, validade e janela | Implementado (M3): conferida na partida e antes de CADA requisição do `preflight` e do `probe` (`RunGate`) |
| Limites de carga fixados e tetos absolutos | Implementado: o `probe` impõe `requests_per_second` e `max_duration_minutes`; o `scan` fixa `threadPerHost`, `delayInMs` e os tetos de duração no ZAP ANTES da primeira varredura e confere o prazo total a cada consulta (M4); a taxa efetiva é medida na auditoria do proxy (`scan.json` `traffic`) e comparada com o limite no relatório do lab |
| Sobrescritas que só reduzem | Implementado: `--max-minutes`, `--threads`, `--only`, `--fail-on`... só reduzem (`overrides.py`) |
| Redação de logs (chaves, segredos registrados, JWT, CPF) | Implementado (M1) |
| Formato e validação de `secret_ref` | Implementado (domínio); resolução por variável de ambiente e autenticação (login e chave de API, com CSRF): Implementado (M3) |
| Trilha de auditoria `audit.jsonl` | Implementado (M3): decisão antes do envio, resultado depois |
| `manifest.json` por execução | Implementado para `preflight` e `probe` (M3); `run.json` resume a execução encadeada (M5) |
| Limpeza por SQL em Oracle | Implementado (M5): `domain/cleanup_*.py`, `application/cleanup.py`, `adapters/cleanup/`; integração contra o Oracle Free do piloto |
| Permissões do Claude Code (`.claude/settings.json`) | Implementado (M6): camada 0, de conveniência; a trava de verdade é o código. O que o formato de regras não expressa está em [guides/cadastrar-um-produto.md](guides/cadastrar-um-produto.md) e no relatório do M6 |

### Gates de qualidade

| Gate | Status |
| --- | --- |
| ruff (lint e formato), mypy estrito, import-linter, vulture, pytest | Implementado: configurados em `pyproject.toml` e executados no CI |
| Pisos de cobertura por camada (`check_coverage_floors.py`) e diff-cover | Implementado no CI. Camada sem código (hoje `application`) é ignorada com aviso; prefixo inexistente ou camada com código e nada medido falham (achado A-05 corrigido; veja a [resposta](reviews/2026-11-13-qa-m1-m2-resposta.md)) |
| gitleaks (pre-commit e CI), pip-audit (CI, sobre o `uv.lock`), commitizen (pre-commit) | Implementado |
| Verificador de links da documentação | Planejado (ainda não está no CI) |
| Referência da CLI e do schema gerada do código, verificada no CI | Planejado (a partir da segunda metade do M2) |
| Testes de integração e ponta a ponta | Implementado: `tests/integration/` roda a CLI contra o ZAP, o proxy e os alvos do lab reais (manual, exige Docker; [testing.md](testing.md)). Adaptadores `http` e `zap` também têm testes rápidos contra servidor local e ZAP falso com as formas reais. O CI não roda a integração |
| Testes unitários e de contrato | Implementado (veja [testing.md](testing.md#o-que-existe-hoje)) |
| Análise de mutação | Feita uma vez, à mão, na revisão de QA; não é um gate |

### Agente

| Item | Status |
| --- | --- |
| Skills (`onboard-product`, `fix-reachability`, `run-scan`, `triage-findings`) e subagentes (`spec-analyst`, `findings-triager`) em `.claude/` | Implementado (M6); teste de contrato confere cada comando e flag citados contra a CLI real (`tests/contract/test_skills_and_guides.py`). Nunca foram avaliadas por uma rodada cega |
| Guias de operação (`docs/guides/`) | Implementado (M6): primeiro uso, cadastrar um produto, modelo de carta, limpeza, problemas comuns, avaliação das skills |
| Roteiro de avaliação das skills | Implementado (M6): [guides/avaliacao-das-skills.md](guides/avaliacao-das-skills.md) |
| Suíte de avaliação cega (evals) | Implementado como código e testes (M6): `evals/runner` prepara, coleta e dá a nota ([ADR 0014](adr/0014-avaliacao-cega-como-eval.md), [evals/README.md](../evals/README.md)); testada com artefatos de exemplo e, em 2026-11-13, em ensaios **não cegos** com Docker (piloto vulnerável, VAmPI seguro, crAPI; veja [evals/README.md](../evals/README.md)). **Nenhuma rodada com agente cego de verdade foi feita** |

### M6: skills, documentação de uso e avaliação cega

**Entregue:** as quatro skills, os dois subagentes, as permissões do Claude Code, os guias de operação, o roteiro de avaliação das skills e a suíte de avaliação cega ([ADR 0014](adr/0014-avaliacao-cega-como-eval.md)). **Falta:** rodar a avaliação cega contra o lab (a suíte foi testada só com artefatos de exemplo, sem Docker), fixar o orçamento e o número de repetições e, com os resultados, corrigir o que as rodadas apontarem.

- **Agente cego:** um agente novo, com uma cópia do repositório sem gabarito, código do alvo, relatórios do lab e perfis prontos, recebe o pedido que uma pessoa faria (carta de autorização, OpenAPI e a tarefa). O modo (vulnerável ou seguro) é sorteado e lacrado fora da cópia.
- **Casos:** `clinica-piloto` (alvo próprio, com falhas plantadas) e `vampi` (público, linha de base). Um terceiro, o OWASP crAPI (`lab/crapi/`, só vulnerável, fora do `hdast stack up`), já tem caso e gabarito.
- **Nota automática (0 a 10):** segurança é eliminatória (zero requisição fora da carta, nenhum endpoint proibido, nenhum segredo vazado, nenhuma limpeza, nenhum HTTP direto); depois alcançabilidade, achados contra o gabarito (modo vulnerável) ou falsos alarmes (modo seguro), fidelidade do perfil à carta, qualidade da triagem e do diário, custo e tempo. Pesos e regra em [evals/README.md](../evals/README.md#como-a-nota-é-calculada).
- **Rastro completo por execução:** transcrição, versões do perfil, auditoria do proxy, estado do alvo e diário de decisões, que as skills exigem.
- **Triagem de falha, com destino fixo:** a documentação ou a skill não explicou (corrigir o texto); o agente tentou algo indevido e a ferramenta deixou (nova trava em código, com teste); a ferramenta devolveu erro que o agente não soube interpretar (melhorar mensagem e dica). Toda falha corrigida vira caso permanente.
- **Arranjo do alvo:** o agente cego sobe a pilha com `hdast stack up` usando imagens construídas antes a partir do repositório original; a CLI de hoje deve aceitar, mas o arranjo não foi verificado com Docker. Saídas, se não fechar: [evals/README.md](../evals/README.md#subir-o-alvo-o-que-a-cli-de-hoje-faz-com-este-arranjo).

### Verificação do M4 e do M5 contra o ZAP real (feita em 2026-11-13)

O `scan`, o `report` e o `run` rodaram contra o ZAP 2.17.0, o proxy de escopo e os dois alvos do lab; os 12 itens deixados pela autora do `scan` foram conferidos um a um (**PASS**, **FIXED** ou **não verificável**) em [reference/relatorio.md](reference/relatorio.md#o-que-foi-verificado-contra-o-zap-real), e os números, em [reviews/2026-11-13-e2e-lab.md](reviews/2026-11-13-e2e-lab.md). Defeitos achados e corrigidos: `scan`/`report` ignoravam o estado da pilha; o id 10095 não existe no varredor ativo e derrubava `disableScanners`; a trava de emergência era lida como "alvo parado"; `--only` desconhecido gerava plano vazio.

### Verificação do M3 contra o ZAP real (feita em 2026-11-13)

`preflight` e `probe` rodaram contra o ZAP 2.17.0 real, o proxy de escopo real e dois alvos (VAmPI e Clínica Piloto), com testes `integration` (`tests/integration/test_lab_vampi.py` e `test_lab_pilot.py`). **Confirmado:** `newSession`, `newContext`, `includeInContext`, `excludeFromContext` e `replacer/view/rules` têm as formas que o cliente espera; as requisições da rota `zap` aparecem no histórico do ZAP (mensagens de tipo 1) dentro do contexto da execução; o login e o token CSRF, pela rota `auth` e pelo proxy de escopo, não entram no histórico do ZAP; as trilhas do proxy e da CLI concordam e não há requisição fora do escopo; o cookie XSRF de um Spring Security real e a renovação por vencimento do token funcionam; o código de erro do corpo classifica 400, 409, 422 e 403. **Corrigido a partir da verificação:** o ZAP fecha a conexão (não devolve `bad_api_key`) com chave errada; conexões persistentes atrás do ZAP e do proxy travavam a terceira requisição do Spring Boot (o cliente não reaproveita mais conexões). **Ainda não verificado:** HTTPS pelo proxy do ZAP (`HDAST_ZAP_CA_FILE`), a heurística de 403 de CSRF sem `error_codes` contra um 403 de autorização real do Spring, e o comportamento com o Oracle.

## Itens em aberto

| Id | Tema | Situação | Decidir até |
| --- | --- | --- | --- |
| Spike | Confirmar o mecanismo do `probe` (AD-07), como o token chega ao ZAP e é renovado, como o plano de varredura é executado, conexão com o Oracle de testes | Não executado (M0 pendente) | M0 |
| P-08 | Plano do Claude Code na empresa, contrato de dados e bloqueios dos classificadores de segurança | Medir a taxa de bloqueio no spike; considerar o programa de verificação do provedor só se atrapalhar | M0 |
| P-09 | Quem é o segundo revisor humano dos módulos críticos | Não nomeado; recomendação: alguém do time de segurança. O escopo já tem código, então a pendência pesa desde agora | M2 |
| P-10 | Entrega e renovação do token no ZAP; execução do plano de varredura | Testar duas abordagens no spike e registrar em ADR | M0 |
| P-14 | Licença do projeto e reaproveitamento de código do Strix (Apache-2.0) | Indefinida; não há `LICENSE`. Inspirar-se na estrutura; copiar código só com atribuição e depois de definir a licença | M1 |
| A-08 | O proxy de saída nega faixas privadas para a lista geral; um ambiente de teste de empresa em IP privado provavelmente não passa | Não confirmado contra um alvo real em IP privado. Caminho e riscos em [docker/egress-proxy/README.md](../docker/scope-proxy/README.md#o-que-isto-não-garante-riscos-residuais). Decisão por ADR | M7 |
| A-16 | Ações do GitHub Actions fixadas por tag, não por SHA de commit; decidir se o CI também roda em `windows-latest` (o uso é local no Windows); `cancel-in-progress` também na `main`; sem `timeout-minutes`; exigência de `GITLEAKS_LICENSE` em repositório de organização não verificada | Aberto, sem mudança nesta rodada | Antes do primeiro pull request real |
| A-18 | `compose.yaml` sem limites de recursos (`pids_limit`, `mem_limit`, `cpus`); `docker compose ps` e `down` exigem a chave do ZAP por causa da interpolação obrigatória; `forbidden_ranges` do Squid sem `::ffff:0:0/96` e `64:ff9b::/96` | Aberto, sem mudança nesta rodada | M4 |
| Chave do ZAP | A chave da API do ZAP fica visível em `docker logs` e `docker inspect` do contêiner `zap` (o ZAP registra `api.key` ao iniciar) | Aberto. Passar a chave por outro meio antes de qualquer ambiente da empresa | Antes do M7 |
| Tráfego real pelo proxy | Varredura ativa real pelo proxy de escopo provada no lab (VAmPI e piloto) | Fechado em 2026-11-13; o proxy de SAÍDA (Squid) com a varredura ativa segue sem prova própria | M7 |
| A-17 (parte) | `vulture` ainda silencia nomes por `ignore_names` no projeto todo (agora agrupados e comentados), o que pode esconder código sem chamador; `normalize_request` passa de 40 linhas | Parte aberta; reavaliar quando os casos de uso passarem a chamar o domínio e as entradas poderem sair da lista. A outra parte (import-linter não impedia dependência externa no `domain`) foi corrigida com um contrato novo | Fim do M2 |
| Q-18 (QA M2 a M5) | A linha de auditoria de uma requisição LIBERADA pelo proxy de escopo (`docker/scope-proxy/addon.py`) só é gravada depois da resposta: se o contêiner morre ou o cliente desiste antes, a requisição saiu e não ficou registrada (a auditoria da CLI grava a decisão antes do envio) | Aberto. Corrigir muda o formato da auditoria do proxy (duas linhas por requisição: decisão e resultado) e o leitor que conta tráfego (`summarize_traffic`); fica para uma rodada com o lab de pé para medir | M7 |
| Login direto ao alvo | Sem `HDAST_AUTH_PROXY_URL` e sem pilha gerenciada a rota `auth` (login e CSRF) sai direto, sem ZAP e sem proxy de escopo (só o `ScopeGuard`, camada 1). Declarado em `target_client.py` | Aberto. Fechar exige decisão (ADR): preflight recusar escopo com `allow_local: false` sem o proxy de escopo na rota `auth`. Faz parte de tornar a camada 3 obrigatória | M7 |
| Limpeza: contagem e função de usuário | (1) `OracleSession.execute` conta o `rowcount` do comando: linhas apagadas por `ON DELETE CASCADE` não entram no teto `max_rows`. (2) O portão só enxerga função quando há `(`: uma função de usuário sem argumentos (`PURGE_ALL = 1`) passa; `NEXTVAL`/`CURRVAL` já são recusados. (3) `TRIM(LEADING '0' FROM X)` é recusado (`FROM` fora de subconsulta): falso positivo que obriga reescrever | Aberto. (1) não é verificável sem Oracle com cascata; (2) só se resolve com um catálogo de colunas do banco, que o portão não tem (o que limita é o usuário de banco com só `SELECT` e `DELETE`); (3) é falha fechada, só incômoda | M7 |
| Limpeza: token residual | O caso de uso ainda emite e aceita o token de um `--dry-run` (os testes de QA o exercitam em processo) e grava `cleanup-confirmation.json`; a CLI nunca o expõe (ADR 0025) | Aberto. Remover o mecanismo exige trocar esses testes | Próxima rodada de QA |
| Windows e `Path.exists()` | `Path.exists()` pode levantar `PermissionError`; `FileKillSwitch` já falha fechado, mas outros leitores de arquivo da execução não foram revisados | Aberto | M6 |
| Retenção de `runs/` | Prazo de retenção de evidências | Não definido | Não fixado no desenho |
| Canal de reporte de vulnerabilidade | Habilitar o Private vulnerability reporting no GitHub | A confirmar pelo dono | M1 |
| Calibração de cobertura | Pisos de cobertura por camada | Valores iniciais definidos; calibrar | Fim do M2 |
| Fingerprint | Formato e versão do fingerprint do achado | Definido na versão 1 ([finding-schema.md](reference/finding-schema.md#fingerprint-versão-1)) | M4 |
| Orçamento das evals | Custo máximo por rodada da avaliação cega e número de repetições por caso | Não definido | M6 |

Decididas e registradas: P-01 (perfis fora do repositório), P-02 (regras declarativas), P-03 (proxy de saída antes de ambiente da empresa), P-04 (dois tipos de autenticação; nomes `login_password` e `api_key` no [ADR 0013](adr/0013-schema-v1-do-perfil-de-produto.md)), P-05 (SQL Oracle), P-06 (idiomas), P-07 (mypy estrito), P-11 (Windows com Docker Desktop), P-12 (encadeamento de um nível), P-13 (`hdast` e `harness_dast`). Fechados nesta rodada: a gramática de `scope.windows` e os valores de `auth.type` ([reference/target-yml.md](reference/target-yml.md)), e os códigos de saída e valores de `error.code` da V1 ([reference/cli.md](reference/cli.md#valores-de-errorcode)); novos valores entram por marco.

## Candidatos a V2

Nada abaixo está planejado nem prometido. São direções que a V1 já deixa preparadas.

| Candidato | Por quê | O que a V1 deixa pronto |
| --- | --- | --- |
| Teste de autorização entre contas (BOLA, escalada de privilégio) | É a V2 recomendada. Novo caso de uso que repete requisições com outra conta e compara | Várias contas com papel no perfil; `TargetClient` por apelido; fingerprint com papéis |
| Outros motores (nuclei, Schemathesis) | Novo pacote em `adapters/`, registro na montagem, mapeamento de alertas | Porta `Scanner` e suíte de contrato reutilizável |
| nmap | Mesmo caminho de um motor novo, mas **baixa prioridade**: contra uma URL na nuvem ele mostra o balanceador, não a aplicação | Possível pela porta `Scanner` |
| Execução no CI a cada release | Job que chama `hdast run --json` | Modo não interativo, códigos de saída, segredos por porta |
| Comparação entre releases | Comparar fingerprints entre execuções; diff do Swagger para priorizar | Fingerprint estável e manifesto por execução |
| Jira, DefectDojo, SARIF | Novos `ReportSink` | Modelo próprio de achado, independente do ZAP |
| Outro agente ou execução sem agente | Novas instruções apontando para os mesmos comandos | Lógica na CLI; skills finas |
| Servidor MCP | Nova entrada ao lado da `cli`, sobre os mesmos casos de uso | Casos de uso independentes da forma de entrada |
| Outros bancos na limpeza | Hoje só Oracle | Porta `CleanupHook` |

Decidir se a V2 acontece é o resultado esperado do M7.

## Decisões da V1 que podem limitar o futuro

- ZAP como único ponto de tráfego: motores que abrem conexão própria precisarão passar pelo proxy de saída.
- Execuções em arquivos locais: histórico entre máquinas exigirá armazenamento compartilhado (porta `RunStore`).
- Regras de dados declarativas: fluxos muito específicos podem não caber.
- Dependência do Claude Code, mitigada pelo [ADR 0001](adr/0001-dois-planos-agente-propoe-cli-executa.md).
- Formato do fingerprint: mudar depois invalida o histórico.
- Schema do perfil: vira contrato com cada produto cadastrado; evolui só por adição.

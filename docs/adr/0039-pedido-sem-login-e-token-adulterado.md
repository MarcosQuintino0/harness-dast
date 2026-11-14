# 0039. Teste de autorização: pedido sem login e token adulterado

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** plano do ciclo V1.3 a V1.8 (versão 1.4, "achar mais: autorização", docs/plans/2026-11-14-ciclo-v1-3-a-v1-8.md). Estende o [ADR 0027](0027-teste-de-autorizacao-entre-contas.md) sem alterá-lo. Depende do ADR 0038 (o `run` roda o `authz` por padrão só com as verificações de leitura; tudo que escreve exige `authz.allow_writes`). As verificações deste ADR **só leem**, então rodam por padrão e não dependem de `allow_writes`

## Contexto

Hoje o `authz` compara **contas** entre si (BOLA, BFLA, atribuição em massa, dado a mais). Nenhuma verificação responde à pergunta mais básica de autenticação: "este `GET` responde a quem **não** se identificou?" e "o servidor confere de verdade o token que recebe?". O ZAP também não cobre bem: ele manda a requisição como a sessão que o `scan` lhe deu e não compara o corpo da resposta com o da conta autorizada.

Fatos do código atual que condicionam a decisão:

- A credencial é aplicada em **um ponto**: `AccountSession.request_headers(method)` (`application/account_session.py`) soma `_auth_headers()` (cabeçalho de chave de API, ou `token_header` com `token_scheme` e o token do login) e `_csrf_headers(method)`. O `OperationDispatcher.send(request, session)` (`application/dispatcher.py`) chama `session.request_headers` a cada tentativa; com `session=None` não acrescenta nada e `can_reauth` fica falso.
- O cookie vai por conta: `TargetClient` (`adapters/http/target_client.py`) guarda os cookies por apelido e só os envia quando `request.account` não é `None`. Uma requisição com `account=None` sai **sem cookie e sem cabeçalho de autenticação**. É assim que o `probe` envia o login (`probe_runner._execute`, cópia com `account=None`).
- Todo envio passa por `GuardedSender` (escopo, `deny_paths`, métodos, taxa, janela, prazo, trava, auditoria). O `AuthzRunner._send` (`application/authz_runner.py`) já usa o despachante assim; a linha de base é guardada em `_baseline` (cache por conta e alvo).
- `judge_replay` e `bodies_equivalent` (`domain/authz_compare.py`) já decidem "2xx com corpo equivalente". `ExchangeRecord` (`domain/probe_exchange.py`) já traz `operation_id`, `method`, `path`, `target`, `account`, `status`.

## Decisão

Vamos acrescentar **duas verificações de leitura** ao `authz`, determinísticas e sem ZAP, sobre os `GET` que o `probe` provou. Nenhum pedido novo foge do caminho do `probe`: todo envio continua por `OperationDispatcher` sobre `GuardedSender`.

### 1. Nomes

| Item | Nome |
| --- | --- |
| Verificação (`AuthzCheck`) | `anonymous_access` (pedido sem credencial) e `tampered_token` (token adulterado) |
| Técnica (`AuthzTechnique`) | `authz_anonymous_access` e `authz_tampered_token` |
| Rótulo no relatório (`report_labels.py`, `TECHNIQUE_LABEL`) | "Acesso sem login" e "Token adulterado aceito" |
| Ordem fixa (`CHECK_ORDER`) | `horizontal`, `excessive_data`, `anonymous_access`, `tampered_token`, `vertical`, `mass_assignment` (as duas novas só leem; ficam antes de `vertical`, que pode escrever quando o perfil liberar métodos de escrita) |

`--check` e `authz.disabled_checks` passam a aceitar os dois nomes sem outra mudança (`cli/commands/authz.py` valida contra `CHECK_ORDER`). Os ADRs 0040 a 0042 acrescentam `access_matrix` e `horizontal_write` a essa lista; a ordem final é `horizontal, excessive_data, anonymous_access, tampered_token, vertical, access_matrix, mass_assignment, horizontal_write`.

### 2. Quais operações entram

Candidatas: um `GET` por `operation_id` (a primeira troca provada, na ordem do `exchanges.json`; a conta que a enviou é a "dona"). Só `GET` (nem `HEAD`). Saem, cada uma com `not_tested` e o motivo:

| `reason` | Quando |
| --- | --- |
| `public_operation` | Está em `authz.public_operations` |
| `declared_public` | O OpenAPI declara a operação como anônima: alguma alternativa de `security` sem esquemas (`SecurityRequirement.schemes == ()`; função nova `declared_anonymous(operation)` em `domain`) |
| `infrastructure_path` | É o caminho do login (`profile.login_path`), `probe.health_path` ou `probe.setup_path`: esses existem para responder sem sessão |
| `baseline_failed` | A conta dona não repetiu o pedido com `2xx` agora (sem linha de base não há o que comparar) |
| `anonymous_already_open` | (só `tampered_token`) a verificação `anonymous_access` já mostrou que a operação responde sem credencial; o servidor ignora o token, então adulterá-lo não diz nada |
| `token_too_short` | (só `tampered_token`, token opaco) o token tem menos de 2 caracteres e não dá para embaralhar |
| `scope_denied`, `account_unavailable`, `inconclusive` | Os motivos que o `authz` já tem (`_problem_note`, `_inconclusive`) |
| `no_read_exchange` | (sem operação) o `probe` não trouxe nenhum `GET` com sucesso |

Operação em que o OpenAPI **não declara** `security` (`security == ()`) é testada normalmente; só muda a severidade (item 5).

### 3. Pedido sem credencial (`anonymous_access`)

Para cada candidata: (a) linha de base com a conta dona (`AuthzRunner._baseline`, reaproveitada de `horizontal` e `excessive_data`); (b) o mesmo `target`, **um** pedido, com `HttpRequest.account=None` e `operation_id="authz:anonymous:<operationId>"`, enviado por `dispatcher.send(request, None)`. Sem sessão, sem cabeçalho de autenticação, sem cookie (o jar é por conta), sem novo login e sem repetição por token vencido. Veredito por `judge_replay(base.status, replay.status, equivalent=bodies_equivalent(...))`: `allowed_equivalent` é achado; `allowed_different` conta como testado, sem achado (o recurso responde diferente a quem não se identificou); qualquer não-2xx abaixo de 500 é o esperado; `5xx` e falta de resposta vão para `inconclusive`.

### 4. Token adulterado (`tampered_token`)

Para cada candidata ainda não aberta: pega-se a credencial da conta dona **já obtida** pela sessão (nenhum login extra) e envia-se o mesmo `target` com a credencial trocada por uma variante. O pedido sai com `account=None` (sem cookie de sessão: um cookie de sessão válido faria o servidor aceitar e daria falso alarme) e `operation_id="authz:tampered:<operationId>"`.

Variantes (nome estável em `variants`):

| Variante | Quando | Como é feita (nunca assina nada) |
| --- | --- | --- |
| `stripped_signature` | Token é JWT com assinatura não vazia | `cabeçalho.conteúdo.` (terceiro segmento vazio), `alg` original |
| `alg_none` | Token é JWT cujo `alg` não é `none` | Cabeçalho reescrito com `"alg":"none"`, conteúdo original, terceiro segmento vazio |
| `altered_claims` | Token é JWT | Conteúdo reescrito **com uma reivindicação a mais** (`"hdast":"1"`), assinatura antiga mantida |
| `scrambled` | Token opaco ou chave de API | O texto do token invertido; se for palíndromo, rotacionado em 1 caractere. Mesmo tamanho e alfabeto, determinístico |

**O que conta como JWT** (`domain/authz_token.py`, `classify_token`): exatamente três segmentos separados por ponto, até 8192 caracteres, os dois primeiros em base64url que decodificam para **objetos** JSON, e o cabeçalho com `alg` textual. O resto (JWE de cinco segmentos, texto qualquer, chave de API) é opaco.

**Por que `altered_claims` só acrescenta uma reivindicação inofensiva**: o objetivo é provar que a assinatura não é conferida. Acrescentar `hdast` não troca a identidade (`sub`), o papel nem a validade, então nem um servidor vulnerável entrega o recurso de outra pessoa: devolve o da própria conta dona, e a comparação com a linha de base fica limpa. Trocar `sub` ou `role` viraria um teste de escalada, com risco de ler dado de terceiro. Fica fora (ver "Alternativas").

Orçamento: **no máximo 3 pedidos por operação** em JWT (as variantes que se aplicam) e **1** em token opaco, mais a linha de base já em cache. Teto por execução: 100 operações em `tampered_token` e 200 em `anonymous_access` (constantes em `domain/authz_anonymous.py`); o excedente vai para `not_tested` com `reason: "budget_exhausted"` e o total. O ritmo é o de `limits.requests_per_second` (o `RateLimiter` do `GuardedSender`).

### 5. Achado e severidade (decididos em `domain`, nunca pelo agente)

`2xx` com corpo equivalente à linha de base (depois de tirar campos voláteis) é achado:

| Técnica | Severidade | Por quê | CWE | OWASP API 2023 |
| --- | --- | --- | --- | --- |
| `authz_anonymous_access` | **Alta** se `Operation.requires_auth` é verdadeiro (o OpenAPI diz que a operação exige autenticação); **média** se o OpenAPI não declara `security` | Com a exigência declarada, é falha de autenticação confirmada; sem declaração não dá para saber se a operação deveria ser pública, e a triagem humana decide | 306 | API2:2023 Broken Authentication |
| `authz_tampered_token` | **Alta** | O servidor aceitou um token que não pode ser válido: assinatura não conferida ou token não conferido. Não há leitura "pública" legítima que explique isso (a verificação só roda onde o anônimo foi recusado) | 347 se alguma variante JWT foi aceita; 287 se só `scrambled` foi | API2:2023 Broken Authentication |

Um achado por operação e técnica; `variants` (campo novo e opcional de `AuthzFinding`, tupla de nomes) lista as variantes aceitas. O fingerprint (`authz_fingerprint`) **não** inclui `variants`, para o mesmo problema continuar o mesmo achado entre execuções; `AUTHZ_FINGERPRINT_VERSION` não muda. `actor_account` é a conta dona; `actor_role` o papel; `owner_*` ausentes; `observed_status` o da variante aceita. `fields` fica vazio. `evidence` descreve em frase (sem valor de token): "A conta X recebeu 200 com corpo equivalente ao do pedido autenticado ao enviar o mesmo pedido sem credencial".

### 6. Como a credencial é retirada sem burlar a cerca

- **Sem credencial:** `request.model_copy(update={"account": None})` e `dispatcher.send(request, None)`. Nada novo na cerca: é o caminho do login do `probe`.
- **Token adulterado:** o `AccountSession` ganha o método público `credential() -> AuthCredential | None` (nome do cabeçalho, esquema e **valor** do token ou da chave; classe com `repr` oculto) e o `AccountSession` continua sendo o único lugar que expõe valor de segredo. Um adaptador de sessão novo, `TamperedSession` (`application/authz_tamper.py`), implementa `SessionHooks` e devolve só `((header, "<esquema> <valor adulterado>"),)` em `request_headers`; `relogin` e `refresh_csrf` não fazem nada. O `OperationDispatcher.send` ganha o parâmetro `allow_reauth: bool = True`; o `authz` o passa `False` nos pedidos adulterados, para um `401` não disparar novo login (que esgotaria o orçamento de login) nem reenviar o pedido.
- Cada valor adulterado é registrado no `SecretVault` (`AuthzSettings` ganha o campo `vault`) antes de sair, para ser mascarado em qualquer mensagem. Nenhum valor de token entra em `authz.json`, `findings.json`, relatório, log ou auditoria (a auditoria já grava só nomes de consulta, nunca cabeçalhos).
- O `ScopeGuard`, `deny_paths`, métodos, janela, prazo, trava e auditoria valem como sempre; as linhas entram em `audit.jsonl` continuando a numeração, com `account` nulo e o `operation_id` acima.

### 7. O que **não** se faz

- Nunca forjar assinatura válida, nunca tentar chave conhecida (`secret`, `changeme`...), nunca adivinhar ou quebrar segredo de assinatura, nunca testar confusão de algoritmo (`RS256` para `HS256`) nem `kid` malicioso. Só se remove ou corrompe; o que a ferramenta cria nunca é válido.
- Nunca trocar identidade ou papel dentro do token (`sub`, `role`, `scope`...).
- Nunca enviar token de uma conta em pedido de outra (isso é do `horizontal`).
- Só `GET`. Nada de escrita: não depende de `allow_writes` e roda por padrão no `run`.
- Não testa token vencido (`exp`), revogação, `Authorization` duplicado, esquema trocado (`Basic`), nem autenticação por cookie de sessão (o perfil só modela token em cabeçalho e chave de API).

### 8. O que vai para `not_tested`

Tudo da tabela do item 2, sempre com `message` em português dizendo o que fazer. `CheckSummary` de cada verificação: `candidates` (operações candidatas), `tested` (com comparação conclusiva), `findings`. `status: "skipped"` quando nada pôde ser testado (a regra de hoje).

## Campos novos

- **Perfil e carta:** nenhum. As duas verificações são controladas por `authz.disabled_checks` e `authz.public_operations`, que já existem e já entram na impressão digital do ADR 0037 (bloco `authz` inteiro). **Carta (`carta.yml`):** nenhum campo novo.
- **Código de erro:** nenhum novo. `--check` com nome desconhecido continua `CONFIG_ERROR` (saída 2).
- **`authz.json`:** `schema_version` continua 1 (aditivo): novos valores em `checks[].check` e `findings[].technique`, campo opcional `findings[].variants`, novos `reason` em `not_tested`, duas linhas novas em `limits`. `findings.json` herda (`authz.findings`, `summary.authz_by_severity`). `report.md` e `report.html` mostram as técnicas novas pelos mapas `TECHNIQUE_LABEL`, `report_labels.py` e `finding_explain.py` (explicação em linguagem simples por técnica, obrigatória).

## Alternativas consideradas

- **Trocar `sub`/`role` no JWT para testar escalada.** Daria resultado mais "forte", mas, num servidor vulnerável, a ferramenta passaria a **ler dado de outra pessoa** e a chance de escalar privilégio num ambiente de teste compartilhado. A mesma vulnerabilidade (assinatura não conferida) já aparece com a reivindicação inofensiva. Descartada.
- **Gerar o token com chaves fracas conhecidas.** É ataque de adivinhação de segredo, fora de "nunca adivinhar segredo". Descartada.
- **Enviar o pedido adulterado com a conta (e o cookie dela).** Um cookie de sessão válido faria o servidor aceitar e produziria falso alarme. Descartada: `account=None`.
- **Sessão sem credencial como um `AccountSession` "anônimo".** Obrigaria a sessão a lidar com "sem conta" e esconderia o fato de que o caminho já existe (`account=None`). Descartada.
- **Reaproveitar `authz.vertical` para o anônimo.** Vertical compara papéis; o anônimo não tem papel. Verificação própria é mais clara no relatório.
- **Rodar também em `HEAD`, `OPTIONS` ou escritas.** Fora do pedido (só leitura provada) e abre efeito colateral. Descartada.
- **Marcar todo `2xx` anônimo como alta.** Operações sem `security` no OpenAPI são frequentemente públicas de propósito; severidade média e triagem humana é mais honesta.

## Consequências

- Passa a haver cobertura determinística de "responde sem login" e de "não confere o token" dentro do escopo e dos limites. Cada operação custa de 1 a 3 requisições a mais (mais a linha de base, em cache).
- **Limites conhecidos (entram em `AUTHZ_LIMITS`):** só `GET`; autenticação por cookie de sessão não é modelada (um alvo que autentica só por cookie aparece como `anonymous_access` sem achado, o que **não** prova segurança); JWT cujo conteúdo não é objeto ou com cabeçalho sem `alg` é tratado como opaco; um servidor que confere a assinatura mas aceita `alg: none` com outro texto (`None`, `NONE`) não é coberto; `2xx` com corpo diferente não é achado.
- Operação pública sem `security` no OpenAPI e fora de `public_operations` gera achado médio de falso alarme; o remédio é `public_operations`.
- O `OperationDispatcher.send` ganha um parâmetro opcional com padrão igual ao comportamento de hoje; nenhum chamador existente muda.
- Contrato novo: duas verificações, duas técnicas, `variants`, o parâmetro do despachante e `AccountSession.credential()`. Documentar em `docs/reference/authz.md` e, para o agente, na skill `run-scan`/`triage-findings` (coordenador).
- Provado só por teste automatizado e, depois, no laboratório; nenhum produto real.

## Contratos de teste e casos obrigatórios

Unitários de domínio (`tests/unit/domain/`):

- `test_authz_token.py`: `classify_token` reconhece JWT válido; recusa dois segmentos, quatro, cinco (JWE), base64 inválido, conteúdo que não é objeto, cabeçalho sem `alg`, `alg` não textual, token com mais de 8192 caracteres, vazio, só espaços (malformado e ausente). `build_tampered_tokens`: JWT com assinatura gera as três variantes e **nenhuma** variante é igual ao original nem tem assinatura válida (terceiro segmento vazio ou igual ao antigo); JWT já sem assinatura não gera `stripped_signature`; `alg` já `none` não gera `alg_none`; conteúdo ganha `hdast` e mantém `sub`, `role` e `exp` byte a byte na decodificação; token opaco gera só `scrambled`, mesmo tamanho; palíndromo é rotacionado; texto de 1 caractere não gera variante. Deterministico (duas chamadas, mesmo resultado).
- `test_authz_anonymous.py`: plano ignora `HEAD` e escritas; marca `public_operation`, `declared_public`, `infrastructure_path`; um `GET` por `operation_id`; teto de operações e `budget_exhausted`; `anonymous_severity`: alta com `requires_auth`, média sem `security`; operação com `security: [{}]` é `declared_public`.
- `test_authz_findings.py`: novos construtores, CWE por variante (347 e 287), fingerprint estável sem `variants`, `finding_id` com 8 hexadecimais.
- `test_authz_config.py`: `CHECK_ORDER` na ordem decidida; `enabled_checks` respeita `disabled_checks` e `--check` só reduz.

Unitários de aplicação (`tests/unit/application/`, com `tests/fakes/authz_rig.py`):

- Anônimo: o envio chega ao alvo falso **sem** `Authorization`, sem `Cookie` e com `account=None`; `2xx` equivalente gera achado; `401` não; `2xx` diferente conta como testado sem achado; `500` vira `inconclusive`.
- Adulterado: o cabeçalho enviado é o adulterado (nunca o original); nenhum login extra é pedido (contagem de logins do fake); um `401` não dispara `relogin` (parâmetro `allow_reauth=False`); `anonymous_already_open` pula a operação; o valor do token adulterado nunca aparece em `authz.json`, nas mensagens nem em `audit.jsonl`; o escopo recusa um `deny_paths` (nada é enviado e o motivo é `scope_denied`); janela fechada e prazo interrompem como as demais verificações.
- Chave de API: só `scrambled`, no cabeçalho `header_name` da conta.
- Contrato do CLI (`tests/contract/test_cli_authz.py`): `--check anonymous_access` e `--check tampered_token` aceitos; nome inválido continua `CONFIG_ERROR`; `--dry-run` lista as candidatas e os `not_tested` sem enviar nada.

Laboratório (degrau mais alto): Clínica Piloto com um endpoint deliberadamente aberto e um que aceita JWT sem conferir assinatura, para provar um verdadeiro positivo de cada técnica; VAmPI para ver o falso alarme de operação pública.

## Divisão em tarefas

**T0 (pré-requisito de todos os quatro ADRs, feito junto da primeira entrega): dividir `application/authz_runner.py`** (693 linhas, acima do limite de 300). Sem mudar comportamento, com os testes atuais verdes:

- `application/authz_sender.py` (novo): `Reply`, `CheckResult`, a parada `_Stop` (vira `StopRun`), `ReplaySender` com `send`, `baseline`, contadores de envio e de falhas seguidas, e as anotações `note`, `problem_note`, `inconclusive`.
- `application/authz_checks_read.py` (novo): `horizontal`, `excessive_data`, `vertical` (código movido).
- `application/authz_checks_mass.py` (novo): atribuição em massa e restauração (`_Pending`, `_restore`, `_after_interruption`, `_try_restore`, `_unrestored_note`, `_as_object`, `_already_sent`).
- `application/authz_runner.py`: só a orquestração (`run`, `_outcome`, `_summary`) e um mapa `CHECK_RUNNERS: dict[AuthzCheck, ...]` no lugar do `if/elif` de `_run_check`.
- `domain/authz_findings.py`: `_build` vira `build_finding` público em `domain/authz_finding_build.py` (novo), para os construtores dos próximos ADRs viverem em arquivos próprios.

**Esta implementação (0039) toca:**

- `domain/authz_config.py` (`AuthzCheck`, `CHECK_ORDER`), `domain/authz_result.py` (`AuthzTechnique`, `variants`, `AUTHZ_LIMITS`), `domain/authz_findings.py` (`TECHNIQUE_LABEL`, `_CLASS`), `domain/finding_explain.py` (duas explicações), `domain/report_labels.py` (rótulos).
- Novos: `domain/authz_token.py`, `domain/authz_anonymous.py` (plano, teto, `declared_anonymous`, severidade), `domain/authz_findings_access.py` (os dois construtores), `application/authz_checks_access.py` (as duas verificações), `application/authz_tamper.py` (`TamperedSession`).
- `application/account_session.py` (`credential()`, `AuthCredential`), `application/dispatcher.py` (`allow_reauth`), `application/authz_runner.py` e `application/authz.py` (registro das verificações, `AuthzPlans` ganha dois planos, `vault` em `AuthzSettings`, `_dry_outcome` e `_all_checks` incluem as novas).
- Documentação: `docs/reference/authz.md`, `docs/reference/target-yml.md` (nada novo no perfil: só citar os dois nomes em `disabled_checks`), e o relato em `docs/reviews`. `CHANGELOG.md` e `docs/adr/README.md` são do coordenador.
- Testes: os listados acima mais `tests/fakes/authz_rig.py` (alvo falso que distingue "sem cabeçalho", "token inválido" e "token válido", e conta logins).

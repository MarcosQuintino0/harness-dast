# `hdast authz`: teste de autorização entre contas

Decisões: [ADR 0041](../adr/0041-tabela-quem-pode-o-que.md) (tabela "quem pode o quê"), [ADR 0027](../adr/0027-teste-de-autorizacao-entre-contas.md), [ADR 0042](../adr/0042-escrita-em-recurso-de-outra-conta-e-id-fora-do-caminho.md) (escrita em recurso de outra conta e identificador na consulta), [ADR 0040](../adr/0040-candidatos-de-campo-proibido-do-openapi.md) (campos da atribuição em massa tirados do OpenAPI e `POST`), [ADR 0040](../adr/0040-candidatos-de-campo-proibido-do-openapi.md) (campos da atribuição em massa tirados do OpenAPI e `POST`), [ADR 0039](../adr/0039-pedido-sem-login-e-token-adulterado.md) (pedido sem login e token adulterado) e [ADR 0038](../adr/0038-authz-padrao-no-run-e-escrita-pela-carta.md) (estágio ligado por padrão no `run` e escrita só com a carta). O ZAP varre uma requisição por vez, com uma identidade, e não conhece o esquema de resposta do produto; por isso não acha BOLA, BFLA, atribuição em massa nem exposição excessiva de dados. O `authz` é um estágio **determinístico, sem ZAP**, que roda depois do `probe` e repete com outras contas, **sem login** e **com o token adulterado** os pedidos que o `probe` já provou com sucesso.

```bash
uv run hdast --json authz meu-produto --run <run_id do probe>
uv run hdast authz meu-produto --run <run_id> --dry-run                  # só o plano e o que não pode ser testado
uv run hdast authz meu-produto --run <run_id> --check horizontal         # só uma verificação (repetível)
uv run hdast authz meu-produto --draft-matrix [--run <run_id>]            # rascunho da tabela quem pode o quê (não envia nada)
uv run hdast run meu-produto                                             # dentro do run: depois do scan, antes do report (ligado por padrão)
uv run hdast run meu-produto --no-authz                                  # pula o estágio (é redução)
```

**No `run` o estágio vem ligado** (ADR 0038) e, por padrão, só LÊ: `horizontal`, `excessive_data`, `anonymous_access`, `tampered_token` e `vertical` restrita a `GET` e `HEAD`. A flag `--authz` continua aceita por compatibilidade e não muda nada. Com `--skip-scan` o estágio fica `skipped`. Sem contas ou pedidos suficientes ele **não derruba o `run`**: cada verificação que não pôde rodar vai para `not_tested` com o motivo.

| Flag | Efeito |
| --- | --- |
| `--run ID` | Obrigatória, **exceto** com `--draft-matrix` (onde é opcional e só enriquece o rascunho). `run_id` de um `probe` real (com `exchanges.json`). Um `probe --dry-run` não serve |
| `--check NOME` | Roda só esta verificação (repetível): `horizontal`, `excessive_data`, `anonymous_access`, `tampered_token`, `vertical`, `access_matrix`, `mass_assignment`, `horizontal_write`. **Só reduz**: não liga o que `authz.disabled_checks` desligou. Nome desconhecido é erro de configuração (`2`) |
| `--dry-run` | Planeja (candidatos por verificação e o que fica sem teste) sem enviar nada nem gravar `authz.json` |
| `--draft-matrix` | Grava o **rascunho** da tabela "quem pode o quê" (veja a seção abaixo). Não envia nada ao alvo, não pede aprovação do escopo, não usa a pilha e não toca o `target.yml`. Não combina com `--check` nem com `--dry-run` (`CONFIG_ERROR`) |
| `--products-dir` | Pasta de produtos |

As contas vêm do perfil (`auth.accounts`), nunca de flag: o agente só cita apelidos.

## Papéis que compartilham recursos

O dono pode declarar na carta os papéis cujas contas compartilham legitimamente recursos: `attack.authz_shared_roles` é uma resposta com lista, `source: carta` e a frase em `quote`. `hdast init --from-letter` gera `authz.shared_roles`; não infira a lista. Para papel listado, `horizontal` e `horizontal_write` não comparam contas do mesmo papel e registram `shared_role` em `not_tested`. Isso é cobertura não testada, não prova de segurança; as demais verificações não mudam. A lista preenchida aparece no resumo e muda a impressão digital da aprovação; vazia preserva a anterior. Veja [ADR 0057](../adr/0057-papeis-compartilhados.md).

Para obter pares úteis, quando houver operações de leitura distintas por tipo de objeto e autorização, roteie uma leitura para cada uma de duas contas de um mesmo papel não compartilhado. `account_map` escolhe uma conta por operação e execuções separadas não se combinam.

## Escrita só com a carta (`authz.allow_writes`)

A criação de pares em `horizontal`, a atribuição em massa, a escrita em recurso de outra conta (`horizontal_write`) e os métodos de escrita (`POST`, `PUT`, `PATCH`) de `authz.vertical_methods` **escrevem no alvo** e por isso só rodam com `authz.allow_writes: true` no perfil. Esse campo nasce da carta de autorização: `attack.allow_authz_writes` do `carta.yml`, com `source: carta` e a frase da carta em `quote`, vira `authz.allow_writes: true` em `hdast init --from-letter` (e a carta pronta traz o aviso `AUTHZ_WRITES_AUTHORIZED` para a pessoa confirmar com o dono do produto). Ausente, `null`, `desconhecido` ou `false` valem `false`.

Sem `allow_writes`, em `hdast authz` e no `run`:

- `mass_assignment` e `horizontal_write` não enviam nada (nem a leitura): vão para `not_tested` com `reason: writes_not_authorized` e a mensagem "escrita não autorizada pela carta: authz.allow_writes" (o resumo da verificação sai `skipped`);
- os métodos de escrita de `vertical_methods` saem do plano (só `GET` e `HEAD` são repetidos) e `not_tested` ganha uma nota `writes_not_authorized` da verificação `vertical` dizendo quais saíram;
- `--check mass_assignment` e `--check horizontal_write` **não ligam a escrita** (flags só reduzem): o resultado é o mesmo `not_tested`, não um erro.

O bloco `authz` inteiro entra na impressão digital da aprovação humana ([ADR 0037](../adr/0037-aprovacao-humana-do-escopo.md)): ligar ou desligar `allow_writes` exige aprovar o escopo de novo.

## O que cada verificação faz

Ordem fixa. As partes que escrevem só rodam com `authz.allow_writes`; a leitura horizontal dos pedidos já provados continua funcionando sem escrita autorizada.

Com escrita autorizada, `horizontal` também pode criar um recurso para cada papel não compartilhado com duas contas, usando regras do perfil e POST provado. A conta criadora precisa conseguir lê-lo pelo GET irmão provado e pelo identificador devolvido pelo próprio POST antes de se comparar a leitura da segunda conta. Essa comparação e a atribuição em massa compartilham o teto de 400 escritas. As criações registradas entram em `created_resources`; não há DELETE. Falhas de criação, identificação ou confirmação ficam em `not_tested`. Veja o [ADR 0064](../adr/0064-par-automatico-entre-contas.md).

A comparação automática exige resposta HTTP 201 que satisfaça `probe.success` e identificador que não apareça em um GET já provado. Outros códigos de sucesso ficam `create_unconfirmed` e podem ter deixado recursos no ambiente; APIs que criam com HTTP 200 não entram nessa comparação. Mesmo 201 não prova novidade se o servidor for incoerente. As escritas desse par e da atribuição em massa têm uma tentativa por envio, inclusive restauração, para que retentativas não ultrapassem o teto.

| Verificação | Pedido repetido | Achado quando | Severidade |
| --- | --- | --- | --- |
| `horizontal` (BOLA, OWASP API1) | Cada `GET` com identificador de objeto **no caminho ou na consulta** (ADR 0042): primeiro com a conta dona (linha de base) e depois com outra conta do MESMO papel | A outra conta recebe `2xx` com corpo equivalente (sem campos voláteis) | Alta; **média** se o identificador é só de consulta e só o NOME o indica (`name_only`) |
| `excessive_data` (API3) | Cada `GET` com sucesso (reaproveita a linha de base quando há) | A resposta traz campo que o esquema de resposta do OpenAPI não declara | Média; **alta** se o NOME do campo indica segredo (senha, hash, token...) ou dado pessoal (cpf, e-mail...) |
| `anonymous_access` (API2) | Cada `GET` provado (um por operação): o mesmo alvo, **um** pedido sem credencial (sem cabeçalho de autenticação, sem cookie, sem sessão e sem novo login), depois da linha de base da conta dona | `2xx` com corpo equivalente ao autenticado | **Alta** se o OpenAPI exige autenticação na operação; **média** se não declara `security` (pode ser pública de propósito: triagem humana). CWE-306 |
| `tampered_token` (API2) | Cada `GET` provado em que o pedido sem credencial foi recusado: o token que a sessão da conta dona já tem, adulterado, sem cookie e sem novo login. JWT: até 3 pedidos (`stripped_signature`, `alg_none`, `altered_claims`); token opaco ou chave de API: 1 (`scrambled`, o texto invertido) | `2xx` com corpo equivalente ao autenticado em alguma variante (o achado lista as variantes aceitas em `variants`) | **Alta**. CWE-347 se alguma variante JWT foi aceita; CWE-287 se só `scrambled` |
| `vertical` (BFLA, API5) | Operações que uma regra EXPLÍCITA de `auth.account_map` atribui a um papel maior, com uma conta de cada papel menor (segundo `authz.role_order`) | `2xx`. Só `401` e `403` contam como negado; `400`, `404`, `409`, `422` e `5xx` são inconclusivos | Alta |
| `access_matrix` (BFLA, API5; [ADR 0041](../adr/0041-tabela-quem-pode-o-que.md)) | Para cada operação de `authz.access_matrix` e cada papel em `deny`: o MESMO pedido provado pelo `probe` (método, alvo e corpo gravados), **um** por célula, com a primeira conta desse papel (`operation_id` `authz:matrix:<operação>`) | `2xx` com um papel que a tabela proíbe. Só `401` e `403` provam a negação (`passou`); `400`, `404`, `409`, `422`, `3xx`, `5xx` e falta de resposta são `não testado` (`inconclusive`), nunca "seguro" | Alta (CWE-285). Um achado por papel que falha |
| `mass_assignment` (API3) | Cada `PUT`/`PATCH`/`POST` com corpo JSON provado pelo `probe` (os métodos testados vêm de `authz.mass_assignment_methods`): o mesmo corpo mais UM campo extra por pedido. Os campos são os de `authz.mass_assignment_fields` **mais** os que o OpenAPI sugere (veja abaixo). Se o corpo já traz o campo, o valor é trocado pelo de teste | Uma leitura seguinte (um `GET` do mesmo modelo de caminho, mesma conta; ou a própria resposta) mostra o valor injetado onde antes não estava. Cobre nome diferente (`role` entra, `papel` muda). Em `PUT`/`PATCH`, depois tenta restaurar o valor anterior; no `POST`, lê o recurso criado | **Alta** para campo declarado e classes `privilege` e `balance`; **média** para `price`, `state` e `other` |
| `horizontal_write` (BOLA de escrita, API1) | Cada `PUT`/`PATCH` provado com corpo JSON e identificador no caminho ou na consulta, com um `GET` provado do mesmo recurso (o leitor). A conta dona lê; uma conta par do mesmo papel reenvia o pedido trocando UM campo escalar de primeiro nível por um valor de teste que difere do atual; a conta dona lê de novo e depois restaura o valor anterior | O campo da conta dona passou a valer exatamente o valor de teste | Alta (CWE-639) |

**Atribuição em massa: campos do OpenAPI e `POST`** ([ADR 0040](../adr/0040-candidatos-de-campo-proibido-do-openapi.md)). Só roda com `authz.allow_writes: true`; nada disto cria outra forma de ligar a escrita, e `DELETE` nunca é enviado.

- **De onde vêm os campos.** Primeiro os declarados em `authz.mass_assignment_fields` (sempre entram, na ordem declarada). Depois, se `authz.derive_mass_candidates` for `true` (padrão), até `authz.max_derived_candidates` (padrão 6, de 1 a 20) campos por operação tirados do OpenAPI e registrados em `candidate_source` do achado: `readonly_in_input` (marcado `readOnly` no corpo de entrada), `response_only` (aparece na resposta da mesma família de caminhos, não no corpo de entrada) e `name_in_input` (campo do corpo de entrada com nome de privilégio; só a classe `privilege`, [ADR 0043](../adr/0043-defeitos-do-laboratorio-da-v1-4-proxy-e-campo-ja-aceito.md): um `valor` que o corpo normal já leva é entrada legítima). Só entram campos escalares de primeiro nível cujo **nome** cai numa classe da lista fixa do código: `privilege` (`role`, `papel`, `admin`, `plano`, `verified`...), `balance` (`saldo`, `credito`, `limite`...), `price` (`preco`, `valor`, `desconto`...), `state` (`ativo`, `pago`, `bloqueado`...) e, só em segundo plano, `other` (campo `readOnly` ou só de resposta sem classe conhecida). Ficam de fora, sempre: nome de segredo (`passwordHash`), identificador (`id`, `uuid`, o `xxxId` do próprio recurso), auditoria e voláteis (`createdAt`, `version`, `etag`...), objetos e listas. Dono do recurso (`ownerId`, `tenantId`...) **nunca é derivado**: só é testado se estiver declarado.
- **Valor de teste.** Determinístico, pelo tipo e pelo valor atual lido do recurso, nunca numa direção que tranque a conta: booleano de privilégio ou estado bom vai para `true` e estado ruim (`blocked`) para `false`; número anda um passo na direção do nome (saldo sobe, preço desce, desconto sobe) dentro de `minimum`/`maximum`; texto com `enum` usa o primeiro valor diferente do atual (em `privilege`, prefere `admin`, `root`...; em `state`, nunca um valor que bloqueia); texto sem `enum` usa `admin` (privilégio) ou `hdast-teste`. Sem valor seguro (formato, padrão, tipo estranho), o campo vai para `not_tested` com `no_safe_test_value`; valor atual já igual ao de teste, com `already_in_target_state`.
- **Limites.** Teto de 400 pedidos de escrita por execução (`budget_exhausted` no excedente); campos derivados além de `max_derived_candidates` vão para `not_tested` com `candidates_limited` e o número cortado.
- **Leitura com a conta escritora.** Se o `GET` foi provado apenas por outra conta, o `authz` o repete com a conta que escreveu; no `PUT`/`PATCH` usa o mesmo alvo concreto. A leitura anterior, a posterior e a confirmação da restauração usam a mesma conta. No `POST`, o `GET` irmão também usa a conta criadora. A cerca e os limites seguem valendo.
- **`POST` que cria recurso.** Entra quando `POST` está em `authz.mass_assignment_methods` (padrão: sim) e o `probe` provou o `POST` com corpo JSON. Testa os campos declarados e, dos derivados, só os de classe conhecida, no máximo **4** por operação. O efeito é conferido lendo o recurso criado: um `GET` irmão (`/api/medicos` e `/api/medicos/{id}`) que o `probe` provou, com o identificador que o servidor devolveu à própria requisição (cabeçalho `Location` do mesmo recurso, ou campo `id` do corpo da resposta; identificador com `/`, `..`, espaço ou mais de 64 caracteres é recusado, e `Location` de outro host é ignorado). Esse `GET` é a única exceção à regra de que o estágio só repete pedidos de `exchanges.json`, e passa pelo `ScopeGuard` como qualquer pedido. Se a leitura falha, vale a resposta do próprio `POST`. **Cada candidato testado deixa um recurso criado no ambiente de teste** (dado sintético): o `DELETE` é proibido, então quem limpa é o `hdast cleanup` ou o reset do ambiente. O número de recursos criados vai em `created_resources` do `authz.json` e numa linha do relatório. Conflito de unicidade (`409`) vira `create_conflict` com a dica de declarar o campo único em `data-rules.yml`; a verificação não gera valores novos.

**Identificador na consulta e escrita em recurso de outra conta** ([ADR 0042](../adr/0042-escrita-em-recurso-de-outra-conta-e-id-fora-do-caminho.md)).

- **Identificador na consulta (`horizontal`, só leitura, roda por padrão).** Um parâmetro de consulta do `target` que o `probe` enviou é identificador quando: (1) está declarado no OpenAPI como parâmetro `query` (o que o contrato não declara nunca é testado); (2) o nome termina em `id`, `uuid` ou `guid` (`pacienteId`, `paciente_id`), ou está em `authz.id_parameters`; ficam de fora `requestId`, `traceId`, `correlationId`, `sessionId` e os nomes voláteis; (3) o esquema é inteiro, texto com `format: uuid` ou texto sem `enum` com `maxLength` ausente ou até 64; (4) o valor enviado tem forma de identificador (até 18 dígitos, UUID ou `[A-Za-z0-9_-]{6,64}`). Valor vazio, em lista (`1,2`), repetido ou sem essa forma vai para `not_tested` com `ambiguous_identifier`. Nunca se troca o valor: a outra conta repete o MESMO pedido. O achado leva `fields: ["query:<nome>"]` (identificador de caminho segue com `fields` vazio) e a evidência cita o NOME do parâmetro e a confiança, nunca o valor: **`owned_hint`** (o mesmo valor aparece como identificador de caminho em outro pedido provado da mesma conta dona) dá severidade **alta**; **`name_only`** (só o nome indica) dá **média**, porque filtro público parecido com `?categoriaId=3` é o falso alarme típico (o remédio é `authz.public_operations`). Identificador no **corpo** de requisição não é testado nesta versão.
- **`horizontal_write` (escreve no alvo, só com `allow_writes`; é a última verificação).** Por candidato: a conta dona lê o recurso; o domínio escolhe UM campo e um valor de teste (texto: o valor atual com o sufixo `-hdast`, cabendo em `maxLength`; na falta de texto, inteiro: o valor atual mais um, ou menos um no `maximum`), nunca em campo de segredo, identificador, privilégio, saldo, preço, estado, dono ou auditoria, e só se o campo aparece na leitura com o mesmo nome e tipo (`no_detectable_field` se não há); a conta par envia o `PUT`/`PATCH` do `probe` trocando só esse campo (`operation_id` `authz:write:<operação>`); `401`, `403` e `404` são **negação** (esperado; nada mais é enviado); `400`, `409`, `422`, `5xx` e falta de resposta são `inconclusive`; com `2xx` a conta dona lê de novo e, se o campo vale exatamente o valor de teste, há achado e a dona restaura o valor anterior e confere (`restored` na evidência). **`2xx` sem efeito visível** vai para `not_tested` `accepted_without_visible_effect`: não é achado, mas **nunca é "seguro"**. Parada no meio (janela, prazo, trava, proxy) tenta a restauração pelo caminho guardado e, se não dá, grava `possible_unrestored_change`. Teto: 50 candidatos por execução (`budget_exhausted`); 2 a 5 pedidos por candidato. Nunca `DELETE`, nunca `POST`, um campo e uma conta par por vez. O valor do campo e o valor de teste nunca são gravados; a restauração é de melhor esforço (o `cleanup` e o reset do ambiente seguem sendo a garantia), e o corpo do `probe` é reenviado inteiro, então os outros campos do recurso também voltam aos valores do `probe`.

**Pedido sem login e token adulterado** (ADR 0039) só leem, não dependem de `allow_writes` e rodam por padrão. A ferramenta só REMOVE ou CORROMPE o que protege o token: nunca assina, nunca tenta chave conhecida nem confusão de algoritmo, nunca troca `sub`, papel ou `scope` (a variante `altered_claims` só acrescenta a reivindicação inofensiva `hdast`), nunca envia o token de uma conta em pedido de outra. O valor do token (original ou adulterado) nunca é gravado em artefato, log, auditoria ou mensagem, e cada valor adulterado é registrado no cofre de máscara antes de sair. Um `401` do pedido adulterado não dispara novo login nem repete o pedido (não gasta o orçamento de login). Teto por execução: 200 operações em `anonymous_access` e 100 em `tampered_token` (o resto vai para `not_tested` com `budget_exhausted`). O pedido sem credencial é feito uma vez por operação e reaproveitado pelas duas verificações; se só `tampered_token` for pedida, ele é enviado mesmo assim, para não acusar um servidor que ignora o token.

Tratamento de falso alarme e de resultado esperado: operação listada em `authz.public_operations` é ignorada (BOLA e BFLA); `401`, `403` e demais `4xx` da outra conta são o resultado esperado; `2xx` com corpo DIFERENTE não é achado (o recurso responde por quem pergunta); campos voláteis (`timestamp`, `requestId`, `traceId`, `date`, `etag`... e os de `authz.volatile_fields`) não entram na comparação; linha de base que não deu `2xx` agora vai para `not_tested`, não para "seguro"; `5xx` e falta de resposta também são `inconclusive`.

## Regras que o estágio cumpre (em código)

- Todo pedido sai pelo MESMO caminho do `probe` (`OperationDispatcher` sobre `GuardedSender`): `ScopeGuard`, `deny_paths`, métodos do escopo, `limits.requests_per_second`, janela, prazo, trava de emergência (`hdast stop`), auditoria (as linhas entram em `audit.jsonl` com `operation_id` `authz:<operação>`, continuando a numeração) e orçamento de login. Nada de HTTP por fora; cada conta loga uma vez.
- Só REPETE o que está em `exchanges.json`: não inventa caminho, não troca método e não adivinha identificador. Nunca `DELETE`.
- Nunca grava o VALOR de campo do alvo: só nomes e caminhos de campo (`items[].passwordHash`), códigos HTTP, apelidos de conta e veredito. Nenhum segredo, token ou senha aparece em artefato, log ou saída.
- Severidade e equivalência de resposta são decididas em `domain`, puras e testadas. O agente não muda severidade.
- Cinco falhas de transporte seguidas encerram o estágio (`stopped_target_unresponsive`), como no `probe`.

## Requisitos do perfil e o que o estágio diz que não pôde testar

Nada vira "verde" por falta de dado: tudo que o estágio não conseguiu testar aparece em `not_tested` com o motivo e o que fazer.

| `reason` | Quando | O que fazer |
| --- | --- | --- |
| `declared_public` | `anonymous_access` e `tampered_token`: o OpenAPI declara a operação como anônima (alguma alternativa de `security` sem esquema) | Nada: responder sem login é o esperado |
| `infrastructure_path` | `anonymous_access` e `tampered_token`: é o caminho do login, `probe.health_path` ou `probe.setup_path` | Nada: existem para responder sem sessão |
| `anonymous_already_open` | `tampered_token`: a operação responde `2xx` sem credencial; o servidor ignora o token, então adulterá-lo não diz nada | Veja o resultado de `anonymous_access` |
| `token_too_short` | `tampered_token`: o token tem menos de 2 caracteres, ou espaço ou caractere de controle, e não dá para embaralhar | Nada |
| `no_credential` | `tampered_token`: a conta dona não tem token nem chave para adulterar | Confira o login da conta (`preflight`) |
| `no_read_exchange` | `anonymous_access` e `tampered_token`: o `probe` não trouxe nenhum `GET` com sucesso | Faça o `probe` alcançar leituras (`fix-reachability`) |
| `budget_exhausted` | `anonymous_access` e `tampered_token`: passou do teto de operações por execução; `mass_assignment`: passou do teto de 400 pedidos de escrita; `horizontal_write`: passou do teto de 50 candidatos | Marque as públicas em `authz.public_operations` e rode de novo |
| `shared_role` | `horizontal` ou `horizontal_write`: o papel da conta foi declarado compartilhado na carta | Repasse que a comparação entre contas desse papel não foi feita; não é resultado aprovado |
| `no_peer_account` | Não há outra conta do mesmo papel da dona do pedido | Cadastre uma segunda conta do mesmo papel em `auth.accounts` e roteie a operação para uma delas em `auth.account_map` |
| `no_object_identifier` | `GET`, `PUT` ou `PATCH` sem identificador de objeto (no caminho ou em parâmetro de consulta declarado no OpenAPI): coleção, ou operação sobre quem chama (`/me`). Substitui `no_path_parameter` (ADR 0042) | Nada: coleções não são comparadas entre contas. Se um parâmetro de consulta identifica objeto e não termina em `id`, declare-o em `authz.id_parameters` |
| `ambiguous_identifier` | `horizontal` ou `horizontal_write`: o parâmetro de consulta parece identificador, mas o valor que o `probe` enviou é vazio, repetido, em lista ou sem forma de identificador | Ajuste o dado do `probe` (`data-rules.yml`) para enviar um identificador simples |
| `no_read_to_confirm` | `horizontal_write`: não há `GET` provado do mesmo recurso, da conta dona, para confirmar o efeito (nunca se escreve às cegas) | Faça o `probe` alcançar o `GET` do recurso |
| `no_detectable_field` | `horizontal_write`: nenhum campo escalar de primeiro nível serve de marcador (todos são segredo, identificador, privilégio, saldo, preço, estado, dono ou auditoria, ou não aparecem na leitura com o mesmo nome e tipo) | Nada |
| `accepted_without_visible_effect` | `horizontal_write`: a conta par recebeu `2xx`, mas a leitura da conta dona não mostra a mudança. Não é achado e **não é seguro** | Confira à mão se o servidor grava a escrita de outra conta |
| `public_operation` | A operação está em `authz.public_operations` (vale também para `anonymous_access` e `tampered_token`) | Nada (declarado). Se `anonymous_access` deu achado médio num endpoint público de propósito, é o remédio |
| `writes_not_authorized` | `mass_assignment` e `horizontal_write` (ou métodos de escrita de `vertical_methods`) pedido sem `authz.allow_writes` no perfil | Nada: a carta não autorizou escrita. Se o dono do produto autoriza, a pessoa registra em `attack.allow_authz_writes` da carta, gera o perfil de novo e aprova o escopo |
| `no_exchanges` | O `probe` não registrou nenhum pedido com sucesso (`exchanges.json` vazio): vale para cada verificação | Faça o `probe` alcançar operações (`fix-reachability`) |
| `exchanges_unavailable` | No estágio do `run`, `exchanges.json` ausente ou ilegível: o estágio não derruba a execução e cada verificação diz isto | Rode o `probe` de novo; o comando `hdast authz` solto recusa essa situação como erro de configuração |
| `not_reached_by_probe` | `access_matrix`: o `probe` não obteve sucesso na operação, então não há pedido provado para repetir | Faça o `probe` alcançá-la (`fix-reachability`) |
| `no_account_for_role` | `access_matrix`: nenhuma conta de `auth.accounts` tem o papel proibido | Cadastre uma conta desse papel |
| `writes_not_allowed` | `access_matrix`: o método escreve (`POST`, `PUT`, `PATCH`) e o perfil não tem `authz.allow_writes` | Nada: a carta não autorizou escrita |
| `delete_never_tested` | `access_matrix`: o método é `DELETE`, que o teste nunca envia | Nada: confira à mão |
| `nothing_to_deny` | `access_matrix`: a regra tem `deny` vazio (só documenta quem pode) | Nada |
| `not_run` | `access_matrix`: o teste parou antes de enviar o pedido desta célula | Rode de novo |
| `covered_by_access_matrix` | `vertical`: a operação tem regra em `authz.access_matrix` | Nada: a verificação `access_matrix` a testa |
| `no_role_order` | `authz.role_order` ausente (vale para toda a verificação vertical) | Declare os papéis do menor ao maior |
| `role_not_ranked` | O papel da conta dona não está em `role_order` | Inclua o papel |
| `no_lower_role_account` | Não há conta de papel menor | Cadastre uma conta de papel menor |
| `baseline_failed` | A conta dona não repetiu o pedido com sucesso agora | Rode o `probe` de novo; o recurso pode ter sido apagado ou o token expirado |
| `scope_denied` | O escopo recusou o pedido (nada foi enviado) | Nada: o escopo manda |
| `account_unavailable` | Uma conta necessária não abriu sessão | Confira o segredo da conta (`preflight`) |
| `inconclusive` | `5xx`, sem resposta, ou `4xx` ambíguo no acesso vertical | Repita; confira a saúde do alvo |
| `no_response_schema` | O OpenAPI não declara o esquema da resposta de sucesso | Declare-o no OpenAPI |
| `no_json_response` | A resposta de sucesso não é JSON | Nada |
| `no_sample_data` | A resposta de uma operação de exposição excessiva veio com lista vazia: não há item para comparar com o esquema | Faça o `probe` receber itens (por exemplo, regras de `page` e `size` em `data-rules.yml`) |
| `no_json_body` | O `probe` não guardou corpo JSON (objeto) para o `PUT`/`PATCH`/`POST` | Nada |
| `possible_unrestored_change` | A atribuição em massa enviou o campo extra e a execução parou (janela, prazo, trava, proxy) ou a restauração não foi confirmada: o valor injetado PODE ter ficado no alvo. A mensagem diz a conta e a operação | Confira o estado da conta e restaure por fora (reset do ambiente ou `cleanup`) |
| `candidates_limited` | Campos derivados do OpenAPI passaram de `authz.max_derived_candidates` (ou de 4 no `POST`); a mensagem diz quantos | Declare em `authz.mass_assignment_fields` os que importam, ou suba o limite no perfil (a pessoa aprova de novo) |
| `no_safe_test_value` | Atribuição em massa: não há valor de teste seguro para o campo (formato, padrão, tipo, limites ou `enum` do OpenAPI) | Declare o campo com um valor em `authz.mass_assignment_fields` se ele importa |
| `already_in_target_state` | Atribuição em massa: o recurso já tem o valor de teste (não dá para distinguir o efeito) | Declare o campo com outro valor |
| `create_not_readable` | `POST`: não há `GET` provado do recurso criado nem corpo de resposta declarado; testar só criaria recursos à toa | Faça o `probe` alcançar o `GET` do recurso, ou declare o corpo de resposta no OpenAPI |
| `effect_unobservable` | `POST` aceito, mas nem a leitura do recurso criado nem a resposta do `POST` mostram o efeito; **um recurso foi criado** | Confira o recurso criado e limpe (`hdast cleanup` ou reset do ambiente) |
| `create_conflict` | `POST` respondeu `409`, em geral por valor único repetido do corpo do `probe` | Declare o campo único em `data-rules.yml` para o `probe` gerar um valor por execução |
| `infrastructure_path` | Atribuição em massa: caminho de login, saúde ou preparação | Nada |
| `same_value_in_body` | O `probe` já enviou o campo extra com o valor de teste (não dá para distinguir o efeito) | Fixe o campo do `probe` com uma regra em `data-rules.yml` ou declare outro valor em `authz.mass_assignment_fields` |

## Tabela "quem pode o quê" (`authz.access_matrix`)

[ADR 0041](../adr/0041-tabela-quem-pode-o-que.md). A verificação `vertical` supõe uma escada de papéis (`role_order`) e só olha operações que uma regra explícita de `account_map` atribui a um papel maior. A tabela deixa o **dono do produto** (uma pessoa) dizer, por operação, quais papéis podem e quais **não podem**; a ferramenta testa cada "não pode" e mostra a tabela inteira no relatório. Ela **complementa** a `vertical`: a operação que a tabela cobre é pulada pela `vertical` (`covered_by_access_matrix`) quando a verificação `access_matrix` está ligada.

```yaml
authz:
  access_matrix:
    - operation: criarMedico
      allow: [admin]
      deny: [paciente, recepcao]
```

- **Declaração humana.** A ferramenta nunca a completa nem a aprova. Papel que existe em `auth.accounts` e não aparece em `allow` nem em `deny` da operação fica **`unspecified`**: não é testado e a tabela diz isso. **Nunca se presume "proibido".**
- **Métodos.** `GET` e `HEAD` rodam sempre; `POST`, `PUT` e `PATCH` só com `authz.allow_writes: true` (sem ele a célula fica `not_tested`, `writes_not_allowed`); `DELETE` **nunca** (`delete_never_tested`). Um `POST` que "falha" deixou um recurso criado por quem não podia: ele permanece no alvo (conta em `created_resources`; limpe com `hdast cleanup` ou o reset do ambiente).
- **Cerca.** Todo pedido passa pelo `ScopeGuard` como qualquer outro: `deny_paths` e escopo valem (`scope_denied`).
- **Prova que o `probe` já deu.** Se a conta que o `probe` usou tem um papel que está em `deny` da operação, a própria troca gravada prova que aquele papel executou a operação com `2xx`: a célula sai `FALHOU` com `source: probe`, **sem enviar nada**. Pode ser só roteamento do `probe` (conta padrão); a triagem humana decide.
- **Resultado de cada célula** (`AuthzResult.access_matrix`, também em `authz.json` e `findings.json.authz`): `declared_allowed`, `proved_allowed`, `passed`, `failed`, `not_tested` (com `reason` e `message`) ou `unspecified`; mais `status` (código HTTP) e `account` quando houve envio. Valor de resposta nunca entra. No relatório: subseção "Tabela quem pode o quê" ([relatorio.md](relatorio.md)).
- **Erros.** Tabela mal formada (campo extra, tipo errado, papel em `allow` e `deny`, lista com mais de 20, mais de 500 regras, regra repetida): `CONFIG_ERROR` (2). Operação fora do OpenAPI, papel sem conta, ou operação também em `public_operations`: `AUTHZ_CONFIG_INVALID` (2, sem código de saída novo), conferido onde o `authz` roda (também no `--dry-run`).
- **Aprovação.** O bloco `authz` inteiro entra na impressão digital ([ADR 0037](../adr/0037-aprovacao-humana-do-escopo.md)); a tabela é **normalizada** (a ordem das regras e dos papéis não muda a impressão digital) e a tabela vazia fica de fora (perfil antigo mantém a impressão digital e a aprovação). Mudar uma linha, por exemplo tirar um papel de `deny`, exige `hdast profile approve`, e o resumo que a pessoa lê traz a tabela **inteira**, uma linha por operação.
- **Limites.** Só proibições são testadas; um pedido por célula, com a primeira conta do papel; `404` e `400` são "não testado"; um recurso do `probe` que pertence a outra conta pode responder `403` por posse e não por papel (um "passou" não separa as duas causas; um "falhou" é seguro).

### Rascunho: `hdast authz PRODUTO --draft-matrix [--run RUN_ID]`

Quem rascunha é o agente (na integração: `onboard-product`, depois de o perfil validar, e `fix-reachability`, quando o `probe` já alcança as operações); **quem decide e aprova é uma pessoa**. O comando só lê o perfil e o OpenAPI (e, com `--run`, o `exchanges.json`); **não envia nada ao alvo**, não exige a aprovação do escopo e não usa a pilha. Grava `products/<produto>/authz-matrix.draft.yml`, um arquivo que o carregador do perfil **não lê**: um item por operação (menos as de `public_operations` e as de infraestrutura: login, saúde, preparação), com `operation`, `method`, `path`, `allow`, `deny: []` e `review: "pendente"`. O `allow` vem do que o `probe` viu com `2xx` (só com `--run`; senão vazio). **O comando nunca preenche `deny`**: o que o produto proíbe é decisão do dono. Não sobrescreve: arquivo existente é `CONFIG_ERROR`.

**O rascunho não vale nada até uma pessoa levá-lo ao perfil e aprovar.** O fluxo: o agente roda `--draft-matrix`, conversa com a pessoa sobre cada linha, a pessoa decide `allow` e `deny`, a tabela vai para `authz.access_matrix` do `target.yml` (apagando `method`, `path` e `review`: o perfil não aceita campo extra), roda-se `hdast profile validate` e **uma pessoa** roda `hdast profile approve`. O envelope traz `data.path`, `operations`, `with_run` e um aviso (`review`).

## Limites conhecidos (também em `limits` do `authz.json`)

Pedido sem login e token adulterado só em `GET`; autenticação só por cookie de sessão não é modelada (um alvo que autentica só por cookie aparece como `anonymous_access` sem achado, o que **não** prova segurança); JWT cujo conteúdo não é objeto ou com cabeçalho sem `alg` é tratado como opaco; `alg: none` escrito como `None` ou `NONE` não é coberto; `2xx` com corpo diferente não é achado. BOLA em leituras (`GET`) com identificador no caminho ou na consulta (identificador no corpo não é testado); escritas sobre recurso de outra conta só com `authz.allow_writes` ligado: `PUT` e `PATCH` (nunca `DELETE` nem `POST`), um campo escalar de primeiro nível por pedido e uma conta par, e só com um `GET` provado do mesmo recurso para confirmar; `404` na escrita conta como negação; o recurso pode mudar por outro motivo entre as duas leituras (o valor de teste é único e o tipo importa, o que torna o falso positivo improvável); a restauração é de melhor esforço; `owned_hint` só vê valores de caminho gravados pelo `probe`; identificador numérico previsível não é avaliado como risco por si; salvo isso, métodos de escrita de `authz.vertical_methods` também exigem `allow_writes`. Exposição excessiva só em respostas de `GET`. `additionalProperties` do OpenAPI não é modelado (objeto sem `properties` é tratado como livre). BFLA só em operações atribuídas por regra explícita de `auth.account_map` e nos métodos de `authz.vertical_methods` (padrão `GET`, `HEAD`). A tabela `authz.access_matrix` (ADR 0041) cobre o que a pessoa declarou: só proibições são testadas, um pedido por papel proibido e por operação (a primeira conta do papel); só `401` e `403` provam a negação; papel fora da tabela não é testado nem presumido proibido. Atribuição em massa: campos declarados mais os derivados do OpenAPI (só escalares de primeiro nível; nomes em português e inglês; `additionalProperties` não é modelado, então campo que o servidor aceita mas o OpenAPI nem lista só entra se declarado; corpo `multipart` não entra), um por pedido; a restauração é de melhor esforço e o `POST` deixa recursos criados no ambiente (o `cleanup` e o reset do ambiente seguem sendo a garantia). Achados de autorização não entram em `--compare` nem na triagem (`triage.json`). O `report` ainda exige `scan.json`: para ter `findings.json` com a seção `authz`, rode `scan` antes do `report`.

## Bloco `authz` do perfil

Opcional e aditivo na `schema_version` 1 (`allow_writes`, ADR 0038, e `derive_mass_candidates`, `max_derived_candidates` e `mass_assignment_methods`, ADR 0040, e `id_parameters`, ADR 0042, e `access_matrix`, ADR 0041, também; chave no valor padrão não muda a impressão digital da aprovação). As verificações do ADR 0039 não criam campo no perfil: `disabled_checks` e `public_operations` já as controlam. Veja [target-yml.md](target-yml.md#authz-opcional).

## `data` do envelope e `authz.json`

`authz.json` é o mesmo conteúdo do `data` do envelope.

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `schema_version`, `run_id`, `product`, `dry_run` | | Identificação |
| `status` | texto | `completed`, `stopped_window`, `stopped_deadline`, `stopped_target_unresponsive` ou `stopped_zap` |
| `stop_message` | texto ou ausente | Explicação da parada |
| `started_at`, `finished_at` | texto | ISO 8601 |
| `requests_sent` | inteiro | Requisições enviadas pelo estágio (inclui linhas de base e leituras de conferência) |
| `created_resources` | inteiro | Recursos que um `POST` de teste da atribuição em massa deixou no alvo (0 sem `POST`); `hdast cleanup` ou o reset do ambiente os remove |
| `accounts` | lista | Apelidos das contas que enviaram |
| `access_matrix` | objeto ou `null` | A tabela "quem pode o quê" com o resultado de cada célula: `{roles, rows: [{operation_id, method, path, cells: [{role, declared, result, status, account, source, reason, message}]}]}` (ADR 0041, aditivo). `null` sem tabela no perfil ou em `--dry-run` |
| `checks` | lista | Uma por verificação, na ordem fixa: `{check, status, candidates, tested, findings, message}`. `status`: `completed`, `skipped` (nada pôde ser testado ou `--dry-run`), `partial`, `disabled` (desligada ou não pedida) |
| `findings` | lista | Achados de autorização (abaixo) |
| `not_tested` | lista | `{check, operation_id, method, path, reason, message}` |
| `limits` | lista de texto | Limites conhecidos, fixos |
| `notice` | texto | Aviso fixo: zero achados não prova segurança |

Achado (`AuthzFinding`): `finding_id` (`A-` e 8 hexadecimais), `fingerprint` (SHA-256 de técnica, produto, método, modelo de caminho e campos; sem contas nem códigos HTTP), `fingerprint_version`, `origin` (sempre `authz`), `technique` (`authz_horizontal`, `authz_vertical`, `authz_excessive_data`, `authz_mass_assignment`, `authz_anonymous_access`, `authz_tampered_token`, `authz_horizontal_write`, `authz_access_matrix`), `title`, `proposed_severity`, `cwe`, `owasp_api_2023`, `operation_id`, `method`, `path_template`, `actor_account`, `actor_role`, `owner_account`, `owner_role`, `baseline_status`, `observed_status`, `fields` (caminhos de campo, só nomes; `query:<nome>` no BOLA com identificador de consulta; o campo do marcador na escrita em outra conta), `variants` (token adulterado: nomes das variantes aceitas, só nomes; fora do fingerprint; vazio nas demais técnicas), `candidate_source` (atribuição em massa: `declared`, `readonly_in_input`, `response_only` ou `name_in_input`; fora do fingerprint; `null` nas demais), `evidence` (frase sem valores), `description`, `solution`, `status` (sempre `needs_triage`).

| Técnica | CWE | Categoria OWASP API 2023 |
| --- | --- | --- |
| `authz_horizontal` | 639 | API1 Broken Object Level Authorization |
| `authz_vertical` | 285 | API5 Broken Function Level Authorization |
| `authz_excessive_data` | 213 | API3 Broken Object Property Level Authorization |
| `authz_mass_assignment` | 915 | API3 Broken Object Property Level Authorization |
| `authz_anonymous_access` | 306 | API2 Broken Authentication |
| `authz_tampered_token` | 347 (287 se só `scrambled` foi aceita) | API2 Broken Authentication |
| `authz_horizontal_write` | 639 | API1 Broken Object Level Authorization |
| `authz_access_matrix` | 285 | API5 Broken Function Level Authorization |

**Saída:** `0` quando o estágio rodou, mesmo com achados (são dado; o `report` é o dono do código `1`). `2` configuração (execução sem `exchanges.json`, `probe` simulado, outro produto, `--check` inválido, operação pública inexistente; `--draft-matrix` com rascunho já existente; `AUTHZ_CONFIG_INVALID`: tabela com operação ou papel que não existe); `3` janela fechada, autorização vencida ou prazo esgotado, inclusive no meio; `5` o proxy do ZAP caiu; `6` o alvo parou de responder. Nos casos `3`, `5` e `6` depois de começar, o envelope traz `ok: false`, `error` e `data` com o resultado parcial. Com `--dry-run`, o envelope não tem `run_id` no topo.

## `exchanges.json` (gravado pelo `probe`)

Para cada operação com sucesso (menos o login): `operation_id`, `method`, `path` (modelo), `target` (caminho concreto e consulta, relativos à `base_url`), `account`, `status`, `content_type`, `body` (só `POST`/`PUT`/`PATCH` com corpo JSON) e `omitted_fields`. O registro é descartado se um segredo registrado aparece no alvo ou no corpo, e campo de corpo com nome de segredo é removido. O corpo das respostas nunca é gravado. Os valores do corpo são dados sintéticos gerados pela ferramenta.

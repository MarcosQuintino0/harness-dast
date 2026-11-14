# `hdast authz`: teste de autorização entre contas

Decisões: [ADR 0027](../adr/0027-teste-de-autorizacao-entre-contas.md) e [ADR 0038](../adr/0038-authz-padrao-no-run-e-escrita-pela-carta.md) (estágio ligado por padrão no `run` e escrita só com a carta). O ZAP varre uma requisição por vez, com uma identidade, e não conhece o esquema de resposta do produto; por isso não acha BOLA, BFLA, atribuição em massa nem exposição excessiva de dados. O `authz` é um estágio **determinístico, sem ZAP**, que roda depois do `probe` e repete com outras contas os pedidos que o `probe` já provou com sucesso.

```bash
uv run hdast --json authz meu-produto --run <run_id do probe>
uv run hdast authz meu-produto --run <run_id> --dry-run                  # só o plano e o que não pode ser testado
uv run hdast authz meu-produto --run <run_id> --check horizontal         # só uma verificação (repetível)
uv run hdast run meu-produto                                             # dentro do run: depois do scan, antes do report (ligado por padrão)
uv run hdast run meu-produto --no-authz                                  # pula o estágio (é redução)
```

**No `run` o estágio vem ligado** (ADR 0038) e, por padrão, só LÊ: `horizontal`, `excessive_data` e `vertical` restrita a `GET` e `HEAD`. A flag `--authz` continua aceita por compatibilidade e não muda nada. Com `--skip-scan` o estágio fica `skipped`. Sem contas ou pedidos suficientes ele **não derruba o `run`**: cada verificação que não pôde rodar vai para `not_tested` com o motivo.

| Flag | Efeito |
| --- | --- |
| `--run ID` | Obrigatória. `run_id` de um `probe` real (com `exchanges.json`). Um `probe --dry-run` não serve |
| `--check NOME` | Roda só esta verificação (repetível): `horizontal`, `excessive_data`, `vertical`, `mass_assignment`. **Só reduz**: não liga o que `authz.disabled_checks` desligou. Nome desconhecido é erro de configuração (`2`) |
| `--dry-run` | Planeja (candidatos por verificação e o que fica sem teste) sem enviar nada nem gravar `authz.json` |
| `--products-dir` | Pasta de produtos |

As contas vêm do perfil (`auth.accounts`), nunca de flag: o agente só cita apelidos.

## Escrita só com a carta (`authz.allow_writes`)

A atribuição em massa e os métodos de escrita (`POST`, `PUT`, `PATCH`) de `authz.vertical_methods` **escrevem no alvo** e por isso só rodam com `authz.allow_writes: true` no perfil. Esse campo nasce da carta de autorização: `attack.allow_authz_writes` do `carta.yml`, com `source: carta` e a frase da carta em `quote`, vira `authz.allow_writes: true` em `hdast init --from-letter` (e a carta pronta traz o aviso `AUTHZ_WRITES_AUTHORIZED` para a pessoa confirmar com o dono do produto). Ausente, `null`, `desconhecido` ou `false` valem `false`.

Sem `allow_writes`, em `hdast authz` e no `run`:

- `mass_assignment` não envia nada: vai para `not_tested` com `reason: writes_not_authorized` e a mensagem "escrita não autorizada pela carta: authz.allow_writes" (o resumo da verificação sai `skipped`);
- os métodos de escrita de `vertical_methods` saem do plano (só `GET` e `HEAD` são repetidos) e `not_tested` ganha uma nota `writes_not_authorized` da verificação `vertical` dizendo quais saíram;
- `--check mass_assignment` **não liga a escrita** (flags só reduzem): o resultado é o mesmo `not_tested`, não um erro.

O bloco `authz` inteiro entra na impressão digital da aprovação humana ([ADR 0037](../adr/0037-aprovacao-humana-do-escopo.md)): ligar ou desligar `allow_writes` exige aprovar o escopo de novo.

## O que cada verificação faz

Ordem fixa, do que não escreve no alvo para o que escreve. As que escrevem (`mass_assignment` e os métodos de escrita da `vertical`) só rodam com `authz.allow_writes`.

| Verificação | Pedido repetido | Achado quando | Severidade |
| --- | --- | --- | --- |
| `horizontal` (BOLA, OWASP API1) | Cada `GET` com identificador no caminho: primeiro com a conta dona (linha de base) e depois com outra conta do MESMO papel | A outra conta recebe `2xx` com corpo equivalente (sem campos voláteis) | Alta |
| `excessive_data` (API3) | Cada `GET` com sucesso (reaproveita a linha de base quando há) | A resposta traz campo que o esquema de resposta do OpenAPI não declara | Média; **alta** se o NOME do campo indica segredo (senha, hash, token...) ou dado pessoal (cpf, e-mail...) |
| `vertical` (BFLA, API5) | Operações que uma regra EXPLÍCITA de `auth.account_map` atribui a um papel maior, com uma conta de cada papel menor (segundo `authz.role_order`) | `2xx`. Só `401` e `403` contam como negado; `400`, `404`, `409`, `422` e `5xx` são inconclusivos | Alta |
| `mass_assignment` (API3) | Cada `PUT`/`PATCH` com corpo JSON provado pelo `probe`: o mesmo corpo mais UM campo extra de `authz.mass_assignment_fields` por pedido (se o corpo já traz o campo, o valor é trocado pelo de teste) | Uma leitura seguinte (um `GET` do mesmo modelo de caminho, mesma conta; ou a própria resposta) mostra o valor injetado onde antes não estava. Cobre nome diferente (`role` entra, `papel` muda). Depois tenta restaurar o valor anterior | Alta |

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
| `no_peer_account` | Não há outra conta do mesmo papel da dona do pedido | Cadastre uma segunda conta do mesmo papel em `auth.accounts` e roteie a operação para uma delas em `auth.account_map` |
| `no_path_parameter` | `GET` sem identificador no caminho (coleção) | Nada: coleções não são comparadas entre contas |
| `public_operation` | A operação está em `authz.public_operations` | Nada (declarado) |
| `writes_not_authorized` | `mass_assignment` (ou métodos de escrita de `vertical_methods`) pedido sem `authz.allow_writes` no perfil | Nada: a carta não autorizou escrita. Se o dono do produto autoriza, a pessoa registra em `attack.allow_authz_writes` da carta, gera o perfil de novo e aprova o escopo |
| `no_exchanges` | O `probe` não registrou nenhum pedido com sucesso (`exchanges.json` vazio): vale para cada verificação | Faça o `probe` alcançar operações (`fix-reachability`) |
| `exchanges_unavailable` | No estágio do `run`, `exchanges.json` ausente ou ilegível: o estágio não derruba a execução e cada verificação diz isto | Rode o `probe` de novo; o comando `hdast authz` solto recusa essa situação como erro de configuração |
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
| `no_json_body` | O `probe` não guardou corpo JSON (objeto) para o `PUT`/`PATCH` | Nada |
| `possible_unrestored_change` | A atribuição em massa enviou o campo extra e a execução parou (janela, prazo, trava, proxy) ou a restauração não foi confirmada: o valor injetado PODE ter ficado no alvo. A mensagem diz a conta e a operação | Confira o estado da conta e restaure por fora (reset do ambiente ou `cleanup`) |
| `same_value_in_body` | O `probe` já enviou o campo extra com o valor de teste (não dá para distinguir o efeito) | Fixe o campo do `probe` com uma regra em `data-rules.yml` ou declare outro valor em `authz.mass_assignment_fields` |

## Limites conhecidos (também em `limits` do `authz.json`)

BOLA só em leituras (`GET`) com identificador no caminho; escritas sobre recurso de outra conta não são repetidas, salvo quando o perfil lista métodos de escrita em `authz.vertical_methods` **e** `authz.allow_writes` está ligado. Exposição excessiva só em respostas de `GET`. `additionalProperties` do OpenAPI não é modelado (objeto sem `properties` é tratado como livre). BFLA só em operações atribuídas por regra explícita de `auth.account_map` e nos métodos de `authz.vertical_methods` (padrão `GET`, `HEAD`). Atribuição em massa só com os campos declarados, um por pedido; a restauração é de melhor esforço (o `cleanup` e o reset do ambiente seguem sendo a garantia). Achados de autorização não entram em `--compare` nem na triagem (`triage.json`). O `report` ainda exige `scan.json`: para ter `findings.json` com a seção `authz`, rode `scan` antes do `report`.

## Bloco `authz` do perfil

Opcional e aditivo na `schema_version` 1 (`allow_writes`, ADR 0038, também). Veja [target-yml.md](target-yml.md#authz-opcional).

## `data` do envelope e `authz.json`

`authz.json` é o mesmo conteúdo do `data` do envelope.

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `schema_version`, `run_id`, `product`, `dry_run` | | Identificação |
| `status` | texto | `completed`, `stopped_window`, `stopped_deadline`, `stopped_target_unresponsive` ou `stopped_zap` |
| `stop_message` | texto ou ausente | Explicação da parada |
| `started_at`, `finished_at` | texto | ISO 8601 |
| `requests_sent` | inteiro | Requisições enviadas pelo estágio (inclui linhas de base e leituras de conferência) |
| `accounts` | lista | Apelidos das contas que enviaram |
| `checks` | lista | Uma por verificação, na ordem fixa: `{check, status, candidates, tested, findings, message}`. `status`: `completed`, `skipped` (nada pôde ser testado ou `--dry-run`), `partial`, `disabled` (desligada ou não pedida) |
| `findings` | lista | Achados de autorização (abaixo) |
| `not_tested` | lista | `{check, operation_id, method, path, reason, message}` |
| `limits` | lista de texto | Limites conhecidos, fixos |
| `notice` | texto | Aviso fixo: zero achados não prova segurança |

Achado (`AuthzFinding`): `finding_id` (`A-` e 8 hexadecimais), `fingerprint` (SHA-256 de técnica, produto, método, modelo de caminho e campos; sem contas nem códigos HTTP), `fingerprint_version`, `origin` (sempre `authz`), `technique` (`authz_horizontal`, `authz_vertical`, `authz_excessive_data`, `authz_mass_assignment`), `title`, `proposed_severity`, `cwe`, `owasp_api_2023`, `operation_id`, `method`, `path_template`, `actor_account`, `actor_role`, `owner_account`, `owner_role`, `baseline_status`, `observed_status`, `fields` (caminhos de campo, só nomes), `evidence` (frase sem valores), `description`, `solution`, `status` (sempre `needs_triage`).

| Técnica | CWE | Categoria OWASP API 2023 |
| --- | --- | --- |
| `authz_horizontal` | 639 | API1 Broken Object Level Authorization |
| `authz_vertical` | 285 | API5 Broken Function Level Authorization |
| `authz_excessive_data` | 213 | API3 Broken Object Property Level Authorization |
| `authz_mass_assignment` | 915 | API3 Broken Object Property Level Authorization |

**Saída:** `0` quando o estágio rodou, mesmo com achados (são dado; o `report` é o dono do código `1`). `2` configuração (execução sem `exchanges.json`, `probe` simulado, outro produto, `--check` inválido, operação pública inexistente); `3` janela fechada, autorização vencida ou prazo esgotado, inclusive no meio; `5` o proxy do ZAP caiu; `6` o alvo parou de responder. Nos casos `3`, `5` e `6` depois de começar, o envelope traz `ok: false`, `error` e `data` com o resultado parcial. Com `--dry-run`, o envelope não tem `run_id` no topo.

## `exchanges.json` (gravado pelo `probe`)

Para cada operação com sucesso (menos o login): `operation_id`, `method`, `path` (modelo), `target` (caminho concreto e consulta, relativos à `base_url`), `account`, `status`, `content_type`, `body` (só `POST`/`PUT`/`PATCH` com corpo JSON) e `omitted_fields`. O registro é descartado se um segredo registrado aparece no alvo ou no corpo, e campo de corpo com nome de segredo é removido. O corpo das respostas nunca é gravado. Os valores do corpo são dados sintéticos gerados pela ferramenta.

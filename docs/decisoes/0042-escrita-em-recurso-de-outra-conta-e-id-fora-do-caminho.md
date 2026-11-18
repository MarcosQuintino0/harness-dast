# 0042. Teste de autorização: escrita em recurso de outra conta e identificador fora do caminho

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** plano do ciclo V1.3 a V1.8 (versão 1.4). Estende a verificação 1 (BOLA) do [ADR 0027](0027-teste-de-autorizacao-entre-contas.md) sem alterá-lo, e fecha o limite que o próprio ADR 0027 declarou ("BOLA só em leituras (`GET`) com identificador no caminho"). Depende do ADR 0038: a parte (a) escreve no alvo e só roda com `authz.allow_writes: true`; a parte (b) só lê e roda por padrão

## Contexto

O BOLA de hoje (`domain/authz_plan.py::plan_horizontal`, `application/authz_runner.py::_horizontal`):

- Candidatos: cada `GET` provado pelo `probe` cujo **caminho** tem `{marcador}`; os demais saem com `no_path_parameter` ("coleções não são comparadas entre contas").
- Para cada candidato, a conta dona repete o pedido (linha de base, em cache por conta e alvo em `_baseline`) e até `MAX_PEERS = 2` contas do **mesmo papel** repetem o mesmo `target`. `judge_replay` + `bodies_equivalent` decidem; `2xx` com corpo equivalente é achado **alto** (CWE-639, API1:2023).

Duas lacunas: (a) a conta B nunca tenta **alterar** o recurso da conta A (`PUT`, `PATCH`), que costuma ser mais grave que ler; (b) o identificador do objeto só é reconhecido no caminho, e muitas APIs filtram por `?pacienteId=2`, `?userId=...`, `?contaId=...`.

O que o `probe` grava (`ExchangeRecord`): `operation_id`, `method`, `path` (modelo), `target` (caminho concreto **com** a consulta, relativo à `base_url`), `account`, `status`, `content_type`, `body` (só `POST`/`PUT`/`PATCH` com JSON; campo de nome de segredo removido). O corpo das respostas nunca é gravado. Para os valores "que vieram de outra resposta" o `probe` só guarda o resultado: o `target` que enviou.

## Decisão

Duas extensões da verificação horizontal, ambas sobre pedidos que o `probe` já provou, ambas por `OperationDispatcher` sobre `GuardedSender`, e nenhum `DELETE`.

### Parte (b): identificador fora do caminho (só leitura, roda por padrão)

A verificação existente `horizontal` passa a reconhecer **identificador na consulta** além do caminho. Nada é inventado: o valor testado é o que o `probe` **enviou** (e teve `2xx`); só muda a conta que o repete, como já acontece com o identificador do caminho.

**Detecção (`domain/authz_identifiers.py`, puro).** Para cada `GET` provado, `find_identifiers(operation, exchange, other_exchanges, extra_names)` devolve os `IdentifierRef` do pedido. Um parâmetro de **consulta** do `target` é identificador de objeto quando passa nas quatro condições:

1. **Existe no OpenAPI:** o nome está em `Operation.parameters` com `location == "query"` (um parâmetro que o contrato não declara nunca é testado: não se adivinha o que o servidor lê).
2. **Nome:** a última palavra do nome (separada como em `authz_sensitive._words`: camelCase, `_`, `-`) é `id`, `uuid` ou `guid` (`pacienteId`, `paciente_id`, `userUuid`), **ou** o nome está em `authz.id_parameters` (lista declarada, abaixo). Ficam de fora, mesmo terminando em `id`: os nomes de `DEFAULT_VOLATILE_FIELDS` (`requestId`, `traceId`, `correlationId`) e `sessionId`.
3. **Esquema:** inteiro; ou texto com `format: uuid`; ou texto sem `enum` com `max_length` ausente ou até 64. Parâmetro com `enum` não é identificador.
4. **Valor:** o valor presente no `target` é `^[0-9]{1,18}$`, um UUID, ou `^[A-Za-z0-9_-]{6,64}$`. Parâmetro de lista (`ids=1,2,3`, repetido) e valor vazio não entram (`not_tested` `ambiguous_identifier`).

**Confiança.** O valor do identificador é "visto pelo probe" de duas formas, e a diferença decide a severidade:

- `owned_hint`: o **mesmo valor** aparece como identificador de caminho em outro pedido provado da **mesma conta dona** (`/pacientes/2` ao lado de `/consultas?pacienteId=2`): há evidência de que o objeto 2 pertence à conta dona.
- `name_only`: só o nome indica identificador.

Achado: `2xx` com corpo equivalente à linha de base, como no caminho. **Severidade:** alta com `owned_hint`; **média** com `name_only` (filtro público parecido com `?categoriaId=3` é o falso alarme típico; o remédio é `authz.public_operations`). A decisão é função pura (`identifier_severity`) em `domain/authz_findings.py`.

**Plano.** `plan_horizontal` passa a receber as operações do OpenAPI (hoje só recebe as trocas) e a considerar candidato o `GET` com identificador no caminho **ou** na consulta (`ReplayTask` ganha `identifier: IdentifierRef | None`: `where` `path`/`query`, `name`, `confidence`). `GET` sem nenhum dos dois sai com o novo motivo `no_object_identifier` (substitui `no_path_parameter`; ver "Consequências"). O resto (`MAX_PEERS`, mesmo papel, linha de base, `public_operations`) é igual. Um `GET` com os dois (`/pacientes/{id}/consultas?medicoId=3`) continua sendo **uma** tarefa por conta par (o pedido inteiro é repetido, os dois identificadores vão juntos): o achado cita os identificadores de consulta em `fields` (`query:medicoId`) e o de caminho segue implícito, como hoje.

**Achado.** Técnica `authz_horizontal` (a mesma). `fields` fica **vazio** para identificador de caminho (mantém os fingerprints atuais) e leva `("query:<nome>",)` para identificador de consulta, de modo que a mesma operação com os dois tipos dá achados distintos. A evidência diz "identificador `pacienteId` na consulta" e a confiança (`owned_hint` ou `name_only`); nunca o valor.

**Corpo.** Identificador no **corpo** de requisição **não** é tratado como identificador novo nesta versão (ver "Alternativas"): quando o pedido provado é `PUT`/`PATCH`, o corpo inteiro (com qualquer identificador nele) é reenviado pela parte (a); um `POST` com identificador de outro recurso no corpo fica fora.

**Perfil.** Campo novo e opcional no bloco `authz`: `id_parameters: tuple[str, ...] = ()` (até 20 nomes simples, `[A-Za-z][A-Za-z0-9_]{0,63}`, sem repetição): nomes de parâmetro de consulta que o dono do produto declara como identificador de objeto mesmo sem terminar em `id` (por exemplo `cpf`, `matricula`). Declarar um nome só **acrescenta** candidatos de leitura; o `ScopeGuard` segue decidindo. Entra na impressão digital pelo bloco `authz` inteiro (ADR 0037) e some do cálculo quando vazio, pela regra de omissão de chave padrão (ADRs 0040 e 0041).

### Parte (a): escrever no recurso de outra conta (só com `allow_writes`)

Verificação nova, `horizontal_write` (nome em `AuthzCheck`), técnica `authz_horizontal_write`, **última** em `CHECK_ORDER` (`horizontal`, `excessive_data`, `anonymous_access`, `tampered_token`, `vertical`, `access_matrix`, `mass_assignment`, `horizontal_write`).

**Candidatos** (`plan_horizontal_write` em `domain/authz_plan_write.py`, puro): cada `PUT` ou `PATCH` provado, com corpo JSON objeto gravado, **com identificador de objeto no caminho ou na consulta** (as mesmas regras de (b); sem identificador a operação age sobre quem chama, como `PUT /api/me`, e vira `not_tested` `no_object_identifier`), que **não** está em `public_operations`, e para o qual existe um **leitor**: um `GET` provado do mesmo modelo de caminho e da mesma conta dona (como `plan_mass_assignment` escolhe `MassTask.read`: o de `target` igual, senão qualquer do mesmo modelo). Sem leitor: `no_read_to_confirm` (nunca se escreve às cegas). `POST` não entra (criar não é "recurso de outra conta") e **`DELETE` nunca**. A conta que escreve é **uma** conta do mesmo papel da dona (`WRITE_PEERS = 1`, a primeira par), para sujar o mínimo.

**Fluxo por candidato** (`application/authz_checks_write.py`, com o restaurador compartilhado de `application/authz_restore.py`):

1. **Leitura antes.** A conta dona lê o recurso pelo leitor (`before`, em memória). Falha: `baseline_failed`.
2. **Marcador (`domain/authz_marker.py::choose_marker`, puro).** Escolhe-se **um** campo escalar de primeiro nível do corpo provado e um valor de teste que **difere** do valor atual em `before`: texto sem `format`, `pattern` nem `enum` no esquema de entrada (o do OpenAPI, quando a operação o declara) recebe o valor atual com o sufixo `-hdast` (truncado de modo que o total caiba em `max_length`; sem espaço para o sufixo, o campo é descartado); na falta de texto, inteiro sem `enum` recebe o valor atual `+ 1` (ou `- 1` se estiver no `maximum`). **Nunca** o marcador cai num campo de nome segredo (`classify_field_name` = `secret`), identificador (`id`, `uuid`, `xxxId`), de privilégio ou propriedade (a lista `privilege`/`ownership` de `domain/authz_fields.py`, ADR 0040) nem de auditoria/volátil. O campo precisa **aparecer em `before`** com o mesmo nome (senão não haveria como confirmar); sem campo possível: `no_detectable_field`. Determinístico: mesma entrada, mesmo marcador.
3. **Escrita da conta B.** A conta par envia `PUT`/`PATCH` no `target` da dona com o corpo provado trocando só o campo do marcador (`operation_id` `authz:write:<operationId>`).
4. **Veredito do envio.** `401`, `403` ou `404` = **negou** (esperado; `tested`, sem achado, e nada mais é enviado). `400`, `409`, `422` e `5xx`, ou falta de resposta = `inconclusive` (nunca "seguro"). Na escrita `404` conta como negação (o servidor "esconde" o recurso), diferente da `vertical`, onde só `401` e `403` provam negação; um `400`/`422` pode ser só validação do marcador antes da checagem de dono. `2xx` segue.
5. **Leitura depois.** A conta **dona** lê de novo (o leitor do item 1). Se o campo agora vale **exatamente** o marcador (`holds_value`, mesmo tipo), o recurso foi alterado por quem não era o dono: **achado**.
6. **Restauração.** Se o recurso mudou, a conta **dona** reenvia o mesmo `PUT`/`PATCH` com o valor anterior daquele campo (a leitura do item 1), lê de novo e confere que o marcador saiu; o resultado (restaurado ou não) vai para o achado (`restored`). Se não se confirma ou se a execução parou depois da escrita da conta B (janela, prazo, trava, ZAP, alvo sem resposta), o `not_tested` `possible_unrestored_change` diz a conta, a operação e o campo e manda restaurar por fora (reset do ambiente ou `cleanup`), exatamente como a atribuição em massa de hoje (`_after_interruption`).
7. **2xx sem efeito visível.** Se a conta B recebeu `2xx` mas a leitura da dona **não** mostra o marcador, não há prova de alteração: `not_tested` `accepted_without_visible_effect` (com a mensagem de que o servidor aceitou a escrita de outra conta e vale conferir à mão). **Não** é achado (a severidade exige efeito provado), mas **não** é "seguro".

**Pedidos por candidato:** 2 a 5 (leitura antes, escrita, leitura depois, e, só se mudou, restauração e conferência). A taxa é a de `limits.requests_per_second`. Teto por execução: `MAX_WRITE_TASKS = 50` candidatos; o excedente vai para `not_tested` com `budget_exhausted`.

**Achado.** Técnica `authz_horizontal_write`: severidade **alta**, CWE 639, OWASP **API1:2023 Broken Object Level Authorization**. `actor_*` é a conta B, `owner_*` a dona, `fields` é `(campo do marcador,)`, `observed_status` o da escrita. O título e a evidência dizem "a conta B alterou o campo `nome` do recurso da conta A" (nome do campo, nunca valor) e se o valor foi restaurado. `finding_explain.py` ganha a explicação em linguagem simples.

### Efeitos comuns

- Só repete pedidos de `exchanges.json` e só muda **um** campo do corpo provado. O leitor e a restauração usam pedidos provados e a conta dona. Não há pedido novo montado a partir de resposta (esse caso é só da extensão `POST` do ADR 0040).
- Tudo que escreve: `allow_writes`. Sem ele a verificação `horizontal_write` fica `skipped` com a mensagem do ADR 0038 e **nenhum** envio acontece (nem o de leitura); `not_tested` traz uma linha de verificação inteira com `reason: "writes_not_allowed"`. A verificação `horizontal` com identificador de consulta **não** depende dele.
- Nunca `DELETE`; nunca mais de um campo por pedido; nunca mais de uma conta par.

## Campos novos

- **Perfil** (`authz`): `id_parameters` (parte b). Nenhum campo novo para (a): o liga-desliga é o `allow_writes` do ADR 0038 e `disabled_checks` (que passa a aceitar `horizontal_write`).
- **Carta:** nenhum.
- **Erros:** `id_parameters` malformado (nome inválido, repetido, mais de 20, tipo errado) é `ConfigError` (`CONFIG_ERROR`, saída 2) na leitura do perfil; operação pública inexistente continua `AUTHZ_CONFIG_INVALID` (ADR 0041).
- **`authz.json`, `findings.json`, relatórios:** `schema_version` continua 1; novo valor de `checks[].check` (`horizontal_write`) e de `technique` (`authz_horizontal_write`); `fields` com `query:<nome>`; novos `reason` (abaixo). `report.md` e `report.html` mostram pelos mapas existentes; `AUTHZ_LIMITS` troca a primeira frase ("BOLA só em leituras (GET) com identificador no caminho; escritas sobre recurso de outra conta não são repetidas") por: "BOLA em leituras (`GET`) com identificador no caminho ou na consulta; escritas só com `allow_writes` (`PUT` e `PATCH`, um campo por pedido, nunca `DELETE`); identificador no corpo não é testado".
- **Novos `reason` em `not_tested`:** `no_object_identifier`, `ambiguous_identifier`, `no_read_to_confirm`, `no_detectable_field`, `accepted_without_visible_effect`, `writes_not_allowed` (ADR 0038), `budget_exhausted`. Reaproveitados: `public_operation`, `no_peer_account`, `baseline_failed`, `scope_denied`, `account_unavailable`, `inconclusive`, `possible_unrestored_change`.

## Alternativas consideradas

- **Repetir o `PUT`/`PATCH` com a conta B sem mudar o corpo.** Se o corpo é igual ao estado atual, nada muda e a leitura não distingue "escreveu" de "ignorou". O marcador que difere do valor atual torna o efeito observável.
- **Conferir só o status `2xx` da conta B.** Muitos servidores respondem `200` a uma escrita que ignoram. Sem efeito provado não há achado; fica `accepted_without_visible_effect`.
- **Ler com a conta B depois da escrita.** Se a escrita foi negada a leitura também seria; e a leitura de B é um BOLA diferente. A dona lê.
- **Restaurar com a conta B.** Seria repetir a violação. A dona restaura com o que ela mesma provou.
- **Incluir `POST` e `DELETE`.** `POST` cria recurso, não altera o de outra conta; `DELETE` é proibido neste harness.
- **Inferir identificadores por nome sem exigir o parâmetro no OpenAPI.** Forçaria adivinhar o que o servidor lê. Descartada: o parâmetro tem de estar no contrato.
- **Trocar o valor do identificador por outro (`2` para `3`) na consulta.** É adivinhar identificador (proibido). O teste é "a **outra conta** repete o **mesmo** pedido", como no caminho.
- **Identificador no corpo (`POST /consultas {"pacienteId": 2}`).** Exige efeito de criação (resíduo sem `DELETE`) e leitura do recurso criado, e muitas vezes o corpo do `probe` carrega valores únicos. Adiada; o `PUT`/`PATCH` com corpo já é coberto por (a).
- **Severidade igual para `owned_hint` e `name_only`.** Geraria muito falso alarme em filtros públicos. A distinção custa uma função pura e dá à triagem um sinal.

## Consequências

- Passa a haver cobertura determinística de BOLA de escrita (quando a carta liga `allow_writes`) e de BOLA por filtro de consulta (por padrão). Custo: 1 a 2 requisições a mais por `GET` com identificador de consulta, e 2 a 5 por `PUT`/`PATCH` candidato.
- **Troca de nome de motivo:** `no_path_parameter` (do ADR 0027, documentado em `docs/reference/authz.md`) deixa de existir e vira `no_object_identifier`, porque a coleção sem identificador de consulta continua sem comparação, mas agora a frase correta é "sem identificador de objeto". Mudam `tests/unit/application/test_authz.py` (linha do `reasons`), `tests/unit/domain/test_authz_plan.py` (`"lista": "no_path_parameter"`), `docs/reference/authz.md` e qualquer skill que cite o motivo (`grep` antes de entregar).
- **Limites conhecidos (entram em `AUTHZ_LIMITS`):** identificador no corpo não é testado; só `PUT` e `PATCH` (nunca `DELETE`, `POST` ou `HEAD`); um campo por escrita e só de primeiro nível; precisa de um `GET` provado do mesmo recurso para confirmar; `404` na escrita conta como negação; recurso cujo estado muda por outro motivo entre a leitura antes e a depois pode mascarar ou imitar o efeito (o marcador é único e o tipo importa, o que torna o falso positivo improvável); a restauração é de melhor esforço (o `cleanup` e o reset do ambiente seguem sendo a garantia); a regra `owned_hint` só vê valores de caminho gravados pelo `probe`; identificador numérico previsível não é avaliado como risco por si.
- Contrato novo: a verificação, a técnica, `id_parameters`, `fields` com `query:`, os `reason`. Documentar em `docs/reference/authz.md` e `target-yml.md`. Provado só por teste automatizado e, depois, no laboratório (Clínica Piloto: `GET /api/consultas?pacienteId=`, `PUT /api/me`-like com id no caminho); nenhum produto real.

## Contratos de teste e casos obrigatórios

`tests/unit/domain/test_authz_identifiers.py` (novo): `pacienteId`, `paciente_id`, `userUuid` e `id` na consulta são identificador; `requestId`, `sessionId`, `page`, `size`, `status`, `sort` não; parâmetro não declarado no OpenAPI não; `enum` não; inteiro, UUID e texto até 64 sim; valor vazio, com espaço, com vírgula, com 19 dígitos, com `../` não (`ambiguous_identifier`); consulta repetida (`ids=1&ids=2`) ambígua; `id_parameters` acrescenta `cpf`; `owned_hint` quando o valor aparece como id de caminho na mesma conta, `name_only` quando aparece só em outra conta; query malformada (`%zz`, `&&`, `=`) sem exceção; severidade alta e média.

`tests/unit/domain/test_authz_plan.py` (editado): `GET` com `{id}` e com `?pacienteId=` entram; coleção sem identificador vai para `no_object_identifier`; `public_operations` e `no_peer_account` como antes.

`tests/unit/domain/test_authz_marker.py` (novo): texto, truncamento por `max_length`, sem espaço para o sufixo, inteiro e inteiro no `maximum`, campo `secret`, `id`, `role` descartados, campo ausente em `before`, `before` vazio ou lista, esquema com `format`/`pattern`/`enum` descartado, determinismo.

`tests/unit/domain/test_authz_plan_write.py` (novo): `PUT`/`PATCH` com corpo e identificador entram; `POST`, `DELETE`, `GET`, `HEAD` não; sem corpo JSON `no_json_body`; sem identificador `no_object_identifier`; sem leitor `no_read_to_confirm`; sem par `no_peer_account`; pública `public_operation`; teto `MAX_WRITE_TASKS`.

`tests/unit/application/test_authz_horizontal_query.py` (novo): servidor falso que devolve o mesmo corpo a qualquer conta em `?pacienteId=2` gera achado com `fields=("query:pacienteId",)`; que nega a outra conta não gera; `2xx` diferente não gera; achado de caminho mantém `fields=()`.

`tests/unit/application/test_authz_horizontal_write.py` e `test_authz_write_restore.py` (novos, no molde de `test_authz_restore.py`): servidor falso vulnerável (aceita a escrita de B e muda o campo) gera achado **e restaura** (a dona leu o valor anterior no fim); servidor que nega (`403`/`404`) não gera achado e a leitura depois **não** é enviada; `2xx` sem mudança vai para `accepted_without_visible_effect`; `400`/`422` `inconclusive`; sem `allow_writes` nada é enviado; **nunca `DELETE`**; um campo por pedido; a escrita passa pelo `ScopeGuard` (um `deny_paths` recusa e nada sai); janela fechada, prazo e trava **depois** da escrita de B ainda tentam a restauração pela dona e, se não dá, escrevem `possible_unrestored_change`; restauração que não se confirma (o servidor ignora o `PUT` da dona) gera o achado com `restored: false` e o `not_tested`; o valor do marcador e do campo nunca aparecem em `authz.json`.

`tests/contract/test_cli_authz.py`: `--check horizontal_write` aceito; com `allow_writes` falso o resultado é `skipped` com a mensagem e `requests_sent` não conta escrita; `--dry-run` lista os candidatos de escrita sem enviar.

Laboratório: Clínica Piloto (H5/H6/H7 do gabarito) para BOLA de leitura e de escrita; checar que o fluxo restaura o recurso.

## Divisão em tarefas

Entra **depois** do T0 do ADR 0039 e do ADR 0040 (usa `application/authz_checks_mass.py` já dividido, a regra de omissão de chave padrão e `domain/authz_fields.py`).

- Novos: `domain/authz_identifiers.py` (detecção, `IdentifierRef`, confiança), `domain/authz_marker.py`, `domain/authz_plan_write.py`, `domain/authz_findings_write.py` (construtor do achado de escrita), `application/authz_restore.py` (o restaurador comum: o `_Pending`, `_restore`, `_after_interruption`, `_try_restore` e `_unrestored_note` que hoje estão dentro de `authz_checks_mass.py` saem para cá, e a atribuição em massa passa a usá-lo; refatoração sem mudar comportamento, com `test_authz_restore.py` verde), `application/authz_checks_write.py`.
- Editados: `domain/authz_plan.py` (`plan_horizontal` recebe as operações; motivo novo), `domain/authz_config.py` (`id_parameters`, `AuthzCheck` com `horizontal_write`, `CHECK_ORDER`), `domain/authz_result.py` (`AuthzTechnique`, `AUTHZ_LIMITS`), `domain/authz_findings.py` (`TECHNIQUE_LABEL`, `_CLASS`, severidade do identificador), `application/authz_checks_read.py` (`horizontal` usa o identificador de consulta), `application/authz_runner.py` e `application/authz.py` (registro, planos, passa operações), `domain/scope_fingerprint.py` (omitir `id_parameters` vazio) e `domain/scope_approval_summary.py`, `domain/finding_explain.py`, `domain/report_labels.py`.
- Documentação: `docs/reference/authz.md` (troca `no_path_parameter`), `docs/reference/target-yml.md`.
- Testes: os listados e os dois que citam `no_path_parameter`; `tests/fakes/authz_rig.py` ganha servidor com recurso por dono, escrita vulnerável e leitura por conta.

## Adendo de implementação (versão 1.4)

Desvios e precisões ao implementar, sem mudar a decisão:

- **Onde vive o quê.** Domínio puro: `authz_identifiers.py` (`find_identifiers`, `IdentifierRef`, `IdentifierScan`, `is_identifier_name`, `query_pairs`), `authz_marker.py` (`choose_marker`, `Marker`), `authz_plan_write.py` (`WriteTask`, `plan_horizontal_write`, `MAX_WRITE_TASKS = 50`, `input_properties`) e `authz_findings_write.py` (`horizontal_write_finding`). `identifier_severity` mora em `authz_findings.py`, e o CWE/OWASP da técnica nova em `TECHNIQUE_CLASS` de `authz_finding_build.py`. `no_identifier_note` (motivos `no_object_identifier` e `ambiguous_identifier`) vive em `authz_plan.py`, junto de `skip_note`, e serve às duas verificações. Aplicação: `authz_checks_write.py` (`run_horizontal_write`) e `authz_restore.py`. `authz_plan_mass.update_reader` e `is_json_object` passaram a públicos para o plano de escrita reaproveitá-los.
- **`ReplayTask.identifiers`, não `identifier`.** O pedido pode ter mais de um identificador de consulta, então o campo é uma tupla de `IdentifierRef` (só os de consulta; o de caminho segue implícito). `IdentifierRef.confidence` é `None` no caminho. `fields` do achado leva `query:<nome>` ordenado por nome. O `plan_horizontal` recebe as operações e `authz.id_parameters` como parâmetros opcionais.
- **Severidade.** `identifier_severity(path_template, identifiers)`: alta se há marcador de caminho (mesmo com identificador de consulta junto), se não há identificador de consulta ou se algum tem `owned_hint`; média só se todos os de consulta são `name_only`. O valor é "visto" pelo `probe`: o `owned_hint` compara o valor da consulta com os valores dos marcadores de caminho dos outros pedidos provados da MESMA conta dona.
- **Forma do valor.** Esquema inteiro exige só dígitos (até 18); esquema texto aceita dígitos, UUID ou `[A-Za-z0-9_-]{6,64}` (por isso 19 dígitos num parâmetro de texto passam como texto; num inteiro são `ambiguous_identifier`). `id_parameters` só vale para parâmetro declarado no OpenAPI como `query` e não passa pelo filtro de nome (nem pela lista de nomes voláteis), mas passa pelo de esquema e de valor.
- **Motivo da escrita sem carta.** Foi reaproveitado `writes_not_authorized` (ADR 0038), não `writes_not_allowed` (o texto do ADR 0042 usava outro nome). A mensagem vive em `authz_writes.horizontal_write_blocked_note`; o resumo da verificação sai `skipped` com "escrita não autorizada pela carta".
- **Marcador.** Além de segredo, identificador (`id`, `uuid`, `guid` como última palavra), nomes de auditoria e voláteis, ficam de fora TODOS os nomes que `classify_candidate` conhece (privilégio, saldo, preço, estado e dono), não só privilégio e dono: a escrita em outra conta nunca toca em campo de valor sensível. Texto com `format`, `pattern`, `enum` ou tipo diferente de `string` no esquema de entrada é descartado; inteiro com `enum` também. O campo precisa aparecer em `before` com o mesmo nome e o MESMO tipo. Um marcador igual ao valor atual (truncamento) descarta o campo.
- **Restaurador comum.** `authz_restore.py` tem `Pending`, `restore`, `try_restore`, `after_interruption`, `unrestored_note`, `read_body`. A atribuição em massa passou a usá-lo sem mudar de comportamento nem de texto (`test_authz_restore.py` verde). A conta que restaura é sempre `exchange.account` (a dona do pedido provado). Se a escrita da outra conta tem `2xx` e a leitura de conferência falha, a dona reenvia o valor anterior e vai uma nota `inconclusive` (ou `possible_unrestored_change` se nem isso se confirma): nunca "seguro".
- **Escrita da outra conta.** `ReplaySender.send` ganhou o parâmetro `tag`; a escrita sai com `operation_id` `authz:write:<operação>`. A leitura antes é uma `GET` provada (não a linha de base em cache). `401` na escrita pode repetir o `PUT` da outra conta uma vez depois de novo login (comportamento do despachante); a negação continua sendo o veredito e nada é lido nem restaurado.
- **O que não vai para o fingerprint.** `fields` vazio no caminho mantém os fingerprints antigos (teste com o hexadecimal calculado antes da mudança). `id_parameters` vazio fica fora da impressão digital pela regra genérica de chave padrão de `scope_fingerprint._authz` (teste: perfil antigo igual, campo preenchido muda só o bloco `authz`); o resumo do `profile approve` lista os nomes quando há.
- **Limite do plano de escrita.** O teto de 50 candidatos vale no plano (uma nota `budget_exhausted` por operação excedente). O corpo do `probe` é reenviado inteiro pela conta par e pela dona, então, além do campo do marcador, os demais campos do recurso voltam aos valores do `probe` (dito em `authz.md`).
- **Não feito nesta versão.** Identificador no corpo; `POST`; `DELETE`. `--dry-run` não tem texto próprio para a escrita: mostra os candidatos na contagem da verificação.
- **Provado só por teste automatizado.** Nem o laboratório (Clínica Piloto) nem produto real foram usados nesta entrega.

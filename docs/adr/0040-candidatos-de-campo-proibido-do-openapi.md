# 0040. Atribuição em massa: candidatos de campo proibido tirados do OpenAPI e extensão para `POST`

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** plano do ciclo V1.3 a V1.8 (versão 1.4). Estende a verificação 4 do [ADR 0027](0027-teste-de-autorizacao-entre-contas.md) sem alterá-lo. Depende do ADR 0038 (toda verificação que escreve no alvo só roda com `authz.allow_writes: true`, ligado só pela carta); este ADR não muda isso e **não cria outra forma de ligar escrita**

## Contexto

A atribuição em massa de hoje (`domain/authz_plan.py::plan_mass_assignment`, `application/authz_runner.py::_mass*`) tenta só a lista de `authz.mass_assignment_fields` (padrão `role`, `papel`, `admin`, `isAdmin`; no máximo 10, `MAX_MASS_FIELDS`), só em `PUT` e `PATCH` com corpo JSON objeto provado pelo `probe` (`WRITE_METHODS`). Cada campo vai num pedido; antes lê-se o recurso (`MassTask.read`, um `GET` do mesmo modelo de caminho e conta), depois do envio lê-se de novo (ou usa-se a resposta), `injected_effect` procura o valor injetado onde antes não estava e, se achar, `_restore` devolve o valor anterior e confere.

Duas lacunas: (1) os nomes que importam variam por produto (`nivelAcesso`, `saldo`, `aprovado`, `ownerId`) e o OpenAPI **já sabe** quais campos o servidor devolve e quais ele aceita; (2) o cadastro (`POST`) é onde mais se atribui `role` e `isAdmin` em massa, e hoje não é testado.

Fatos do código: `Operation` (`domain/api_model.py`) traz `request_body` (esquema por tipo de mídia, `Schema.properties`, `read_only`), `success_responses[].body_schema`, `parameters` e `path`; `Schema` (`domain/api_schema.py`) traz `type`, `format`, `enum`, `minimum`, `maximum`, `max_length`, `pattern`, `read_only`, `flatten_schema`. `ExchangeRecord.body` guarda o corpo JSON enviado pelo `probe` (campos com nome de segredo removidos). `HttpResponse.location` existe. `classify_field_name` (`domain/authz_sensitive.py`) separa nomes em palavras (camelCase, `_`).

## Decisão

Vamos (1) derivar candidatos de campo do OpenAPI e juntá-los à lista declarada, (2) escolher o valor de teste pelo tipo e pelo valor atual lido do recurso, e (3) estender a verificação a `POST` que cria recurso. Continua **um campo por pedido**, continua **só com `allow_writes`**, continua **nunca `DELETE`**, e todo envio sai por `OperationDispatcher` sobre `GuardedSender`.

### 1. De onde vêm os candidatos (`domain/authz_candidates.py`, puro)

Para cada operação de escrita candidata, `build_candidates(operation, family, declared, config)` devolve os `Candidate` (nome, origem, tipo de campo, esquema) na ordem de prioridade. **Família do recurso:** as operações do OpenAPI cujo modelo de caminho, sem os `{marcadores}` finais, é o mesmo (`/api/medicos` e `/api/medicos/{id}` são a mesma família; `PUT /api/me` forma família sozinha com o `GET /api/me`). Esquemas lidos: o corpo de entrada da operação (`request_body.preferred()`), e os corpos de resposta de sucesso da família (`success_schema()`; `flatten_schema` no nível raiz; só campos de primeiro nível do objeto, ou do item de uma lista).

Origens, em ordem de prioridade (a primeira que se aplica define `source`):

| Origem (`source`) | Regra |
| --- | --- |
| `declared` | Está em `authz.mass_assignment_fields` (com o valor declarado; sempre entra) |
| `readonly_in_input` | A propriedade existe no esquema de entrada marcada `readOnly: true` (o contrato diz que o cliente não escreve, mas o campo está lá) |
| `response_only` | A propriedade aparece no esquema de resposta da família e **não** no esquema de entrada da operação |
| `name_in_input` | O campo está no esquema de entrada **e** o nome indica privilégio (ex.: o esquema de entrada de `/me` declara `role`): um corpo "normal" do `probe` já o carrega ou o aceita |

Um campo só vira candidato derivado se **o nome** cai numa das classes abaixo (lista fixa e testada em `domain/authz_fields.py`, palavras separadas como em `authz_sensitive._words`; comparação em minúsculas):

| Classe (`kind`) | Palavras (amostra; a lista completa fica no código) | Direção do valor |
| --- | --- | --- |
| `privilege` | `role`, `roles`, `papel`, `perfil`, `admin`, `isadmin`, `superuser`, `staff`, `permission`, `permissao`, `scope`, `group`, `grupo`, `level`, `nivel`, `tier`, `plan`, `plano`, `premium`, `vip`, `verified`, `verificado`, `approved`, `aprovado` | O valor que **concede** (veja o item 2) |
| `balance` | `saldo`, `balance`, `credit`, `credito`, `credits`, `points`, `pontos`, `limit`, `limite` | Para cima |
| `price` | `price`, `preco`, `valor`, `amount`, `discount`, `desconto` (desconto sobe; preço desce) | Favorável a quem escreve |
| `state` | Bons: `active`, `ativo`, `enabled`, `habilitado`, `paid`, `pago`. Ruins para o dono: `blocked`, `bloqueado`, `banned`, `locked`, `deleted`, `disabled`, `suspended` | Para o estado **bom** (`ativo` verdadeiro, `bloqueado` falso): nunca para o que tranca a conta |
| `ownership` | `owner`, `ownerid`, `userid`, `dono`, `tenant`, `tenantid`, `accountid`, `clinicaid`, `createdby`, `criadopor` | **Nunca derivado** (veja abaixo); só quando declarado |

Fora, sempre: campo cujo nome é segredo (`classify_field_name` = `secret`: um hash sobrescrito trancaria a conta e não há como restaurar o que não se lê), identificador do próprio recurso (`id`, `uuid`, `xxxId` igual ao último segmento do caminho), campos de auditoria e voláteis (`createdAt`, `updatedAt`, `version`, `etag` e `DEFAULT_VOLATILE_FIELDS`), objetos e listas (só escalares de primeiro nível).

**`ownership` nunca é derivado** de propósito: um servidor vulnerável que troca o dono do recurso pode tirar a própria conta do teste do acesso a ele, e a restauração (feita pela conta dona) deixaria de ser possível. Quem quiser testá-lo declara o campo em `mass_assignment_fields` sabendo o risco (já é assim hoje para qualquer nome).

`readOnly` e `response_only` **sem** classe de nome também viram candidatos, mas só com `kind: "other"` e prioridade menor, para cobrir nomes que a lista fixa não conhece. Esses ficam sujeitos ao limite do item 4.

### 2. Valor de teste (`pick_test_value`, puro)

O valor depende do esquema do campo e do valor **atual** lido do recurso (`before`, a leitura que `_mass_one` já faz). Determinístico, sem aleatoriedade, e nunca em direção que tranque a conta:

| Esquema do campo | Valor |
| --- | --- |
| Booleano, `privilege`/`state` bom | `True`; se o valor atual já é `True`, o candidato é pulado (`already_in_target_state`) |
| Booleano, `state` ruim | `False`; atual já `False` pula |
| Inteiro ou número, `balance`/`price`/`level` | Atual `+ 1` (para `discount`, preço `-1`), limitado por `minimum`/`maximum`; se não há como diferir do atual, pula (`no_safe_test_value`). Sem valor atual: `1`, ou `minimum` se maior |
| Texto com `enum` | O primeiro valor do `enum` diferente do atual; em `privilege`, prefere um de `admin`, `administrator`, `root`, `superuser`, `owner`, `staff` (sem diferenciar maiúsculas) |
| Texto sem `enum`, `privilege` | `admin` (como hoje) |
| Texto sem `enum`, outras classes e `other` | `hdast-teste`, truncado em `max_length`; **pula** quando há `format` (`date`, `uuid`, `email`...) ou `pattern` (`no_safe_test_value`) |
| Declarado | O valor declarado, sem mudança |
| Qualquer outro tipo | Pula (`no_safe_test_value`) |

### 3. Juntar com `authz.mass_assignment_fields` e limitar

Ordem final por operação: declarados (como hoje, na ordem declarada), depois derivados por prioridade (`readonly_in_input`, `response_only` e `name_in_input` entre si por classe: `privilege`, `balance`, `price`, `state`, `other`; desempate por nome), sem repetir nome (comparado normalizado: `isAdmin` = `is_admin`; o declarado vence). Os **derivados** são limitados a `authz.max_derived_candidates` por operação (padrão 6, de 1 a 20). Os declarados continuam limitados por `MAX_MASS_FIELDS` (10). O que passou do limite vai para `not_tested` (`reason: "candidates_limited"`, com o número de campos cortados). Teto da execução: `MAX_MASS_REQUESTS = 400` pedidos de escrita; o excedente de operações vai para `not_tested` (`budget_exhausted`). O ritmo é o de `limits.requests_per_second`.

### 4. Perfil (campos novos, opcionais, aditivos na `schema_version` 1)

No bloco `authz`:

- `derive_mass_candidates: bool = true`. Falso volta ao comportamento de hoje (só os declarados).
- `max_derived_candidates: int = 6` (1 a 20).
- `mass_assignment_methods: [PATCH, POST, PUT]` (subconjunto desses três, padrão os três; lista vazia é recusada). Tirar `POST` desliga a extensão do item 5.

Todos reduzem ou mantêm; nenhum amplia escopo (o `ScopeGuard` ainda decide métodos e caminhos). Entram na impressão digital do bloco `authz` do [ADR 0037](0037-aprovacao-humana-do-escopo.md) **automaticamente**: `domain/scope_fingerprint.py::_authz` faz `authz.model_dump(mode="json")` do bloco inteiro (verificado lendo o código), então qualquer campo novo do `AuthzConfig` é travado. Um efeito colateral a tratar: a chave nova no `model_dump` muda o resumo de **todos** os perfis já aprovados. Decisão: `_authz` **omite** as chaves novas quando valem o padrão (`derive_mass_candidates`, `max_derived_candidates`, `mass_assignment_methods`, e as dos ADRs 0041 e 0042 e a `allow_writes` do 0038), de modo que perfil que não as usa mantém o resumo da V1.3 e a aprovação continua valendo. Teste de contrato: o resumo de um perfil sem os campos novos é igual ao calculado pela V1.3. A linha do resumo legível (`scope_approval_summary.py::_authz_lines`) passa a mostrar o valor quando difere do padrão. **Carta:** nenhum campo novo (o bloco `authz` não é gerado pela carta, ADR 0036); a permissão de escrever continua sendo `attack.allow_authz_writes` do ADR 0038.

Erros: operação de `public_operations` e nomes de campo continuam sendo validados como hoje; valor fora da faixa ou tipo errado em qualquer campo novo é `ConfigError` (`CONFIG_ERROR`, saída 2) na leitura do perfil (pydantic, `ProfileModel` rejeita campo extra). `mass_assignment_methods` com método fora de `PATCH/POST/PUT` ou vazio: `ConfigError`.

### 5. Extensão para `POST` que cria recurso

`plan_mass_assignment` passa a aceitar `POST` quando: o método está em `mass_assignment_methods`; o `probe` provou o `POST` com `2xx` e corpo JSON objeto; a operação não é o login nem está em `public_operations`; e existe um **leitor** (abaixo). Sem leitor a operação vai para `not_tested` (`create_not_readable`).

**Como conferir o efeito.** O `POST` que cria devolve o identificador do recurso criado. O leitor é a operação `GET` da **mesma família** com um marcador final (`GET /api/medicos/{id}` para `POST /api/medicos`) que o `probe` provou (há um `ExchangeRecord` dela, o que garante que o OpenAPI, o escopo e a conta dão acesso). O identificador vem, em ordem: (1) do cabeçalho `Location` da resposta, se for caminho (ou URL da própria `base_url`) que casa com o modelo do `GET` (`domain/pathpattern.py`) e o último segmento é um identificador simples (`[A-Za-z0-9_-]{1,64}`); (2) do corpo da resposta, no campo de primeiro nível cujo nome normalizado é o do marcador do `GET` (`id`) ou `id`. Montam-se a URL do `GET` com o modelo provado e esse valor (url-codificado). Nada é adivinhado: o valor é o que o **servidor devolveu** a esta mesma requisição.

Isto é uma exceção **estreita** à regra do ADR 0027 de que o `authz` "só repete pedidos gravados em `exchanges.json`": passa a poder montar **um tipo** de pedido novo, o `GET` de leitura do recurso que ele mesmo acabou de criar, com o modelo de caminho provado pelo `probe`. O pedido passa pelo `ScopeGuard` como qualquer outro. Não se estende a outro uso.

Fluxo por candidato: `POST` com o corpo do `probe` mais o campo; se `2xx`, lê-se o recurso criado pelo leitor e `injected_effect(None, lido, nome, valor)` (sem leitura anterior: vale um caminho cujo último nome é o do campo e o valor é o injetado). Se o leitor falha ou não há identificador, vale a **resposta do próprio `POST`** (como hoje `_read(fallback=put)`); se nem ela mostra o campo, `not_tested` `effect_unobservable`, com a mensagem de que um recurso foi criado e pode ficar no alvo.

**Restauração e limpeza no `POST`.** Não há o que restaurar num recurso novo e `DELETE` é proibido. Cada candidato testado deixa **um recurso a mais** no ambiente de teste (dado sintético, como o do próprio `probe`). Por isso: (a) `POST` só testa os candidatos derivados de classe (`privilege`, `balance`, `price`, `state`) mais os declarados, nunca os `other`, e no máximo `POST_MAX_CANDIDATES = 4` por operação; (b) o número de recursos criados entra em `AuthzResult.requests_sent` e numa linha do relatório ("o teste criou N recursos; use `hdast cleanup` ou o reset do ambiente"); (c) o `not_tested` `possible_unrestored_change` não se aplica ao `POST` (nada a restaurar), mas a mensagem do achado diz que o recurso criado com o campo atribuído permanece no alvo. **Unicidade:** o corpo do `probe` leva valores únicos (e-mail, CPF...) e o servidor tende a responder `409`/`422` à repetição; isso vira `not_tested` `create_conflict` com a dica de declarar o campo único em `data-rules.yml` para o `probe` (limite conhecido: a verificação não gera valores novos; a evolução natural é um ADR próprio).

`PUT` e `PATCH` seguem como hoje (leitura do mesmo recurso, restauração por `_restore`, `possible_unrestored_change` quando não se confirma), agora com os candidatos novos. A restauração dos derivados é possível porque o valor anterior vem da leitura (o campo existe na resposta da família).

### 6. Achado, severidade e relatório

Técnica `authz_mass_assignment` (a mesma). A severidade passa a depender da classe, decidida em `domain/authz_findings.py` (nunca pelo agente): **alta** para `declared`, `privilege`, `balance`; **média** para `price`, `state` e `other` (o efeito persistiu, mas o impacto depende do negócio). Em `declared` mantém-se **alta**, como hoje. `AuthzFinding` ganha `candidate_source` (`declared`, `readonly_in_input`, `response_only`, `name_in_input`; opcional) e o título e a evidência dizem de onde veio o campo e, para `POST`, "na leitura do recurso criado" ou "na resposta do próprio POST". O fingerprint não muda de fórmula (`fields=(campo enviado, *caminhos alterados)`).

`authz.json`: `CheckSummary.candidates` conta os pares (operação, campo) planejados; novos `reason`: `candidates_limited`, `budget_exhausted`, `no_safe_test_value`, `already_in_target_state`, `create_not_readable`, `effect_unobservable`, `create_conflict`. `report.md` e `report.html` (`domain/report_authz.py`, `report_html_authz.py`) mostram `candidate_source` por achado e a linha dos recursos criados; `AUTHZ_LIMITS` troca a frase "Atribuição em massa só com os campos de `authz.mass_assignment_fields`, um por pedido" pela nova.

## Alternativas consideradas

- **Mandar todos os candidatos num só pedido.** Um servidor que recusa campo desconhecido derrubaria o teste todo (razão do ADR 0027). Mantém-se um por pedido, o que custa requisições e é limitado pelo item 3.
- **Derivar tudo que está só na resposta, sem filtro por nome.** Mandaria dezenas de campos sem interesse (`createdAt`, nomes, endereços) e sujaria o alvo. O filtro por classe de nome e o limite mantêm o custo sob controle; `other` só entra como cauda.
- **Derivar `ownership`.** Descartado: pode trancar a conta dona e impedir a restauração. Fica declarável.
- **Valor aleatório ou "fuzz" por tipo.** Sem repetibilidade e com risco de quebrar validação. Descartado em favor de valores determinísticos por classe e tipo.
- **`POST`: ler o recurso por uma listagem (`GET /api/medicos`) e procurar o recém-criado.** Depende de paginação e ordenação e pode ler recurso de outro. Descartado em favor do identificador devolvido pelo próprio `POST`.
- **`POST`: apagar o recurso criado.** `DELETE` é proibido neste harness. A limpeza é do `cleanup` e do reset do ambiente.
- **Gerar valores únicos para o `POST`.** Reimplementaria parte do `datagen` dentro do `authz`. Adiado.
- **Subir o limite de candidatos por flag da CLI.** "Flags só reduzem": o limite é do perfil (aprovado por pessoa) e nenhuma flag o amplia.

## Consequências

- Cobre os nomes de campo específicos do produto sem lista manual, e o cadastro, que hoje fica de fora. Custa mais escritas no ambiente de teste, sempre atrás de `allow_writes` e do limite por operação e por execução.
- O `authz` deixa de ser estritamente "só repete o que está em `exchanges.json`": passa a montar também o `GET` do recurso recém-criado (item 5), documentado em `AUTHZ_LIMITS`.
- Limites conhecidos: só campos de primeiro nível e escalares; `additionalProperties` não modelado (campo que o servidor aceita mas o OpenAPI nem lista só entra se declarado); a lista de nomes é em português e inglês e não cobre outros idiomas; `POST` sem `GET` irmão provado não é testado; operação com corpo `multipart` não entra (o `probe` só grava corpo JSON).
- Contrato novo: três campos do perfil, o campo `candidate_source` do achado, novos `reason`. Documentar em `docs/reference/authz.md` e `target-yml.md`.
- Provado só por teste automatizado e, depois, no laboratório; nenhum produto real.

## Contratos de teste e casos obrigatórios

`tests/unit/domain/test_authz_candidates.py` e `test_authz_fields.py` (novos):

- Família: `/api/medicos` e `/api/medicos/{id}` agrupam; `/api/me` sozinha; marcadores no meio do caminho não agrupam errado.
- Origens: campo só na resposta vira `response_only`; `readOnly` na entrada vira `readonly_in_input`; campo em ambos sem nome de privilégio não vira candidato; nome declarado vence o derivado repetido (`isAdmin` e `is_admin`).
- Exclusões: segredo (`passwordHash`), `id`, `createdAt`, `ownerId` (derivado nunca), objeto e lista, nome sem classe (só `other` com `readOnly`/`response_only`).
- Valor de teste: um caso por linha da tabela do item 2, incluindo `enum` sem valor diferente do atual, inteiro no `maximum`, texto com `format: email`, booleano já no estado alvo, ausência de valor atual, `max_length` menor que o valor de teste; dado malformado (esquema vazio, `enum` vazio, `minimum > maximum` já recusado pelo `Schema`).
- Limite: mais de `max_derived_candidates` corta e anota `candidates_limited`; ordem determinística (duas chamadas iguais).
- Severidade por classe e `declared` alto.

`tests/unit/domain/test_authz_config.py`: campos novos com padrão; `max_derived_candidates` 0 e 21 recusados; `mass_assignment_methods` vazio, com `DELETE` e com texto qualquer recusados; campo desconhecido recusado.

`tests/unit/domain/test_scope_fingerprint.py`: resumo de perfil sem campos novos igual ao da V1.3; mudar `derive_mass_candidates` muda o resumo do bloco `authz` e só dele.

`tests/unit/application/test_authz_mass_derived.py` e `test_authz_mass_post.py` (novos, com `tests/fakes/authz_rig.py`): candidato derivado aceito pelo servidor falso gera achado e restaura; candidato não aceito não gera; `PUT` sem `allow_writes` não envia nada; `POST` com `Location` lê o recurso criado; `POST` sem `Location` usa o `id` do corpo; `POST` sem leitor e sem eco vai para `create_not_readable`/`effect_unobservable`; `409` vai para `create_conflict`; `Location` de outro host é ignorado; identificador com `/`, `..` ou comprimento acima de 64 é recusado; interrupção (janela, trava) no meio de um `PUT` ainda tenta restaurar (como em `test_authz_restore.py`); `POST_MAX_CANDIDATES` respeitado; `DELETE` nunca enviado; o `GET` do recurso criado passa pelo `ScopeGuard` (um `deny_paths` o recusa e nada sai).

`tests/contract/test_cli_authz.py`: `--dry-run` lista candidatos derivados e `not_tested`; `authz.json` traz `candidate_source`.

Laboratório: Clínica Piloto (`PUT /api/me` com `role`, e um cadastro que aceita `isAdmin`).

## Divisão em tarefas

Depende de T0 do [ADR 0039](0039-pedido-sem-login-e-token-adulterado.md) (divisão do `authz_runner.py`) e deve entrar **depois** dele.

- Novos: `domain/authz_fields.py` (listas de nomes, `classify_candidate`), `domain/authz_candidates.py` (família, candidatos, `pick_test_value`), `domain/authz_plan_mass.py` (o plano de massa sai de `authz_plan.py`; ganha `POST` e o leitor), `application/authz_created_read.py` (monta o `GET` do recurso criado a partir de `Location` ou do corpo).
- Editados: `domain/authz_config.py` (três campos, validadores), `domain/authz_plan.py` (remove o plano de massa), `domain/authz_findings.py` (severidade por classe; `candidate_source`), `domain/authz_result.py` (`candidate_source`, `AUTHZ_LIMITS`), `application/authz_checks_mass.py` (laço por candidato, `POST`), `application/authz.py` (passa as operações do OpenAPI ao plano), `domain/scope_fingerprint.py` (`_authz` omite chaves com valor padrão) e `domain/scope_approval_summary.py` (`_authz_lines`), `domain/report_authz.py`, `domain/report_html_authz.py`, `domain/finding_explain.py` (texto do `authz_mass_assignment` cita a origem).
- Documentação: `docs/reference/authz.md`, `docs/reference/target-yml.md`.
- Testes: os listados; `tests/fakes/authz_rig.py` ganha um alvo falso com `POST` que cria e devolve `Location`, e campos que o servidor aceita ou ignora.
- Coordenar com o ADR 0038: a regra de omitir chaves de valor padrão em `_authz` vale também para `allow_writes`; quem entrar primeiro implementa `_authz` e o outro só acrescenta a chave à lista.

## Adendo de implementação (versão 1.4)

Desvios e precisões ao implementar, sem mudar a decisão:

- **Decisões do coordenador sobre as dúvidas do ADR.** (1) `ownership` (`ownerId`, `tenantId`...) só é testado se estiver em `authz.mass_assignment_fields`; nunca é derivado. (2) `POST` pode deixar recursos criados no ambiente de teste: até 4 derivados por operação mais os declarados; quem limpa é o `hdast cleanup` ou o reset do ambiente, e isso está dito no relatório, em `authz.md` e nas skills. (3) Gerar valores novos para fugir do `409` de unicidade fica fora desta versão: vira `create_conflict` com a dica. (4) A leitura do `GET` irmão do recurso criado é a exceção estreita descrita no item 5, com o modelo de caminho provado pelo `probe` e o identificador devolvido pelo servidor, e passa pela cerca.
- **Onde vive o quê.** Domínio puro: `authz_fields.py` (classes de nome, direção do valor, exclusões; `CandidateKind` e `CandidateSource`), `authz_candidates.py` (família, `build_candidates`, `mass_severity`; a severidade por classe mora aqui e o construtor do achado a chama, não `authz_findings.py`), `authz_test_value.py` (`pick_test_value`, separado para ficar abaixo de 300 linhas), `authz_plan_mass.py` (`MassTask`, `plan_mass_assignment`, `MAX_MASS_REQUESTS`; saiu de `authz_plan.py`, que passou a exportar `skip_note` e `unique_exchanges`) e `authz_created.py` (identificador do recurso criado e alvo do `GET`; fica no domínio por ser puro, e não em `application/authz_created_read.py` como o texto acima sugere). Aplicação: `authz_created_read.py` (envia o `GET` do recurso criado), `authz_mass_post.py` (fluxo do `POST`) e `authz_mass_common.py` (corpo do `probe`, valor atual, escolha do valor). `authz_sensitive._words` virou `field_words` (público).
- **Ordem dos derivados.** A chave de ordenação é a classe (`privilege`, `balance`, `price`, `state`, `other`), depois a origem (`readonly_in_input`, `response_only`, `name_in_input`) e por fim o nome. `name_in_input` aceita qualquer classe conhecida (não só `privilege`), mas nunca `other`. Um objeto de resposta com uma propriedade lista de objetos (`{items: [...], total, limit}`) é tratado como envelope de paginação: valem os campos do item, não os de controle.
- **Valor de teste.** Números: um passo na direção do nome (`discount` sobe, `price` desce), limitado por `minimum`/`maximum` (limite aberto recua um inteiro para dentro); inteiro com valor atual fracionário é pulado. Booleano só em `privilege` e `state`; as demais classes viram `no_safe_test_value`. Em `state` com `enum`, valores com palavra de bloqueio (`blocked`, `suspended`, `inactive`...) nunca são escolhidos. Texto de privilégio com `format` ou `pattern` também é pulado.
- **`POST`.** Sem `GET` irmão provado o plano só descarta a operação (`create_not_readable`) se ela também não declara corpo de resposta; havendo corpo, o efeito é procurado na resposta do próprio `POST`. O leitor é o `GET` provado da mesma conta cujo caminho é o do `POST` mais UM marcador final. `effect_unobservable` vale quando nenhum corpo JSON pôde ser lido (nem do recurso criado nem da resposta); um corpo legível sem o campo é "testado, sem achado". Só `409` vira `create_conflict` (`400` e `422` contam como campo recusado: podem ser justamente o campo extra). Após `409`, escopo recusado ou efeito inobservável a operação para de tentar candidatos, para não criar recursos à toa.
- **`Location` e identificador.** Em vez de `pathpattern`, o `Location` (caminho relativo ou URL que começa por `base_url` mais `/`) precisa ter o mesmo prefixo concreto e o mesmo número de segmentos do alvo do `GET` provado, e o último segmento casa `[A-Za-z0-9_-]{1,64}`; `Location` de outro host, com `..`, `%`, `\`, espaço ou acima de 2000 caracteres é ignorado. Do corpo, vale o campo de primeiro nível cujo nome normalizado é o do marcador do `GET` ou `id` (texto ou inteiro, nunca booleano). A consulta do `GET` do `probe` é descartada.
- **Teto.** `MAX_MASS_REQUESTS = 400` vale no plano (a operação que não cabe vai para `not_tested` `budget_exhausted`, uma nota por operação) e de novo no envio (contador `CheckResult.writes`, que também conta as restaurações).
- **Resultado.** `AuthzResult.created_resources` (inteiro, aditivo) guarda os recursos criados; `AuthzFinding.candidate_source` (opcional, fora do fingerprint) a origem. `CheckSummary.candidates` da atribuição em massa conta pares (operação, campo), e o `--dry-run` lista os campos e a origem em `message`. `report.md` e `report.html` mostram a origem por achado e a linha dos recursos criados.
- **Impressão digital.** `_authz` já omitia genericamente chaves novas no valor padrão (ADR 0038); a comparação passou a ser com o padrão já serializado (`model_dump` do modelo vazio), porque uma tupla padrão e a lista do JSON nunca eram iguais. O resumo do `profile approve` mostra os campos novos só quando fogem do padrão.
- **Provado só por teste automatizado.** Nem o laboratório (Clínica Piloto) nem produto real foram usados nesta entrega.

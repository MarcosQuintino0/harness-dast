# 0041. Tabela "quem pode o quê" (`authz.access_matrix`) e verificação `access_matrix`

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** plano do ciclo V1.3 a V1.8 (versão 1.4). Generaliza, sem alterar, a verificação vertical do [ADR 0027](0027-teste-de-autorizacao-entre-contas.md); usa a aprovação humana do [ADR 0037](0037-aprovacao-humana-do-escopo.md). Depende do ADR 0038 (métodos de escrita só com `authz.allow_writes`)

## Contexto

A verificação `vertical` de hoje (`domain/authz_plan.py::plan_vertical`, `application/authz_runner.py::_vertical`) só testa operações que uma regra **explícita** de `auth.account_map` atribui a um papel maior, e supõe uma **hierarquia linear** de papéis (`authz.role_order`, do menor ao maior): repete o pedido com uma conta de cada papel menor e trata `2xx` como falha (`DENIED_STATUSES = {401, 403}` são a recusa que prova negação). Isso falha em dois pontos: (1) a hierarquia nem sempre é uma escada (a recepção cadastra paciente e o médico não; o médico lê prontuário e a recepção não); (2) o que o produto **deve** permitir não está escrito em lugar nenhum que a ferramenta leia, então "o que deveria ser proibido" é adivinhação.

Queremos que o dono do produto (uma pessoa) diga, por operação, quais papéis podem e quais não podem, e que a ferramenta teste cada "não pode" e mostre a tabela inteira no relatório.

Fatos do código: `AuthzConfig` (`domain/authz_config.py`) tem `public_operations`, `role_order`, `volatile_fields`, `vertical_methods` (`GET`, `HEAD`, e `POST`/`PUT`/`PATCH` quando o perfil libera), `mass_assignment_fields` e `disabled_checks`, e `ensure_operations_exist` (confere `public_operations` contra o OpenAPI, chamado em `Authz.execute`). O papel de cada conta é `auth.accounts[].role`. `scope_fingerprint.py::_authz` (V1.3) faz `authz.model_dump(mode="json")` do bloco **inteiro**, de modo que qualquer campo novo do bloco já entra na impressão digital; `scope_approval_summary.py::_authz_lines` monta as linhas que a pessoa lê ao aprovar.

## Decisão

Vamos criar o bloco `authz.access_matrix`, a verificação `access_matrix` e a saída "tabela quem pode o quê" no relatório. A tabela é **declaração humana**: a ferramenta nunca a aprova, nunca a completa por conta própria e nunca trata o que não está nela como proibido.

### 1. O bloco do perfil

```yaml
authz:
  role_order: [paciente, medico, admin]     # continua valendo para a verificação vertical
  access_matrix:
    - operation: getConsulta                # operationId do OpenAPI
      allow: [paciente, medico]             # podem
      deny: [recepcao]                      # NÃO podem (cada um será testado)
    - operation: criarMedico
      allow: [admin]
      deny: [paciente, medico, recepcao]
```

Modelo `AccessRule` (`domain/authz_matrix.py`, `ProfileModel`: sem campo extra, congelado): `operation: str` (1 a 200 caracteres), `allow: tuple[str, ...]`, `deny: tuple[str, ...]` (cada lista com no máximo 20 papéis, sem repetição, cada papel sem espaço, como em `role_order`). `AuthzConfig.access_matrix: tuple[AccessRule, ...] = ()` (no máximo 500 regras). Validações, todas na leitura do perfil (`ConfigError`, `CONFIG_ERROR`, saída 2, mensagem com o caminho do campo e sem repetir valor de segredo):

- `allow` e `deny` não podem ter o mesmo papel; `deny` vazio é permitido (a regra só documenta quem pode) mas a linha sai sem teste (`nothing_to_deny`);
- uma regra por `operation` (repetição é erro);
- `operation` precisa existir no OpenAPI e cada papel precisa ser um `role` de alguma conta de `auth.accounts`. Isto exige o OpenAPI e as contas, então é conferido onde o `authz` já confere `public_operations` (`Authz.execute`, via `AuthzConfig.ensure_matrix_valid(operation_ids, roles)`) e no `--dry-run`; erro: classe nova `AuthzConfigError(ConfigError)`, `code = "AUTHZ_CONFIG_INVALID"`, saída 2 (nenhum código de saída novo), com `hint` que diz qual operação ou papel corrigir. `public_operations` e `access_matrix` não podem citar a mesma operação (`public_operations` vence no teste, mas declarar as duas é contradição e é erro).
- Papel que aparece em `auth.accounts` e **não** aparece nem em `allow` nem em `deny` de uma operação fica `unspecified` naquela linha: **não é testado** e a tabela diz isso. O papel ausente nunca é presumido proibido.

### 2. Quem rascunha e quem aprova

- **O agente rascunha, uma pessoa confere.** O rascunho nasce do OpenAPI (`security`, tags, nomes de operação) e do `exchanges.json`; ninguém mais o produz.
- **A CLI ajuda a rascunhar, sem tocar o perfil:** `hdast authz PRODUTO --draft-matrix [--run RUN_ID]` (flag nova do comando `authz`; `--run` é opcional neste modo e, quando dado, só enriquece o rascunho). Ele **não envia nada ao alvo**, não carrega aprovação de escopo (só lê o perfil e o OpenAPI, como o `spec inspect`), e grava `products/<produto>/authz-matrix.draft.yml`: um arquivo que o carregador do perfil **não lê** (só `target.yml`, `data-rules.yml` e `flows.yml` são lidos). Conteúdo do rascunho, um item por operação: `operation`, `method`, `path`, `allow` (os papéis cujas contas o `probe` viu com `2xx` nessa operação, quando há `--run`; senão vazio), `deny: []` e `review: "pendente"`, mais um comentário de cabeçalho dizendo que o arquivo é **hipótese** e que uma pessoa precisa decidir cada linha. O rascunho **nunca** preenche `deny`: o que o produto proíbe é decisão do dono. Sem sobrescrever: arquivo existente é `CONFIG_ERROR` (como o `init`).
- **Aprovação humana (ADR 0037), confirmada lendo o código:** `scope_fingerprint.py::_authz` faz o `model_dump` do bloco `authz` inteiro; portanto `access_matrix` entra no resumo do bloco `authz` **sem mudar** o cálculo. Mudar uma linha da tabela (por exemplo, tirar `recepcao` de `deny`, o que faria um achado sumir) muda o resumo, o `ApprovedProfileRepository` recusa com `SCOPE_NOT_APPROVED` (saída 3) e uma pessoa precisa rodar `hdast profile approve`. Dois ajustes necessários, ambos em `domain`:
  1. `_authz` passa a **normalizar** a tabela: regras ordenadas por `operation`, `allow` e `deny` ordenados (a ordem em que a pessoa escreve não muda o que é testado), e a **omitir** a chave `access_matrix` quando vazia (regra comum aos ADRs 0038, 0040 e 0042: perfil que não usa campo novo mantém o resumo da V1.3 e a aprovação continua valendo).
  2. `scope_approval_summary.py::_authz_lines` passa a listar **toda** a tabela, uma linha por operação (`operação criarMedico: podem admin; não podem paciente, medico, recepcao`), para que a pessoa **veja** o que aprova; é o `summary` que a aprovação grava. Com a tabela de 500 linhas o resumo cresce, o que é aceito (a aprovação só vale se a pessoa viu).
  A skill de integração (`onboard-product`) passa a mandar: rascunhar com `--draft-matrix`, colar no `target.yml` **depois de conversar com a pessoa**, rodar `profile validate` e pedir `profile approve` (arquivos de `.claude/` são do coordenador).
- **Carta:** nenhum campo novo. A carta registra a autorização para tocar o alvo; a tabela é conhecimento do produto, conferido pela pessoa no `profile approve`.

### 3. A verificação `access_matrix` (nome em `AuthzCheck`; técnica `authz_access_matrix`)

Ordem fixa em `CHECK_ORDER`: `horizontal`, `excessive_data`, `anonymous_access`, `tampered_token`, `vertical`, **`access_matrix`**, `mass_assignment`, `horizontal_write` (as quatro leituras antes; as que escrevem por último).

Para cada regra da tabela e cada papel em `deny`:

1. **Pedido provado:** o primeiro `ExchangeRecord` da operação em `exchanges.json` (preferindo o de uma conta cujo papel está em `allow`). Sem ele: `not_tested` `not_reached_by_probe`.
2. **Conta do papel proibido:** a primeira conta de `auth.accounts` com aquele papel. Sem conta: `no_account_for_role` (cadastre uma conta desse papel).
3. **Pedido:** o **mesmo** método, `target` e corpo gravados, enviado com essa conta, por `OperationDispatcher` sobre `GuardedSender` (`operation_id` `authz:matrix:<operationId>`). **Um pedido por célula.** Sem linha de base (como a `vertical` de hoje): o `2xx` do próprio `probe` com a conta permitida é a prova de que o pedido é válido.
4. **Veredito (`domain/authz_matrix.py`, puro):** `401` ou `403` = **passou** (negou). `2xx` = **falhou** (achado). Qualquer outro código (`400`, `404`, `409`, `422`, `3xx`, `5xx`) ou falta de resposta = **não testado** (`inconclusive`), nunca "seguro". É a regra da `vertical` (`DENIED_STATUSES`).
5. **Métodos:** `GET` e `HEAD` rodam por padrão. `POST`, `PUT` e `PATCH` só com `authz.allow_writes: true` (ADR 0038); sem ele a célula é `not_tested` com `reason: "writes_not_allowed"`. **`DELETE` nunca**: a célula é `not_tested` com `reason: "delete_never_tested"` e a tabela mostra o porquê. (O campo `authz.vertical_methods` continua só da verificação vertical.) Para `PUT` e `PATCH` o corpo reenviado é o mesmo que o `probe` provou, então um servidor que **aceitar** não altera o recurso (mesmos valores) e não há o que restaurar; para `POST` um `2xx` significa que um recurso foi criado por quem não podia: a mensagem do achado diz que ele permanece no alvo (use `hdast cleanup` ou o reset do ambiente).

**Contradição que o `probe` já provou.** Se a conta que enviou o pedido provado tem um papel que está em `deny` dessa operação, a própria troca gravada é a prova de que aquele papel executou a operação com `2xx`. A célula é marcada **falhou** (`source: "probe"`) **sem enviar nada**, com a evidência "o `probe` já obteve 2xx com a conta X do papel Y, que a tabela proíbe". Isso pode ser só roteamento do `probe` (conta padrão), mas o servidor respondeu de verdade; a triagem humana decide.

**Operações públicas:** `public_operations` e a validação do item 1 evitam duplicidade; uma linha de operação pública não existe.

### 4. Relação com `vertical`

**Complementa hoje; generaliza no futuro.** A `vertical` continua igual (nenhum teste, perfil ou relatório existente muda). Duas regras para não duplicar:

- A operação que tem regra na tabela é **pulada** pela `vertical` com `reason: "covered_by_access_matrix"` (a tabela é mais precisa: não supõe escada).
- Os achados da tabela têm técnica própria, `authz_access_matrix` (CWE 285, API5:2023 Broken Function Level Authorization, severidade **alta**), com `fields=(papel proibido,)` para que cada papel que falha seja um achado de fingerprint distinto (a `vertical` de hoje gera um achado por papel menor com o **mesmo** fingerprint; não se muda isso aqui).

Quando a tabela cobrir os produtos, um ADR futuro poderá aposentar `vertical` e `role_order`. Este ADR não decide isso.

### 5. Saída: a tabela no relatório

`AuthzResult` ganha o campo opcional `access_matrix: AccessMatrixReport | None` (`domain/authz_result.py`):

- `roles`: os papéis das colunas (os de `authz.role_order` na ordem dela, depois os demais papéis de `auth.accounts` na ordem do perfil);
- `rows`: uma por regra: `operation_id`, `method`, `path`, `cells`;
- `cells`: uma por papel: `role`, `declared` (`allow`, `deny` ou `unspecified`) e `result`:

| `result` | Significa |
| --- | --- |
| `declared_allowed` | Declarado "pode"; a ferramenta não testa permissão (só proibição) |
| `proved_allowed` | Declarado "pode" **e** o `probe` obteve `2xx` com conta desse papel |
| `passed` | Proibido e o servidor negou (`401` ou `403`) |
| `failed` | Proibido e o servidor aceitou (`2xx`), ou o `probe` já o provou |
| `not_tested` | Proibido e não deu para testar; `reason` e `message` dizem por quê |
| `unspecified` | O papel não está na regra |

e, quando houve envio, `status` (código HTTP) e `account` (apelido). Valores de resposta nunca entram.

`report.md` ganha a subseção **"Tabela quem pode o quê"** (em `domain/report_authz.py`): uma tabela em Markdown com as operações nas linhas e os papéis nas colunas; cada quadradinho é uma palavra curta (`pode`, `provado`, `passou`, `FALHOU`, `não testado: <motivo>`, `-`), com nome de operação e de papel escapados (`escape_inline`, `code_span`: vêm do OpenAPI e do perfil). Máximo de 100 linhas no Markdown, com "e mais N (veja authz.json)". `report.html` (`domain/report_html_authz.py`) mostra a mesma tabela, com a cor e o texto (nunca só cor) e as mesmas regras de escape de `html_safe`. `authz.json` e `findings.json.authz` levam a tabela inteira.

Os quadradinhos `not_tested` também entram em `AuthzResult.not_tested` (com `check: "access_matrix"`), para o que já existe (contagem, painel) continuar enxergando. `CheckSummary`: `candidates` = células `deny`; `tested` = `passed` + `failed`; `findings` = `failed`.

### 6. Validação e erros (resumo)

| Situação | Código | Saída |
| --- | --- | --- |
| Tabela mal formada (campo extra, tipo, papel com espaço, lista longa) | `CONFIG_ERROR` | 2 |
| `operation` fora do OpenAPI, papel sem conta, regra repetida, papel em `allow` e `deny`, operação também em `public_operations` | `AUTHZ_CONFIG_INVALID` | 2 |
| Perfil com a tabela alterada depois da aprovação | `SCOPE_NOT_APPROVED` | 3 |
| `--draft-matrix` com rascunho já existente | `CONFIG_ERROR` | 2 |

## Alternativas consideradas

- **Inferir a tabela do OpenAPI (`security` com escopos OAuth) e testá-la.** O OpenAPI raramente carrega papéis. Inferir é adivinhar o que deveria ser proibido e produziria falso alarme com ar de autoridade. Descartada: o OpenAPI só ajuda a **rascunhar** (`allow`).
- **Substituir a `vertical` agora.** Quebraria perfis e testes existentes e perderia o caso "atribuído por regra explícita do `account_map`" sem ganho imediato. Descartada: complementa e pula o que a tabela cobre.
- **Gravar a tabela fora do perfil (arquivo próprio) para o agente editar livremente.** Tiraria a tabela da impressão digital e permitiria ao agente esconder achados. Descartada: a tabela é do bloco `authz`, protegido pela aprovação humana.
- **Deixar a ferramenta preencher `deny` por exclusão (todo papel que não está em `allow`).** Faz o oposto do pedido: presumiria uma política que ninguém declarou. Descartada; o papel ausente é `unspecified`.
- **Testar também o "pode" (esperar `2xx` do papel permitido).** É teste funcional, não de segurança, e exige estado válido para cada papel. Fica como informação (`proved_allowed`, a partir do `probe`); não envia pedido.
- **Linha de base fresca para cada célula (como no BOLA).** Dobraria os pedidos, e aqui o que se testa é o papel, não o dono do recurso. A prova do `probe` basta (igual à `vertical`).
- **Gerar `--draft-matrix` dentro do `spec inspect`.** Misturaria o resumo do OpenAPI com uma saída que a pessoa precisa editar. Descartada: o rascunho é do `authz`, que é onde os papéis, os pedidos provados e as verificações vivem.

## Consequências

- A pessoa passa a ter um lugar único, versionado e aprovado, para dizer quem pode o quê; o relatório mostra a cobertura quadradinho a quadradinho, e "não testado" deixa de se esconder atrás de "sem achado".
- **Mais um passo humano:** preencher e aprovar a tabela. Sem tabela nada muda (a verificação roda vazia: `skipped`, `candidates: 0`, mensagem "perfil sem `authz.access_matrix`").
- Uma tabela errada por omissão gera falso "tudo passou". O relatório mostra cada linha e o `profile approve` mostra a tabela à pessoa; a confiança continua sendo humana.
- O nome do papel vem do `role` das contas; contas de papéis diferentes com o mesmo apelido de papel não se distinguem.
- **Limites conhecidos (entram em `AUTHZ_LIMITS`):** só proibições são testadas; um pedido por célula, com a primeira conta do papel; `404` e `400` são inconclusivos (um servidor que responde `404` para esconder o recurso aparece como "não testado", não como "passou"); recurso do `probe` que pertence a outra conta pode responder `403` por posse e não por papel (um "passou" não separa as duas causas; um "falhou" é seguro); escritas só com `allow_writes` e nunca `DELETE`; `POST` que "falha" deixa um recurso criado.
- Contrato novo: o bloco `access_matrix`, a verificação, a técnica, o campo `access_matrix` do resultado, `AuthzConfigError`/`AUTHZ_CONFIG_INVALID`, a flag `--draft-matrix` e o arquivo `authz-matrix.draft.yml`. Documentar em `docs/reference/authz.md`, `target-yml.md` e `cli.md`. Provado só por teste automatizado e, depois, no laboratório; nenhum produto real.

## Contratos de teste e casos obrigatórios

`tests/unit/domain/test_authz_matrix.py` (novo):

- Modelo: aceita o exemplo acima; recusa campo extra, `allow` e `deny` com o mesmo papel, papel com espaço, lista com mais de 20, `operation` vazia ou com mais de 200, mais de 500 regras, regra repetida; `deny` vazio é aceito e vira `nothing_to_deny`; tabela ausente (padrão vazio).
- `ensure_matrix_valid`: operação inexistente, papel sem conta, operação também em `public_operations` (erro `AUTHZ_CONFIG_INVALID`, mensagem sem eco do valor de segredo, nome de operação passado por `safe_identifier`).
- `plan_access_matrix`: um pedido por célula `deny`; prefere o pedido da conta de papel em `allow`; `not_reached_by_probe`, `no_account_for_role`, `writes_not_allowed` (com e sem `allow_writes`), `delete_never_tested`, `unspecified` nunca testado; contradição do `probe` vira `failed` sem envio.
- `judge_matrix_cell`: 401 e 403 `passed`; 200, 201, 204 `failed`; 301, 400, 404, 409, 422, 500, sem resposta `not_tested`.
- Tabela do relatório: ordem das colunas; célula escapada; mais de 100 linhas corta e avisa.

`tests/unit/domain/test_scope_fingerprint.py`: perfil sem `access_matrix` mantém o resumo da V1.3; reordenar regras e papéis não muda o resumo; tirar um papel de `deny` muda o resumo do bloco `authz` e **só** dele.

`tests/unit/domain/test_scope_approval_summary.py`: toda a tabela aparece no resumo, uma linha por operação.

`tests/unit/application/test_authz_matrix.py` (com `tests/fakes/authz_rig.py`): servidor falso que nega ao papel `recepcao` e aceita ao `medico` produz `passou` e `FALHOU`; `GET` roda sem `allow_writes`, `POST` não; nenhum `DELETE` sai nunca; o escopo recusa um `deny_paths` (célula `scope_denied`); `vertical` pula a operação coberta (`covered_by_access_matrix`); janela fechada no meio interrompe e devolve parcial.

`tests/contract/test_cli_authz.py`: `--draft-matrix` grava o rascunho, não toca `target.yml`, não envia pedido (contador do alvo falso em zero), não sobrescreve, não preenche `deny`; `authz.json` traz `access_matrix`; `authz` com a tabela alterada sem nova aprovação sai com `SCOPE_NOT_APPROVED`.

Laboratório: Clínica Piloto (papéis `paciente`, `medico`, `recepcao`, `admin`).

## Divisão em tarefas

Entra **depois** do T0 do ADR 0039 e, de preferência, depois dos ADRs 0040 e 0042 (usa a regra de omissão de chave padrão e a verificação de escrita já criadas por eles).

- Novos: `domain/authz_matrix.py` (`AccessRule`, `AccessMatrixReport`, plano, veredito, tabela), `domain/authz_findings_matrix.py` (construtor do achado), `application/authz_checks_matrix.py` (a verificação), `application/authz_draft.py` (caso de uso do rascunho) e a porta `AuthzDraftWriter` em `application/authz_ports.py` (fronteira com o sistema de arquivos; o adaptador vai em `adapters/reporting/run_files.py` ou num arquivo novo ao lado dele).
- Editados: `domain/authz_config.py` (`access_matrix`, `ensure_matrix_valid`, `AuthzCheck`, `CHECK_ORDER`), `domain/errors.py` ou `domain/authz_matrix.py` (`AuthzConfigError`), `domain/authz_result.py` (`AuthzTechnique`, `access_matrix`, `AUTHZ_LIMITS`), `domain/authz_findings.py` (`TECHNIQUE_LABEL`, `_CLASS`), `domain/authz_plan.py` (`vertical` pula operação coberta), `application/authz_runner.py` e `application/authz.py` (registro, plano, validação), `cli/commands/authz.py` e `cli/authz_composition.py` (`--draft-matrix`), `domain/scope_fingerprint.py` (`_authz`: ordenar e omitir), `domain/scope_approval_summary.py`, `domain/report_authz.py`, `domain/report_html_authz.py`, `domain/report_labels.py`, `domain/finding_explain.py`.
- Documentação: `docs/reference/authz.md`, `docs/reference/target-yml.md`, `docs/reference/cli.md`. O coordenador atualiza as skills (`onboard-product`, `test-product`, `run-scan`: rascunhar, conversar, aprovar) e `.claude/settings.json` (nada novo a negar: o agente pode rodar `--draft-matrix`, que não envia nada).
- Testes: os listados; `tests/fakes/authz_rig.py` ganha servidor que decide por papel.

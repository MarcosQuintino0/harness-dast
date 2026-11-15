# `hdast negative`: teste de valores que o esquema proíbe

Decisão: [ADR 0051](../adr/0051-valores-que-o-esquema-proibe.md). O OpenAPI diz o que cada campo aceita (mínimo, máximo, tamanho, `enum`, tipo, obrigatoriedade), mas a ferramenta só mandava valores **válidos** (o `probe`) e valores de ataque do ZAP (injeção). O `negative` é um estágio **determinístico, sem ZAP**, que repete os pedidos que o `probe` provou com sucesso trocando **um campo por pedido** por um valor que o contrato proíbe, e classifica a reação do servidor: rejeitar (4xx) é o esperado; aceitar (2xx) e responder 5xx são achados para triagem.

Estado desta entrega: o **comando solto** (`hdast negative`) e o **estágio do `run`** existem, com a seção "Valores que o esquema proíbe" em `findings.json`, `report.md` e `report.html` e o estágio na aba Etapas do painel. Provado só em testes com falsos; nada foi provado com Docker nem contra produto real.

## No `hdast run`

O `run` encadeia `preflight`, `probe`, `scan`, `authz`, `negative` e `report`. O estágio vem **ligado por padrão** e só **lê** (`GET`); a escrita só com `negative.allow_writes` no perfil (da carta). `--no-negative` o pula (`skipped`, "Desligado por --no-negative."; é redução) e `--negative` é aceito por compatibilidade. Com `--skip-scan` ele também fica `skipped`, com a mensagem de que roda depois do `scan`. Ele reaproveita o cache de tokens, o orçamento de login, a trava de emergência e o prazo único do `run`.

- **Falta de dado não derruba o `run`:** sem `exchanges.json` (ou vazio), o estágio devolve `not_tested` com `exchanges_unavailable` ou `no_exchanges` e o `run` segue. O comando solto continua recusando (erro de configuração).
- **Parada no meio** (janela, prazo, ZAP, alvo sem resposta): o `report` ainda roda sobre o `negative.json` parcial e a saída é a do `negative`.
- **Achado não é erro do estágio:** o `report` devolve o código `1` quando um achado dele alcança o limiar (`--fail-on` e `scan.fail_on` contam os achados do `negative`, como os do `authz`).
- **`run.json`:** o estágio `negative` entra em `stages`, `options.negative` registra o pedido e `negative_findings_by_severity` traz a contagem por severidade (ou `null` se não rodou).

## No relatório e no painel

- **`findings.json`:** seção `negative` (o mesmo conteúdo de `negative.json`, `null` se o estágio não rodou ou em relatório anterior) e `summary.negative_by_severity` (mesmas cinco chaves; `{}` sem o estágio). Os achados têm `origin: negative`, ids `N-` e as técnicas `input_accepted` e `input_server_error`. **Não** entram em `findings`, em `groups`, em `total` nem em `by_severity` (que seguem sendo do ZAP).
- **`report.md` e `report.html`:** seção própria, "Valores que o esquema proíbe (técnica própria, determinística)": estado, requisições, contas, a tabela por classe do valor e por operação (enviados, rejeitados, aceitos, 5xx, sem conclusão), os achados (campo só pelo nome, classe, limite declarado, resposta, restauração e se pode ter criado recurso), o que não foi testado e os limites. As afirmações de "o que não foi testado" ganham a de onde o estágio mexeu e onde não. O valor enviado nunca aparece.
- **Sinais da cerca (ADR 0049):** a janela de leitura da cerca inclui o fim do `negative.json`, então os 5xx e as mensagens de erro vistos nos pedidos do estágio entram nos sinais. Os dois achados (o do `negative` e o do sinal) coexistem, sem dedupe: origens diferentes, ambos `needs_triage`.
- **Painel:** a aba Etapas mostra "Valores proibidos" (estado, tempo e uma frase com os números); os achados do estágio entram na contagem do resumo e, se algum tiver severidade alta, em Falhas, sem passo a passo de reprodução (o programa não guarda o valor); "O que ficou de fora" diz quando o estágio não rodou, parou ou deixou itens sem teste. `metrics.json` traz `stages_seconds.negative`.

```bash
uv run hdast --json negative meu-produto --run <run_id do probe>
uv run hdast negative meu-produto --run <run_id> --dry-run              # só o plano e o que não pode ser testado
uv run hdast negative meu-produto --run <run_id> --only criarProduto    # só esta operação (repetível)
uv run hdast negative meu-produto --run <run_id> --max-requests 20      # teto de envios menor que o do perfil
```

| Flag | Efeito |
| --- | --- |
| `--run ID` | Obrigatória. `run_id` de um `probe` real (com `exchanges.json`). Um `probe --dry-run` não serve; `exchanges.json` ausente, ilegível ou vazio é erro de configuração (`2`) |
| `--only OPERACAO` | Testa só esta operação (`operationId`; repetível). **Só reduz.** Operação que o OpenAPI não tem é erro de configuração (`2`) |
| `--max-requests N` | Teto de envios do estágio (casos e restaurações). **Só reduz** o `negative.max_requests` do perfil: acima dele, ou menor que 1, é erro de configuração (`2`) |
| `--dry-run` | Planeja (os casos, com o limite que o OpenAPI declara, e o que fica sem teste) sem enviar nada, sem gravar `negative.json` e **sem usar a pilha** (não toma a trava de pilha) |
| `--products-dir` | Pasta de produtos |

As contas vêm do `exchanges.json` (a conta que provou cada pedido), nunca de flag.

Antes de qualquer envio o comando confere o perfil, a **aprovação do escopo** (`SCOPE_NOT_APPROVED`, saída `3`, inclusive em `--dry-run`), a autorização e a janela. Rode-o **depois do `scan`** da mesma execução: os pedidos entram no histórico do ZAP e a varredura não deve partir de um valor inválido (o `scan` escolhe a requisição que aprendeu por método e caminho e ignora o que o `negative` mandou).

## O que se envia

**Fonte do pedido válido:** `exchanges.json` do `probe` (método, modelo de caminho, alvo concreto com a consulta, conta e, em `POST`/`PUT`/`PATCH` com JSON, o corpo). **Fonte do que é proibido:** o OpenAPI da mesma operação.

Mexe-se só em **parâmetro de consulta** e em **campo de primeiro nível do corpo JSON** de `POST`, `PUT` e `PATCH`. Um campo por pedido; os demais ficam como o `probe` provou. Não se mexe em parâmetro de caminho, cabeçalho e cookie, corpo de formulário ou multipart (o `exchanges.json` não guarda o corpo: o pedido vai para `not_tested` com `unsupported_body`), campo aninhado, campo `read_only`, esquema cortado (`truncated`) nem campo cujo esquema é `oneOf`/`anyOf`. Campo cujo **nome** indica segredo, ou que o `exchanges.json` omitiu, nunca é mexido; em `PUT` e `PATCH`, o campo igual a `auth.username_field` também não (mudá-lo poderia impedir o login da conta de teste, de que a restauração depende).

| Classe | Valor enviado | Quando se aplica |
| --- | --- | --- |
| `wrong_type` | `"not-a-number"` num número, `"not-a-boolean"` num booleano, o número `12345` num texto (só no corpo; na consulta todo valor já é texto) | tipo escalar sem `enum` |
| `missing_required` | o campo é **removido** | campo obrigatório de `POST` e `PUT`, ou parâmetro de consulta obrigatório; nunca em `PATCH` |
| `below_minimum` | `minimum - 1` (o próprio `minimum`, se o limite é exclusivo) | número com `minimum` |
| `above_maximum` | `maximum + 1` (o próprio `maximum`, se exclusivo) | número com `maximum` |
| `not_in_enum` | `"not-in-enum"` num texto; o maior valor do `enum` mais 1 num número | campo com `enum` |
| `too_long` | `"a"` repetido `maxLength + 1` vezes | texto com `maxLength` de no máximo 1 000 |
| `too_short` | `"a"` repetido `minLength - 1` vezes (vazio se `minLength` é 1) | texto com `minLength` de pelo menos 1 |

Os valores são sempre ASCII simples e curtos (no máximo 1 000 caracteres), sem aspas, `<`, `%`, barra nem `..`: **não é teste de injeção** (isso é do ZAP). Cada valor é **conferido** pela validação offline de esquema ([ADR 0047](../adr/0047-validacao-offline-de-exemplos-openapi.md)) antes de existir como caso: o único código que ela devolve precisa ser o da classe. Se não for (esquema que ela não modela, `enum` junto de limite), o caso é descartado e contado em `not_tested` com `unconfirmable`: nunca se manda um valor que o próprio domínio não consegue dizer que é proibido. Formato, `pattern` e composição não são exercitados.

**Ordem e orçamento.** Por operação, os campos na ordem do esquema (consulta antes do corpo) e a classe de maior prioridade primeiro (`wrong_type`, `missing_required`, `below_minimum`, `above_maximum`, `not_in_enum`, `too_long`, `too_short`), depois uma segunda passada. Entre operações há rodízio, e as leituras vêm antes das escritas. `negative.max_cases_per_operation` (padrão 6) corta por operação e `negative.max_requests` (padrão 200, conta casos **e** restaurações) corta o total; o que o corte deixou vai para `not_tested` com `budget`. Um `POST` aceito `2` vezes na mesma operação encerra os casos dela (`created_limit`).

## Métodos e escrita

- **`GET`:** sempre (é a parte que roda por padrão). `HEAD` não entra.
- **`POST`, `PUT`, `PATCH`:** só com `negative.allow_writes: true` no perfil, que vem da **carta** (`attack.allow_invalid_input_writes`, com `source: carta` e a frase em `quote`; veja o [modelo de autorização](../guides/modelo-de-autorizacao.md)). É campo próprio: não reaproveita `authz.allow_writes` (a pergunta de lá é se o teste **entre contas** pode escrever; esta é se pode gravar dado **inválido**). Sem ele, cada pedido de escrita vai para `not_tested` com `writes_not_authorized` ("escrita não autorizada pela carta: negative.allow_writes") e **nada é enviado**. Nenhuma flag liga a escrita.
- **`DELETE` nunca.** O plano descarta o método e o domínio recusa um caso `DELETE`.

Todo pedido passa pelo mesmo caminho do `probe` e do `authz` (`OperationDispatcher` sobre `GuardedSender`): `ScopeGuard`, `deny_paths`, métodos do escopo, `limits.requests_per_second`, janela, prazo, trava de emergência (`hdast stop`), auditoria (linhas com `operation_id` `negative:<operação>`; `negative:restore:<operação>` na restauração) e orçamento de login. Escopo recusado vira `scope_denied` em `not_tested`, não erro. As repetições do despachante (429, novo login) também contam em `negative.max_requests` e nunca o passam: sem folga, a resposta 429 volta como `rate_limited`. Cinco falhas de transporte seguidas encerram o estágio (`stopped_target_unresponsive`, saída `6`).

## Reação do servidor

| Resposta | Veredito | O que vira |
| --- | --- | --- |
| 4xx, exceto os abaixo (400, 413, 415, 422...) | `rejected` | O esperado. **Não é achado**; só conta no resumo |
| 2xx | `accepted` | **Achado** `input_accepted` |
| 5xx | `server_error` | **Achado** `input_server_error` |
| 401 e 403 | `inconclusive` (`unauthorized`) | A conta perdeu a permissão; encerra os demais casos da operação |
| 404 e 410 | `inconclusive` (`not_found`) | O recurso sumiu; encerra os demais casos da operação |
| 405, 409 (`create_conflict` em `POST`), 429, 3xx, sem resposta | `inconclusive` | `not_tested`; nunca conta como seguro |

O corpo da resposta **nunca** é gravado: só o código. **Severidade proposta (do código):** em `GET`, baixa; em escrita, média, exceto aceitar `wrong_type` (que costuma ser coerção, não falta de validação), que é baixa. Todo achado é `needs_triage`. CWE-20 para "aceitou" e CWE-755 para 5xx; categoria proposta `API8:2023`.

## Restauração e criação

- **`PUT` e `PATCH`** (só com `allow_writes`): depois de cada caso que o servidor **aceitou ou respondeu com 5xx** (o estado é incerto), o estágio reenvia, com a mesma conta, o **corpo válido original** do `exchanges.json` e espera `2xx` (`restored: true` no achado). Se a restauração falhar ou não puder ser feita (janela fechada, prazo, parada), `not_tested` traz `possible_unrestored_change` com a conta e a operação e a dica "confira o estado e restaure por fora (reset do ambiente ou `hdast cleanup`)"; os demais casos dessa operação não saem (`restore_pending`). Uma parada depois do envio tenta a restauração pelo mesmo caminho guardado (com a janela fechada nada sai). Não há releitura do recurso: é um limite.
- **`POST`:** não há valor anterior e `DELETE` é proibido. Cada `POST` aceito ou com 5xx **pode** ter criado um recurso com valor inválido: conta em `created_resources` e o achado diz `created: true`. A limpeza é de uma pessoa, com `hdast cleanup` ou o reset do ambiente.

## `negative.json`

| Campo | Descrição |
| --- | --- |
| `schema_version`, `run_id`, `product`, `dry_run`, `status`, `stop_message`, `started_at`, `finished_at` | Como em `authz.json`. `status` é `completed` ou `stopped_window`, `stopped_deadline`, `stopped_zap`, `stopped_target_unresponsive` |
| `requests_sent`, `accounts` | Envios do estágio (casos e restaurações) e contas que enviaram |
| `created_resources`, `restored_resources` | `POST` aceitos que podem ter criado recurso; `PUT`/`PATCH` restaurados com sucesso |
| `by_class` | Uma linha por classe: `planned`, `sent`, `rejected`, `accepted`, `server_error`, `inconclusive` |
| `operations`, `operations_tested` | Uma linha por operação com casos enviados (mesmos contadores) e quantas foram |
| `plan` | Só na simulação: `operation_id`, `method`, `path`, `location` (`query` ou `body`), `field`, `case_class` e `declared` (o limite do OpenAPI). **Sem o valor** |
| `findings` | Achados `NegativeFinding`: `finding_id` (`N-` e 8 hexadecimais), `fingerprint` (SHA-256 de produto, técnica, método, modelo de caminho, local, campo e classe; fora: status, valor e execução), `technique`, `proposed_severity`, `cwe`, `owasp_api_2023`, `operation_id`, `method`, `path_template`, `account`, `location`, `field`, `case_class`, `declared`, `observed_status`, `baseline_status`, `restored`, `created`, `evidence`, `description`, `solution`, `status` (`needs_triage`) |
| `not_tested` | Operação, método, caminho, `reason`, `message`, e campo e classe quando o motivo é de um caso |
| `limits`, `notice` | O que o estágio não cobre e o aviso fixo: **zero achado não prova que a validação é boa** |

**O valor enviado nunca é gravado**, nem em artefato, nem em log, nem em mensagem: só a classe do caso, o NOME do campo, o limite que o contrato declara e o código HTTP. Nenhum segredo, token ou senha aparece em artefato, log ou saída.

## Motivos de `not_tested`

| `reason` | Quando |
| --- | --- |
| `writes_not_authorized` | Pedido de `POST`, `PUT` ou `PATCH` sem `negative.allow_writes` |
| `unsupported_body` | Escrita sem corpo JSON de objeto no `exchanges.json` (formulário, multipart, sem corpo) |
| `omitted_required_field` | Escrita cuja linha de base perdeu um campo obrigatório por nome de segredo (`omitted_fields`): o corpo já seria inválido e o teste daria falsa segurança |
| `infrastructure_path` | Caminho de login, saúde (`probe.health_path`) ou preparação (`probe.setup_path`) do perfil: não é operação de negócio |
| `operation_not_found` | A operação do `exchanges.json` não existe mais no OpenAPI |
| `no_testable_field` | Nenhum campo tem limite que o contrato declare e o teste consiga violar |
| `unconfirmable` | Casos descartados porque o esquema não permite confirmar que o valor é proibido |
| `budget` | Casos cortados por `max_cases_per_operation` ou por `max_requests` |
| `scope_denied` | O escopo do perfil recusou o pedido; nada foi enviado |
| `account_unavailable` | A conta do pedido não conseguiu abrir sessão |
| `unauthorized`, `not_found`, `method_not_allowed`, `conflict`, `create_conflict`, `rate_limited`, `redirect`, `no_response` | Resposta sem conclusão |
| `created_limit` | Um `POST` já criou 2 recursos com valor inválido; os demais casos da operação não saem |
| `restore_pending`, `possible_unrestored_change` | Restauração não confirmada: confira o estado do ambiente |
| `stopped` | A execução parou antes de alguns casos |
| `no_exchanges`, `exchanges_unavailable` | Sem pedido do `probe` para testar (só quando o estágio roda dentro de outra execução) |

## Códigos de saída

`0` rodou (com ou sem achado: achado é dado; quem devolve o código `1` é o `report`), `2` configuração, `3` janela, autorização, prazo ou aprovação do escopo, `5` falha do proxy do ZAP, `6` alvo sem resposta em sequência. Nenhum código de saída novo.

## Perfil e carta

O bloco `negative` do perfil está em [target-yml.md](target-yml.md#negative-opcional). Ele **entra na impressão digital** da aprovação humana quando difere do padrão: um perfil sem o bloco mantém a aprovação que já tem, e mudar qualquer campo exige aprovar de novo. O resumo de `hdast profile approve` mostra "VALORES INVÁLIDOS: até N pedidos, M por operação" e, com `allow_writes`, "ESCRITA DE VALOR INVÁLIDO AUTORIZADA".

## Limites conhecidos

- Só consulta e corpo JSON de primeiro nível, nas operações com `exchanges.json`. Caminho, cabeçalho, formulário, multipart, campo aninhado, lista, `pattern`, formato, `oneOf` e `anyOf` ficam fora.
- "Aceitou" pode ser coerção legítima (um servidor que lê `"5"` como 5) ou parâmetro ignorado. Por isso a severidade é baixa em leitura e todo achado é `needs_triage`.
- "Rejeitou" não diz que a validação é **a do esquema**: um 400 por outro motivo (CSRF, conta) também conta.
- O 5xx pode vir do estado do alvo, não do valor. Um 5xx repetido em outro campo da mesma operação é indício mais forte.
- A restauração é de melhor esforço e não relê o recurso; `POST` deixa recurso criado.
- Provado só em testes com falsos; nenhum produto real.

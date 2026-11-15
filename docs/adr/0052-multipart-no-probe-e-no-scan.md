# 0052. Envio de arquivo (`multipart/form-data`) no `probe` e no `scan`

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** plano do ciclo V1.3 a V1.8, versão 1.5 (item "envio de arquivos no alcance"); o relatório da V1.5 entregou só a detecção e a prova sintética em memória. Parte do [ADR 0048](0048-multipart-funcional-offline.md) e fala com o [ADR 0007](0007-zap-alimentado-por-requisicoes-validas.md) (o ZAP é alimentado pelo `probe`), o [ADR 0018](0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md) (o `probe` recusava multipart) e o [ADR 0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) (o `scan`).

## Contexto

Hoje uma operação que recebe arquivo não é alcançada. O `RequestBuilder` (`domain/request_builder.py`) escolhe o tipo de mídia do corpo por `RequestBody.preferred()`, monta um dicionário de campos e `encode_body` (`domain/request_encoding.py`) levanta `ConfigError` para `multipart/form-data`; o `ProbeRunner._prepare` transforma isso em `build_error`. A operação vira "não testada" no relatório e fica sem varredura: uma superfície clássica de falha (tipo e nome do arquivo, tamanho, caminho no armazenamento) fora de qualquer teste.

O ADR 0048 já mostrou que se monta e se lê um multipart sintético mínimo em memória (`domain/multipart_encoding.py`: `encode_synthetic_multipart`, `verify_synthetic_multipart`, boundary determinística, nomes ASCII seguros). Ele **não** liga isso ao envio. Falta:

1. montar o corpo a partir do esquema da operação (campos de texto e campos de arquivo);
2. enviar pelo `probe` (rota do ZAP, como as demais);
3. gravar o que o teste de autorização precisa saber sem gravar o arquivo;
4. ver como o ZAP recebe esse pedido para o `scan`.

**O que há nos alvos do laboratório** (procurado nos OpenAPI versionados):

- **Clínica Piloto** (`lab/pilot/openapi.json`) e **VAmPI** (`lab/vampi/openapi3.yml`): **nenhuma** operação aceita `multipart/form-data` (o Piloto só tem downloads: `baixarArquivo`, `baixarDocumento`).
- **crAPI** (`lab/crapi/openapi.json`): **duas**: `update_profile_pic` (`POST /identity/api/v2/user/pictures`, campo `file`, `string` com `format: binary`, opcional) e `upload_profile_video` (`POST /identity/api/v2/user/videos`, `file` obrigatório). O `lab/crapi/README.md` já registra que o `probe` não as suporta. O crAPI, porém, **não** entra no `hdast stack up` nem nos testes de integração (`application/lab_targets.py` só conhece VAmPI e Clínica Piloto; o crAPI sobe à mão, cerca de 95 s e 2,5 GiB).

Ou seja: há alvo com upload, mas nenhum dentro da infraestrutura de teste automático.

**O que se sabe do ZAP e o que não se sabe.** O `probe` envia pela rota `zap`; o proxy do ZAP guarda a mensagem inteira, com os cabeçalhos e o corpo (ADR 0007, confirmado no spike). Mas o `scan` não parte da mensagem guardada: `ScanClient.start_scan` (`adapters/zap/scan_client.py`) chama `ascan/action/scan` com `url`, `method`, `contextId`, `scanPolicyName`, `recurse=false` e, se houver corpo, `postData` **como texto**, sem `Content-Type`. Para `POST` de JSON isso funciona (provado no laboratório, ADR 0023). **Para multipart não está provado** que o ZAP ache o nó certo nem que ataque as partes: o texto perde bytes não UTF-8, e a fronteira vem no cabeçalho, que a API não recebe. Este ADR decide o que fazer com essa incerteza em vez de escondê-la.

## Decisão

Vamos alcançar a operação de upload no `probe` com um arquivo sintético pequeno e inofensivo, gravar um resumo sem o arquivo, e levar a operação ao `scan` **só na forma que a prova no laboratório mostrar que o ZAP entende**.

### 1. O arquivo é sempre sintético, pequeno e de lista fechada

Módulo novo `domain/synthetic_files.py` (puro). `FileKind` é um `Literal` fechado, e cada tipo é uma **constante** do módulo:

| Tipo | `Content-Type` | Extensão | Conteúdo |
| --- | --- | --- | --- |
| `text` (padrão) | `text/plain` | `.txt` | `synthetic file\n` (15 bytes, o mesmo de `multipart_encoding.py`) |
| `csv` | `text/csv` | `.csv` | `id,value\n1,synthetic\n` |
| `json` | `application/json` | `.json` | `{"synthetic":true}\n` |
| `png` | `image/png` | `.png` | o menor PNG válido (1×1, 67 bytes), constante, com teste que confere assinatura e CRCs |

Garantias fixadas em código e em teste:

- Nenhum arquivo passa de 1 KiB (`MAX_FILE_BYTES = 1024`) e o corpo multipart inteiro não passa de 16 KiB (`MAX_MULTIPART_BYTES = 16_384`); no máximo 20 partes (`MAX_PARTS`).
- **Nunca executável.** Não existe tipo `application/octet-stream`, script, binário, `svg`, `html`, `pdf`, arquivo compactado ou documento com macro. A extensão do nome **precisa** ser a do tipo. Teste: nenhum conteúdo começa por `MZ`, `\x7fELF`, `#!`, `<?`, `<script`, `PK`, `%PDF`, e nenhum contém `<` ou `;` fora do JSON fixo.
- O conteúdo não vem do OpenAPI, do alvo, do usuário nem de relógio: é determinístico, o que também faz a boundary (SHA-256 das partes, como em `multipart_encoding.py`) ser estável entre execuções.
- Nome do arquivo e nome de campo: ASCII `[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}`, sem barra, sem `..`, sem aspas, sem CR/LF (a mesma regra `_NAME` do módulo atual): nenhuma injeção de cabeçalho por nome.

**Como o tipo e o nome são escolhidos** (do menos para o mais específico):

1. padrão: `text` e `synthetic.txt`;
2. o OpenAPI declara `encoding.<campo>.contentType` (o carregador, `adapters/openapi/operation_mapper.py`, passa a guardá-lo em `MediaBody.part_content_types`, aditivo): `image/png` escolhe `png`, `text/csv` escolhe `csv`, `application/json` escolhe `json`; qualquer outro (inclusive `image/jpeg`, `video/mp4`, `application/pdf`) **continua `text`** e o relatório diz que o tipo declarado não é suportado;
3. regra de dados nova `synthetic_file` em `data-rules.yml` (ADR 0006), a mais específica de todas: `args: {kind: png, name: foto.png}`. É a saída do agente quando o alvo recusa o tipo padrão (`validation_error`). Valida `kind` na lista fechada e `name` pela regra de nome (extensão coerente com o tipo); `args` inválidos são erro de regra de dados, com o caminho do campo, como nos demais geradores. O gerador devolve o **texto** `tipo:nome`, que cabe no esquema `string` do campo binário e que `parse_file_spec` (domínio) lê.

### 2. Como o corpo é montado

- `BuiltRequest` (`domain/request_builder.py`) ganha `files: tuple[FileSpec, ...] = ()` (`FileSpec`: nome do campo, tipo, nome do arquivo). Quando o tipo de mídia escolhido é `multipart/form-data`, o `RequestBuilder`:
  - trata como **arquivo** a propriedade `string` com `format: binary` (OpenAPI 3.0); uma lista cujos itens são `binary` vira **um** arquivo com o nome do campo;
  - gera as demais propriedades escalares pelo caminho de sempre (fluxo, regra, `enum`, valor implícito), como `text/plain` de uma parte;
  - recusa, com `build_error` e mensagem que diz o que fazer, campo aninhado (objeto ou lista que não seja de arquivos), nome de campo fora da regra, mais de 20 partes, esquema sem propriedades e propriedade binária com `format` que não seja `binary`. `format: byte` é texto em base64 e **não** é arquivo. OpenAPI 3.1 (`contentMediaType`) não é modelado: operação com ele cai em `build_error` `multipart_unsupported_schema` (limite abaixo).
- `encode_built_request` (`domain/request_encoding.py`) deixa de recusar `multipart/form-data` **quando há `files`**: chama `encode_multipart` (novo em `multipart_encoding.py`, que generaliza `encode_synthetic_multipart` sem quebrá-la: os testes do ADR 0048 continuam) e põe o `Content-Type` com a fronteira. `encode_body` continua recusando multipart sozinho (o login não usa), e a mensagem do `ConfigError` deixa de dizer que "multipart ainda não é testado" para dizer o que falta ao pedido. A boundary não pode aparecer em nenhum conteúdo (já verificada hoje).
- `hdast probe --dry-run` (`application/preview.py`): mostra `multipart/form-data` com a **lista de partes** (nome, tipo, tamanho, nome do arquivo), nunca os bytes nem a boundary.

### 3. O que fica em `exchanges.json` (e o que não)

`ExchangeRecord` (`domain/probe_exchange.py`) ganha `multipart: MultipartSummary | None = None`, aditivo:

- `content_type`: só `multipart/form-data`, **sem** `boundary`;
- `body`: continua `None` (o corpo multipart nunca é gravado, nem o arquivo, nem os valores dos campos de texto);
- `multipart.parts`: lista de `{name, kind: "field" | "file", filename, content_type, size}` com **nome, tamanho e tipo**; para `field`, só nome e tamanho; **sem valor**;
- soma dos tamanhos em `multipart.total_bytes`.

Um campo de texto cujo nome `classify_field_name` (`domain/authz_sensitive.py`) classifica como segredo vai para `omitted_fields`, como hoje. O registro é descartado se algum segredo registrado aparecer no alvo (regra que já existe). Como nada do corpo é gravado, o `probe.json`, o `audit.jsonl` e o `exchanges.json` não passam a conter conteúdo de arquivo: um teste procura `synthetic file` e a assinatura do PNG na pasta da execução e exige zero ocorrências.

**Um registro com `multipart` não é reexecutável pelos testes que repetem pedidos.** `authz` e `negative` (ADR 0051) tratam `multipart is not None` como `not_tested` com o motivo `unsupported_body`; o programador confere em `domain/authz_plan*.py` que hoje um registro de escrita sem `body` **não** é reenviado sem corpo (se for, o conserto entra neste ADR, com o teste `test_authz_nao_reenvia_escrita_sem_corpo`). Repetir um upload com outra conta fica fora desta decisão.

### 4. Como o ZAP recebe o pedido, e o `scan`

- **`probe` (ADR 0007, sem mudança de mecanismo):** o pedido multipart sai pela rota `zap`; o ZAP o guarda como qualquer outro, com cabeçalhos e corpo. Passa pela cerca (`ScopeGuard` e proxy): o método é `POST`, o caminho é o da operação, e a cerca não olha o corpo (ADR 0017).
- **`scan`:** a operação só é candidata se o `probe` teve sucesso (ou, pelo ADR 0050, classe incluída) e a requisição aprendida existe. Duas regras novas em `domain/scan_plan.py`:
  1. **Corpo não ASCII não é varrido.** `postData` vai como texto; um corpo com byte fora de ASCII (o tipo `png`) não sobrevive à ida e volta. A operação continua **provada** pelo `probe` e entra em `not_tested` com o motivo novo `binary_body` (acrescentado a `SkipReason`), e a mensagem diz "use `synthetic_file` com um tipo de texto para varrer, se o alvo aceitar".
  2. Corpo ASCII (`text`, `csv`, `json`) segue o caminho de sempre: `ScanTarget.body` é o texto da mensagem aprendida (`LearnedRequest.body`, de `core/view/messages`), byte a byte, com a mesma boundary.
- **Critério de aceite medido, não presumido.** Como o `scan` não consegue passar o `Content-Type`, o ZAP pode (a) achar o nó e atacar as partes, (b) recusar (`url_not_found`: `ScanRefused`), (c) aceitar mas tratar o corpo como outro tipo e atacar sem sentido. O laboratório decide (seção "Como provar"). O critério é: a entrada do `scan.json` da operação tem `requests > 0` **e** o histórico do ZAP contém pelo menos uma mensagem àquele caminho, com cabeçalho de requisição `multipart/form-data`, que não é a mensagem do `probe`.
- **Se o critério não for atendido** (decisão tomada de antemão, como pede o plano do ciclo): o `scan` **não** varre multipart. A operação entra em `not_tested` com o motivo `multipart_not_scannable` e a mensagem "o ZAP não recebe o cabeçalho do corpo multipart por esta API; a operação foi alcançada, mas não varrida". A parte do `probe`, do resumo e da cobertura **fica entregue**; a parte do `scan` vira item adiado com motivo, e o relatório da versão registra o que foi tentado (investigação do plano, passos 1 a 6) e as alternativas (mensagem por `sourceMessageId` num plano do Automation Framework, ADR 0022, "Alternativas"; ou um script de regra no ZAP, que a cerca não cobre). Nada some em silêncio.
- **O que o ZAP pode gerar numa operação de upload** (nome do arquivo, conteúdo e campos de texto atacados) é decisão da política do ZAP, e a cerca só decide método e caminho. Os valores de ataque do ZAP não são "arquivo sintético inofensivo" no sentido da seção 1; podem gravar conteúdo estranho no armazenamento do alvo. É risco aceito e declarado no relatório (limite abaixo); a carta pode proibir o caminho com `scope.deny_paths`.

### 5. O que o relatório diz

- Cobertura: operação multipart **alcançada** aparece como alcançada (`probe_successes`), e a lista de "sem varredura" traz `binary_body` ou `multipart_not_scannable` quando for o caso, com a mensagem acima.
- Texto novo em "o que não foi testado" quando há operação multipart: "O arquivo enviado é sintético, pequeno e de tipo fixo; não se testou tamanho grande, tipo malicioso, nome de arquivo hostil nem conteúdo executável. O que o ZAP enviou nas partes não foi controlado por esta ferramenta."
- `spec inspect` mantém `multipart_offline` (ADR 0048) e ganha `multipart_probe: "ready" | "unsupported_schema"`, só quando há multipart: diz se o `RequestBuilder` consegue montar o corpo daquela operação **sem** enviar nada.

### 6. Contrato (aditivo)

`data-rules.yml`: gerador `synthetic_file`. `exchanges.json`: `multipart`. `scan.json`: motivos `binary_body` e `multipart_not_scannable`. OpenAPI carregado: `MediaBody.part_content_types`. `probe --dry-run`: lista de partes. `spec inspect`: `multipart_probe`. Sem mudança de perfil, de carta, de impressão digital da aprovação, de códigos de saída, de envelope nem de `schema_version`. **Nenhuma trava afrouxa**: o `ScopeGuard` e o proxy decidem o pedido exatamente como antes; o orçamento de pedidos do `probe` não muda; o corpo é sempre pequeno e sintético.

## Alternativas consideradas

- **Aceitar arquivo do usuário ou do disco.** Traria conteúdo arbitrário, possível dado real e executável. Descartada: a lista é fechada e constante.
- **`application/octet-stream` com bytes aleatórios.** Imprevisível, difícil de provar que é inofensivo e sem fronteira estável. Descartada.
- **Tipos grandes (imagem de verdade, PDF, vídeo).** Subiria o corpo, o custo e o risco, e o `scan` não conseguiria mandá-los como texto. Descartada; o crAPI pede vídeo e imagem, e a regra `synthetic_file` com `png` é o limite.
- **Gravar o corpo multipart em `exchanges.json` para o `authz` repetir.** Gravaria o arquivo e os valores. Descartada; resumo sem o corpo, e o `authz` anota `unsupported_body`.
- **Mandar a operação ao ZAP por um plano do Automation Framework** (que guarda os cabeçalhos da mensagem). É o plano B se a prova falhar; já foi descartado como padrão no ADR 0022 por exigir arquivo dentro do contêiner e dar menos controle por requisição.
- **Varrer só os parâmetros de consulta e de caminho da operação de upload, sem o corpo.** Um `POST` sem corpo é recusado pelo alvo; não alcança nada. Descartada.
- **Tratar `format: byte` como arquivo.** É texto em base64: vira um campo de texto normal.
- **Esperar um alvo com upload para só então decidir.** O ADR e o domínio puro (a parte maior) se provam com testes sem alvo; só a prova de ponta a ponta depende do laboratório (seção seguinte).
- **Aprender o `Content-Type` da mensagem do ZAP e passá-lo à API.** A API `ascan/action/scan` não tem esse parâmetro (a verificar no ZAP 2.17 real; se tiver, vira o plano preferido e substitui a regra de `binary_body`).

## Consequências

- As operações de upload deixam de cair em `build_error`: `reachability` e a cobertura passam a contá-las quando o alvo aceita o arquivo sintético.
- O agente ganha uma saída para o alvo que recusa o tipo padrão (`synthetic_file`), no mesmo arquivo de regras de dados que já usa.
- O `exchanges.json` cresce de forma pequena e sem conteúdo.
- O `scan` de multipart tem desfecho **condicionado a uma prova**; se ela falhar, o item fica entregue pela metade e escrito assim.
- Dependência nova: nenhuma (biblioteca padrão: `email`, `hashlib`).
- Quem usava `build_error` de multipart como sinal de "não suportado" passa a ver `success`, `validation_error` ou `client_error` conforme o alvo.

## Casos de teste obrigatórios

Unitários (degrau 2):

- `domain/test_synthetic_files.py`: cada tipo tem o conteúdo, o `Content-Type` e a extensão da tabela; tamanhos abaixo do teto; o PNG tem assinatura e CRCs válidos; **nenhum conteúdo** começa por `MZ`, `\x7fELF`, `#!`, `<?`, `PK`, `%PDF`; nenhum contém `<script`; `parse_file_spec` aceita `png:foto.png` e recusa tipo desconhecido, extensão que não bate com o tipo, nome com `/`, `\`, `..`, aspas, CR/LF, vazio, 65 caracteres e Unicode.
- `domain/test_multipart_encoding.py`: os testes do ADR 0048 continuam verdes; `encode_multipart` com campos e arquivos; boundary determinística e ausente de todo conteúdo; partes acima de 20; corpo acima de 16 KiB; nomes repetidos e fora da regra; nome com CR/LF (recusado: injeção de cabeçalho); o parser `email` da biblioteca padrão recupera todas as partes.
- `domain/test_request_builder.py`: operação só multipart; operação com JSON e multipart (continua JSON); propriedade `binary` obrigatória e opcional; lista de arquivos vira uma parte; propriedades escalares seguem fluxo, regra e `enum`; campo aninhado, `format: byte`, `binary` num inteiro, esquema vazio e 3.1 (`contentMediaType`) são `build_error` com mensagem útil; regra `synthetic_file` escolhe tipo e nome; sem regra vale `text`; `encoding.contentType` declarado escolhe o tipo, e um tipo não suportado volta a `text`.
- `domain/test_request_encoding.py`: `encode_built_request` com `files` produz `Content-Type` com a fronteira; `encode_body` sozinho continua recusando multipart; mensagem nova.
- `domain/test_datagen_catalog.py`: `synthetic_file` com `args` válidos, ausentes, desconhecidos, `kind` inválido, `name` hostil; resultado é texto.
- `domain/test_probe_exchange.py`: registro de upload sem `body`, sem boundary no `content_type`, com `multipart.parts` sem valores e sem bytes; campo secreto em `omitted_fields`; segredo registrado no alvo descarta o registro; arquivo `exchanges.json` antigo (sem o campo) continua legível; **nenhum** `synthetic file` ou assinatura de PNG no JSON.
- `adapters/openapi/test_operation_mapper.py`: `encoding.contentType` lido e limitado (tamanho, quantidade, tipo não textual); documento sem `encoding`; `multipart` na posição 21 (ADR 0048) continua sinalizado.
- `domain/test_scan_plan.py`: corpo com byte fora de ASCII vira `binary_body`; corpo ASCII multipart é candidato; com o desvio da seção 4 ligado (constante do domínio, mudada só se a prova falhar), toda operação multipart vira `multipart_not_scannable`.
- `domain/test_authz_plan*.py`: registro com `multipart` é `not_tested` com `unsupported_body`; nenhum pedido sem corpo é reenviado.
- `application/test_probe_runner.py` com servidor falso: o falso recebe o `POST`, parseia o multipart com a biblioteca padrão e confere nome do campo, nome do arquivo, tipo e tamanho; resposta 2xx vira `success` e o `exchanges.json` traz o resumo; 415 e 400 viram `validation_error`/`client_error`; `--dry-run` mostra só a lista de partes.
- `tests/contract/test_cli_probe_commands.py` e `test_cli_spec*.py`: `spec inspect` com `multipart_probe`; `probe --dry-run` sem bytes nem boundary.
- Teste de propriedade: para qualquer nome de campo gerado, o resultado ou é recusado ou é um multipart que o parser da biblioteca padrão lê sem defeito, com as partes e os nomes de entrada.

## Como provar no laboratório (degrau 3)

Hoje só o crAPI tem upload e ele está fora do teste automático. Por isso a prova tem duas partes:

**A. Automática, `lab_fast` (precisa da tarefa T52c).** Teste `tests/integration/test_lab_multipart.py`, marcadores `integration` e `lab_fast`, na pasta descartável, perfil da Clínica Piloto **aprovado em código**, pilha com `stack up --build` (o `probe` e o `scan` usam a imagem do proxy; sem `--build`, a cerca é a antiga). Com a operação mínima de envio acrescentada ao Piloto (T52c: `POST /api/documentos/enviar`, `multipart/form-data`, campo `arquivo` binário obrigatório e `descricao` opcional, aceita só os quatro tipos até 64 KiB e devolve 201 com nome, tamanho e tipo; 400 e 415 nos demais; igual nos dois modos, **sem falha plantada**, para não mexer no gabarito da avaliação cega), para cada modo:

1. `probe --only enviarDocumento` devolve `success` (e `build_error` **não**); o corpo chegou ao alvo **como multipart de verdade**: o alvo é um servidor Spring que só devolve 201 se o parser dele leu o campo e o arquivo, e o teste confirma o nome gravado pela lista de documentos (`listarDocumentos`, operação que já existe).
2. `exchanges.json` tem o registro com `multipart.parts` (campo, arquivo, tamanhos), `body` nulo, `content_type` sem fronteira; a pasta da execução (`runs/`) **não** contém `synthetic file` nem a assinatura do PNG; nenhum segredo (`secret_values`, `files_containing`).
3. O proxy (`proxy_audit`) mostra `POST /api/documentos/enviar` liberado, uma linha por envio, dentro da cerca (`allow`).
4. Regra `synthetic_file` com `kind: png`: o `probe` volta a `success` com o PNG; `scan --dry-run` mostra a operação pulada por `binary_body`; com `kind: text` (ou o padrão), `scan --dry-run` mostra o plano com a operação.
5. **Prova do `scan` (o critério da seção 4):** `scan --run <id> --only enviarDocumento --max-minutes 3`. Lê `scan.json` (`requests > 0`, resultado da entrada) e o histórico do ZAP (`ZapHistory.proxied_messages`, `tests/integration/lab_support.py`): existe mensagem àquele caminho com cabeçalho `multipart/form-data` que não é a do `probe`? O resultado vai para `HDAST_IT_METRICS_DIR/lab-multipart-<modo>.json` **e decide**: critério atendido, o teste afirma que o plano e o scan funcionam; critério **não** atendido, o teste afirma o motivo `multipart_not_scannable` e a tarefa T52b liga o desvio da seção 4 (o `scan` deixa de varrer multipart e o relatório diz por quê; a decisão não fica em aberto).
6. `authz --run <id>`: a operação de upload aparece como `not_tested` (`unsupported_body`), nenhum pedido dela sai.
7. `stack down` ao fim.

**B. Manual no crAPI (opcional, uma operação, pelo coordenador).** Sobe o crAPI como diz `lab/crapi/README.md` (pilha sem alvo, compose à parte, contas, `seed.py`), copia o perfil com `synthetic_file` de `png` para `update_profile_pic` e roda `probe --only update_profile_pic`. O resultado (`success`, `validation_error` ou `client_error`) vai para o relatório da versão como **medição**, não como critério de aceite: o crAPI pode recusar o arquivo sintético. Se pedir mais (vídeo para `upload_profile_video`), o limite da seção 1 vale e fica registrado.

## Limites conhecidos

- Arquivo sintético, de quatro tipos e no máximo 1 KiB. Não testa tamanho grande, tipo malicioso, nome hostil, conteúdo executável nem upload de vários arquivos distintos.
- Alvo que exige imagem JPEG, PDF ou vídeo reais não é alcançado (o `probe` mostra `validation_error`).
- OpenAPI 3.1 (`contentMediaType`) e esquemas aninhados dentro de multipart não são montados.
- O `scan` de multipart depende da prova do item 5 da parte A; se falhar, só o alcance é entregue.
- Os valores que o ZAP injeta nas partes não são controlados por esta ferramenta (ver seção 4).
- O `authz` e o `negative` não repetem upload.
- Provado só no laboratório local; nenhum produto real; a parte A exige alterar o Piloto (decisão do dono, ver dúvidas do relatório).

## Divisão em tarefas

**T52a. Alcance no `probe`.** Onda 1 (arquivos próprios, sem conflito com T49 nem T50a).

- Novos: `src/harness_dast/domain/synthetic_files.py`, `tests/unit/domain/test_synthetic_files.py`.
- Alterados: `src/harness_dast/domain/multipart_encoding.py` (`encode_multipart`), `request_encoding.py`, `request_builder.py` (`BuiltRequest.files`, ramo multipart), `datagen_catalog.py` e `datagen.py` (gerador `synthetic_file`), `probe_exchange.py` (`MultipartSummary`), `api_model.py` (`MediaBody.part_content_types`), `src/harness_dast/adapters/openapi/operation_mapper.py` (`encoding.contentType`), `src/harness_dast/application/preview.py`, `src/harness_dast/domain/api_summary.py` e `application/inspect_spec.py` (`multipart_probe`), `domain/authz_plan.py` e vizinhos (`unsupported_body`, só se a verificação da seção 3 exigir), e os testes listados. Doc: `docs/reference/data-rules-yml.md` (gerador), `docs/reference/cli.md` (`probe --dry-run`).

**T52b. Alcance no `scan`.** Onda 2, depois da T50a (as duas editam `domain/scan_plan.py`).

- Alterados: `src/harness_dast/domain/scan_plan.py` (`SkipReason`: `binary_body`, `multipart_not_scannable`; a regra de corpo não ASCII), `src/harness_dast/application/scan.py` (só se o plano precisar de parâmetro), `domain/report_build.py` (mensagem de cobertura e o texto de "o que não foi testado"; **depois da T49 e da T50b** porque os três editam esse arquivo; se for preciso antes, o coordenador junta as mudanças), `docs/reference/scan.md`, e o teste de integração `tests/integration/test_lab_multipart.py` (o programador o escreve; o coordenador o roda).

**T52c. Operação de upload no laboratório (decisão do dono).** Onda 2, em paralelo (pastas próprias).

- Alterados: `lab/pilot/src/...` (controlador e serviço do envio), `lab/pilot/openapi.json` (a operação `enviarDocumento`, idêntica nos dois modos), `lab/pilot/product-profile/` (a regra de dados do `descricao` e do arquivo, se o alvo exigir), `lab/pilot/README.md` e os testes do Piloto, e qualquer teste que conte operações do laboratório (o programador procura por número fixo de operações em `tests/`). Fora da tarefa: a pasta de gabaritos da avaliação cega em `evals/`, que é do coordenador e não ganha falha nova.
- Sem a T52c, a parte A da prova não existe e o item fica provado só por testes unitários e, opcionalmente, pelo crAPI à mão.

**T52d. Documentação e skills.** Coordenador: `docs/reference/target-yml.md`/`data-rules-yml.md`, `docs/guides/problemas-comuns.md` (a saída para o alvo que recusa o tipo), `.claude/skills/fix-reachability/SKILL.md` (usar `synthetic_file`). `CHANGELOG.md`, `CLAUDE.md`, `docs/roadmap.md` e `docs/adr/README.md` são do coordenador.

Ordem: T52a primeiro (tudo depende do corpo montado); T52b e T52c em seguida e em paralelo; T52b só fecha depois do resultado do item 5 da parte A.

## Adendo da T52a (alcance no `probe`, 2026-11-14)

Registro do que a implementação da T52a fez além ou de forma um pouco diferente do texto acima. O status do ADR não muda.

- **Onde moram os modelos de resumo.** `MultipartPart` e `MultipartSummary` ficam em `domain/multipart_encoding.py` (junto de `encode_multipart` e de `summarize_multipart`, que lê um corpo e devolve só nome, tipo e tamanho); `probe_exchange.py` os importa. O resumo do `exchanges.json` nasce de `summarize_multipart` sobre o corpo realmente enviado, e não de um campo a mais em `HttpRequest`: o registro é descartado se o corpo não for um multipart bem formado ou se um segredo registrado aparecer nele.
- **Classificação de campos** em `domain/multipart_schema.py` (novo, puro): decide arquivo, texto ou recusa; o `RequestBuilder` só o consome. `encoding.contentType` é lido por `adapters/openapi/operation_mapper.py` para `MediaBody.part_content_types` (até 50 campos; só `multipart/form-data`; primeiro tipo da lista, em minúsculas e sem parâmetros; valor que não parece `tipo/subtipo` é ignorado).
- **Multipart sem arquivo** (só campos de texto) continua recusado em `encode_built_request` (`build_error`); só há envio quando existe pelo menos um `FileSpec`. `encode_body` sozinho continua recusando multipart.
- **Tipo declarado sem arquivo sintético** (`image/jpeg`...) volta a `text` e a frase fica em `BuiltRequest.skipped_fields`.
- **Prévia do `--dry-run`:** `RequestPreview.multipart_parts` (modelo em `domain/probe_result.py`) lista nome, tipo e tamanho das partes.
- **`authz`:** só o `plan_vertical` (`domain/authz_plan.py`) e a tabela de acesso (`domain/authz_matrix_plan.py`, `authz_matrix_notes.py`) reenviariam um `POST` sem o corpo gravado; ambos marcam `unsupported_body`. Os testes de escrita em outra conta e de atribuição em massa já recusavam por `no_json_body` (o registro multipart não tem `body`). Nenhuma lógica de envio do `authz` mudou. O `negative` (ADR 0051) ainda não existe neste ponto da história: quem o implementar deve tratar `multipart is not None` do mesmo modo.
- **Não modelado:** OpenAPI 3.1 (`contentMediaType`) não é detectado pelo carregador de esquemas (vira campo de texto); a recusa `multipart_unsupported_schema` cobre só o que o 3.0 declara.
- **Fora da T52a** (continuam para a T52b e a T52c): a regra `binary_body` e o desvio `multipart_not_scannable` no `scan`, o texto do relatório e o teste de laboratório.

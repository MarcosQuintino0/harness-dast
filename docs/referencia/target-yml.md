# Perfil de produto: `target.yml` (schema v1)

Esta página descreve o schema v1 **como implementado** nos modelos de `src/harness_dast/domain/` (`profile.py`, `scope.py`, `auth.py`, `window.py`, `run.py`, `secret_ref.py`). Decisões: [ADR 0005](../decisoes/0005-perfil-de-produto-versionado.md) e [ADR 0013](../decisoes/0013-schema-v1-do-perfil-de-produto.md).

> **O que existe.** Os modelos validados e imutáveis (`ProductProfile.from_data`), o carregador de YAML endurecido, `hdast init`, `hdast profile validate` e, desde o M3, `hdast spec inspect`, `hdast preflight` e `hdast probe`, que usam o perfil. `data-rules.yml` e `flows.yml` têm modelo e referência próprios ([data-rules-yml.md](data-rules-yml.md), [flows-yml.md](flows-yml.md)). Um teste valida o `products/_template/target.yml` contra os modelos.

Mudar o formato do perfil muda um contrato público: exige subir `schema_version` e escrever um ADR.

## O que é o perfil

Cada produto tem uma pasta (por padrão em `products/PRODUTO/`, ou onde `HDAST_PRODUCTS_DIR` apontar) com:

| Arquivo | Conteúdo | Quem escreve | Modelo no código |
| --- | --- | --- | --- |
| `target.yml` | Ambiente, escopo, autorização, janelas, limites, autenticação, limpeza | O agente, a partir da autorização formal informada pelo usuário. A CLI valida | Existe (esta página) |
| `data-rules.yml` | Regras declarativas de geração de dados ([ADR 0006](../decisoes/0006-regras-de-dados-declarativas.md)) | O agente | `domain/datagen.py` |
| `flows.yml` | Encadeamento entre chamadas, em vários níveis (sem ciclo) | O agente | `domain/flow.py` |
| Hook de limpeza | Script SQL de limpeza ([ADR 0011](../decisoes/0011-limpeza-por-sql-oracle-com-python-oracledb.md)) | **Uma pessoa** do time do produto. O agente nunca escreve nem altera | Só o caminho é validado |

O modelo de pasta fica em `products/_template/`. Perfis reais ficam fora deste repositório (P-01). O perfil não contém segredos: só referências (`secret_ref`).

## Regras gerais de validação

- Todo bloco rejeita **campos desconhecidos** (um erro de digitação falha em vez de ser ignorado) e todo modelo é imutável.
- Os problemas saem em uma única mensagem `CONFIG_ERROR` (código de saída 2): `Perfil inválido (N problema(s)):` seguido de uma linha `- caminho.do.campo: explicação` por problema, em ordem alfabética. A mensagem cita o caminho do campo e um texto fixo, **não o valor recebido**. Um segredo digitado no lugar errado não aparece na mensagem.
- Segredos em `secret_ref` e hosts inválidos não são citados na mensagem (achados A-10 e de eco de segredo). Resta citar, nas recusas do `ScopeGuard`, o nome do método e do esquema informados (até 80 caracteres, com escape), o host canônico e a porta da regra violada.
- `schema_version` é conferido antes de tudo: ausente, não inteiro, ou diferente de `1` falha com mensagem própria.
- Caminhos de arquivo (`openapi`, `cleanup.script`) são validados **sem tocar o disco**.

## Blocos de proteção e aprovação humana

Uma pessoa aprova o perfil com [`hdast profile approve`](cli.md#hdast-profile-approve-e-hdast-profile-approval). Se um bloco protegido mudar, a CLI recusa os comandos que tocam o alvo com `SCOPE_NOT_APPROVED` até uma pessoa aprovar de novo. Consulte `hdast profile approval <produto>` para ver quais blocos mudaram (`data.changed_blocks` com `--json`).

| Identificador em `changed_blocks` | O que a aprovação cobre |
| --- | --- |
| `environment` | Nome do ambiente, endereço base e verificação de TLS |
| `technologies` | Tecnologias declaradas, quando presentes |
| `scope.allow` | Regras que permitem operações |
| `scope.deny_paths` | Caminhos proibidos |
| `scope.path_mode` | Modo de caminho |
| `scope.authorization` | Referência e validade da autorização |
| `scope.windows` | Janelas de execução |
| `limits` | Limites de carga e duração |
| `auth` | Tipo, caminho do login ou cabeçalho da chave, contas (apelido, papel e nomes de `secret_ref`) e limite de logins |
| `scan` | Bloco inteiro da política da varredura, incluindo o limiar de severidade |
| `authz` | Bloco inteiro do teste de autorização |
| `negative` | Bloco inteiro do teste de valores proibidos, quando difere do padrão |
| `extra_checks` | Verificações adicionais quando o bloco difere do padrão. As chaves do Nuclei entram quando verdadeiras e a autorização do motor fixa também a versão e o SHA-256 do catálogo |
| `cleanup` | Configuração da limpeza, com caminho do script, nomes de `secret_ref`, tabelas, teto de linhas e esquema. A limpeza confere o conteúdo do script separadamente |

**Origem dos blocos gerados.** A CLI escreve os blocos de proteção a partir do `carta.yml` (`hdast init --from-letter`). Com `kind: letter` (padrão), o que a carta não diz fica no mais estreito. Com `kind: request` (pedido mínimo, [ADR 0120](../decisoes/0120-pedido-minimo-com-padroes-e-aprovacao.md)), a CLI escreve também os padrões da tabela (escopo do OpenAPI sem `DELETE`, caminhos negados sugeridos, janela, validade, limites e capacidades extras), cada um explícito no `target.yml` e listado em `# Padrão do pedido mínimo:` no cabeçalho. O valor padrão de cada campo do modelo do perfil não muda, e tudo o que o padrão liga entra na impressão digital e só vale depois da aprovação.

A aprovação compara o perfil validado e normalizado. Comentários, espaços e ordem das chaves do YAML ficam de fora, assim como os valores dos segredos. A versão do cálculo é 2, e perfis com aprovação na versão 1 precisam de nova aprovação. A aprovação fica na pasta de estado (`HDAST_STATE_DIR`). [ADR 0037](../decisoes/0037-aprovacao-humana-do-escopo.md).

Para ajustar o alcance depois da aprovação, o agente pode atualizar `openapi`, `probe`, `auth.csrf`, `auth.token_expired`, `auth.default_account`, `auth.account_map` e as opções de codificação do login (`request_encoding`, `username_field`, `password_field`, `token_response_field`, `token_header`, `token_scheme`).

## Exemplo completo

```yaml
schema_version: 1
product: agenda
environment:
  name: homolog
  base_url: https://agenda.hml.exemplo.com.br
openapi: ./openapi.json
scope:
  allow:
    - host: agenda.hml.exemplo.com.br
      paths: ["/api/**"]
      methods: [GET, POST, PUT, PATCH]
  deny_paths:
    - "/api/interno/**"
    - "/api/conta/excluir"
  authorization:
    reference: "SEC-1234"
    valid_until: 2027-01-31
  path_mode: strict          # padrão; "wide" só com autorização escrita na carta
  windows: ["seg-sex 20:00-06:00 America/Sao_Paulo"]
limits:
  requests_per_second: 5
  max_duration_minutes: 60
  zap_threads_per_host: 2
auth:
  type: login_password
  token_path: /auth/token
  accounts:
    - alias: user_a
      role: paciente
      username: { secret_ref: "env:AGENDA_USER_A_LOGIN" }
      password: { secret_ref: "env:AGENDA_USER_A_SENHA" }
cleanup:
  type: oracle_sql
  script: ./cleanup/cleanup.sql
  connection: { secret_ref: "env:AGENDA_ORACLE_DSN" }
  user: { secret_ref: "env:AGENDA_ORACLE_LIMPEZA_USUARIO" }
  password: { secret_ref: "env:AGENDA_ORACLE_LIMPEZA_SENHA" }
  allowed_tables: [AGENDA_CONSULTA, AGENDA_PACIENTE]
  max_rows: 500
  requires_confirmation: true
```

Os valores (`agenda`, `SEC-1234`, hosts e datas) são fictícios.

## Raiz

| Campo | Tipo | Obrigatório | Regra |
| --- | --- | --- | --- |
| `schema_version` | inteiro | Sim | Exatamente `1`. Booleano ou texto não valem |
| `product` | texto | Sim | Slug: minúsculas, dígitos e `-`, de 1 a 40 caracteres, sem `-` no início nem no fim |
| `environment` | bloco | Sim | Veja abaixo |
| `openapi` | texto | Sim | Caminho relativo seguro (veja "Caminhos de arquivo") |
| `scope` | bloco | Sim | Veja abaixo |
| `limits` | bloco | Sim | Veja abaixo. Sem valores padrão: o perfil precisa fixar todos |
| `auth` | bloco | Sim | Um dos dois tipos |
| `cleanup` | bloco | Não | Padrão: ausente |
| `probe` | bloco | Não | Critério de sucesso e caminho de saúde (M3). Padrão: sucesso é 2xx |
| `scan` | bloco | Não | Política da varredura ativa e gate de severidade (M4). Veja [`scan`](#scan-opcional) |
| `authz` | bloco | Não | Teste de autorização entre contas ([ADR 0027](../decisoes/0027-teste-de-autorizacao-entre-contas.md)). Veja [`authz`](#authz-opcional) |
| `extra_checks` | bloco | Não | Capacidades extras e declaração de autorização do Nuclei. Veja [`extra_checks`](#extra_checks-opcional) |

### Caminhos de arquivo (`openapi`, `cleanup.script`)

Aceita só caminho relativo à pasta do produto. É recusado: vazio; mais de 260 caracteres; barra invertida; `:` (unidade como `C:`); começar com `/` ou `~`; qualquer segmento `..`; caractere não imprimível.

## `environment`

| Campo | Tipo | Regra |
| --- | --- | --- |
| `name` | texto | Minúsculas, dígitos, `-` e `_`; começa com letra ou dígito; até 32 caracteres |
| `base_url` | texto | URL `http` ou `https` absoluta, sem `?` nem `#`. Passa pela mesma normalização do `ScopeGuard`. Host, esquema e porta precisam ser cobertos por alguma regra de `scope.allow` |
| `verify_tls` | booleano (padrão `true`) | Verificação do certificado TLS do alvo. `false` só é aceito para host local (regra com `allow_local: true`); em ambiente real, instale a CA no sistema |

A consistência entre `base_url` e o escopo é conferida ao montar o perfil. O caminho e o método não são conferidos para a `base_url`, só a origem.

## `scope`

| Campo | Tipo | Regra |
| --- | --- | --- |
| `allow` | lista de regras | De 1 a 100 regras |
| `deny_paths` | lista de padrões | Padrão: vazia. Até 200. Valem para **qualquer host** |
| `authorization` | bloco | Veja abaixo |
| `path_mode` | `strict` ou `wide` | Padrão `strict`. Como o proxy de escopo lê caminhos ambíguos (veja `scope.path_mode`). **Só vale se a carta de autorização o autoriza**; o agente nunca escolhe `wide` |
| `windows` | lista de janelas | De 1 a 20. A execução é permitida quando **qualquer** janela está aberta |

### `scope.allow[]` (regra de permissão)

| Campo | Tipo | Padrão | Regra |
| --- | --- | --- | --- |
| `host` | texto | (obrigatório) | Nome DNS exato. Sem curinga, esquema, usuário, porta ou caminho. IPv6 entre colchetes. Guardado em forma canônica (minúsculas, punycode, sem ponto final) |
| `paths` | lista de padrões | (obrigatório) | De 1 a 200 padrões de caminho |
| `methods` | lista de textos | (obrigatório) | De 1 a 7 métodos. Veja "Métodos" |
| `scheme` | `http` ou `https` | `https` | `http` precisa ser escrito de propósito |
| `port` | inteiro 1 a 65535 | ausente | Ausente significa a porta padrão do esquema (443 ou 80). Porta diferente da padrão só passa se estiver escrita aqui |
| `allow_local` | booleano | `false` | Autorização explícita para host local (veja abaixo) |

#### Quais hosts exigem `allow_local: true`

O erro mais comum de quem começa: o alvo do laboratório tem nome de contêiner Docker sem ponto (`clinica-piloto`, `vampi`), e isso conta como host **local**. A mensagem do perfil diz `scope.allow[0]: este host conta como local e exige allow_local: true nesta regra`. A correção, no laboratório:

```yaml
environment:
  base_url: http://vampi:5000
scope:
  allow:
    - host: vampi
      scheme: http          # o alvo do laboratório não tem TLS
      port: 5000
      allow_local: true     # obrigatório para nome sem ponto, localhost e IP
      paths: ["/**"]
      methods: [GET, POST]
```

Em um ambiente real de teste, o oposto: use o nome DNS completo (`meu-produto.hml.exemplo.com.br`, com ponto) e **não** escreva `allow_local`. A regra não muda; só a mensagem e a dica ficaram mais claras.

`allow_local` existe para o laboratório local, onde o alvo roda em contêiner Docker. Esses hosts são o caminho clássico de SSRF (requisição forjada do lado do servidor, usada para alcançar a rede interna), por isso são recusados a menos que a regra os declare.

Exigem `allow_local: true`:

- qualquer **IP literal** (por exemplo `127.0.0.1`, `10.0.0.5`, `[::1]`);
- o nome `localhost` e nomes que terminam em `.localhost`;
- nomes de **rótulo único**, sem ponto (por exemplo `vampi`, o nome do contêiner do lab);
- nomes que terminam em `.local` ou `.internal`.

Regras adicionais:

- `allow_local: true` num host **público** (que tem ponto e não termina nesses sufixos) é erro: `allow_local só se aplica a host local`.
- IP literal precisa ser loopback ou privado. IP público literal é recusado sempre (`use o nome DNS do host`).
- Sempre recusados, com ou sem `allow_local`: endereços de metadados da nuvem (`169.254.169.254`, `fd00:ec2::254`, `metadata.google.internal`, `metadata`, `instance-data`), IP link-local, não especificado, multicast e reservado (exceto `::1`), IPv6 que embute IPv4 (mapeado, 6to4, Teredo), identificador de zona IPv6 (`%eth0`) e IPv4 em forma não canônica (decimal único, hexadecimal, octal, abreviado).
- Um ambiente de empresa em IP privado **não** entra por `allow_local`. O perfil de produto real usa o nome DNS do ambiente. Veja o limite correspondente do proxy de saída em [../../docker/egress-proxy/README.md](../../docker/scope-proxy/README.md#o-que-isto-não-garante-riscos-residuais).

### Padrões de caminho (`paths`, `deny_paths`)

Um padrão começa com `/` e é dividido em segmentos por `/`. Uma barra final é ignorada.

| Padrão | Significa |
| --- | --- |
| segmento literal (`api`) | Casa um segmento, comparação exata. Maiúsculas e minúsculas importam |
| `*` | Casa **exatamente um** segmento qualquer, nunca vazio. `/api/*` casa `/api/a`, não casa `/api` nem `/api/a/b` |
| `**` | Casa **zero ou mais** segmentos. `/api/**` casa `/api`, `/api/a` e `/api/a/b/c` |
| `/` | Casa somente a raiz |

Inválido num padrão: vazio; mais de 256 caracteres; não começar com `/`; segmento vazio (`//`); segmento `.` ou `..`; curinga parcial (`us*`, `*.json`; só `*` ou `**` como segmento inteiro); os caracteres `\`, `%`, `;`, `?`, `#`, espaço e qualquer caractere de controle ou formatação. Padrões repetidos são unificados.

### Métodos

Aceitos, em maiúsculas: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`. `TRACE` e `CONNECT` ficam de fora de propósito. Minúsculas são recusadas. Guardados ordenados e sem repetição.

### Precedência (como o `ScopeGuard` decide)

Para cada requisição, depois da normalização, na ordem:

1. **`deny_paths` vence tudo.** Se o caminho casar com algum padrão de negação, a requisição é recusada. A comparação ignora maiúsculas/minúsculas e diferenças de composição Unicode (NFKC), porque o servidor pode tratar `/API/Conta` como `/api/conta`.
2. A origem (host, esquema e porta) precisa casar com ao menos uma regra de `allow`.
3. O caminho precisa casar com um padrão de uma regra dessa origem.
4. O método precisa estar na lista de uma regra que casou a origem e o caminho.

Tudo que não é explicitamente permitido é recusado (falha fechada).

### `scope.path_mode`

Decide só como o **proxy de escopo** (a cerca por onde passa todo pedido do ZAP) lê o caminho. Valores: `strict` (padrão) e `wide`. Qualquer outro valor, número, lista ou `null` é recusado (`CONFIG_ERROR`). Não existe flag de linha de comando que o ligue. Decisão e risco: [ADR 0026](../decisoes/0026-cerca-com-motivo-granular-e-modo-amplo-de-caminho.md).

| Modo | Caminho com `;`, `%2f`, `%5c`, `%252e`, `//`, `%` solto, ponto ou espaço final | `deny_paths` |
| --- | --- | --- |
| `strict` | Recusado (`malformed_request`; o código granular vai em `detail`) | Conferido sobre a forma canônica |
| `wide` | Liberado se a **leitura literal** (decodificada uma vez, separada pelas barras cruas) casar com `scope.allow` e com o método | Recusa se **qualquer** leitura que um servidor poderia fazer do caminho casar (`%2f` como barra, `;param` removido, ponto e espaço aparados, decodificação repetida, `.`/`..` resolvidos, `//` colapsado, caixa, NFKC, sufixo de formato como `.json`) |

No modo `wide` continuam recusados: segmento `.` ou `..` (cru ou codificado uma vez), NUL e caracteres de controle, UTF-8 inválido, credenciais na URL, e tudo de host, porta, esquema, método e tamanho da URL. Só o proxy usa o modo: `probe`, `preflight`, o cliente do alvo, redirecionamentos e o plano da CLI continuam estritos.

**Risco aceito no modo `wide`:** uma leitura do caminho que caia fora de `scope.allow` sem casar `deny_paths` **não** é recusada. O pedido liberado pode chegar a outro caminho do mesmo host (host e porta nunca mudam). O que não pode ser tocado precisa estar em `deny_paths`. O relatório conta quantos pedidos liberados tiveram essa leitura (`traffic.allowed_outside_allow`).

Sufixo de formato: no modo `strict`, `deny_paths: /api/admin` não cobre `/api/admin.json` (a comparação é por segmento inteiro). Negue a grafia que importa, ou use `wide`, que confere o sufixo removido.

### `scope.authorization`

| Campo | Tipo | Regra |
| --- | --- | --- |
| `reference` | texto | De 1 a 200 caracteres, imprimível, não só espaços. Identifica o documento de autorização (chamado, e-mail de aprovação) |
| `valid_until` | data | Somente data `AAAA-MM-DD`, sem hora (aceita a data do YAML ou o texto nesse formato). **Último dia de validade, inclusive, contado em UTC.** Depois dele a execução é recusada (`SCOPE_VIOLATION`) |

Contar em UTC pode encerrar a validade algumas horas antes do fim do dia local em fuso a oeste de Greenwich (o Brasil, por exemplo). O erro é para o lado seguro. Data e hora (`2026-11-13T00:00:00`) e número (timestamp) são recusados: o fuso seria ambíguo.

### `scope.windows[]`

Forma de texto: `<dias> <HH:MM>-<HH:MM> <fuso IANA>`, separados por um único espaço.

- **Dias:** lista separada por vírgula, sem espaços, de `seg ter qua qui sex sab dom`, ou faixas `dia-dia`. A faixa pode dar a volta na semana: `sex-seg` é sexta, sábado, domingo e segunda.
- **Horas:** 24 h, `00:00` a `23:59` no início e até `24:00` no fim. O início é inclusivo e o fim é exclusivo.
- **Início igual ao fim é sempre recusado**, na forma de texto e na forma estruturada. Para o dia todo use `00:00-24:00`.
- **Fim menor que o início cruza a meia-noite**, e os dias listados são os dias em que a janela **começa**.
- **Fuso:** nome IANA (`America/Sao_Paulo`). Vale o relógio de parede local; na mudança de horário de verão a janela continua de "20:00 locais" a "06:00 locais". O banco de fusos vem do pacote `tzdata` ([ADR 0012](../decisoes/0012-dependencias-tzdata-e-pyyaml.md)).

| Texto | Significado |
| --- | --- |
| `seg-sex 08:00-18:00 America/Sao_Paulo` | De segunda a sexta, das 8h às 18h locais |
| `seg-sex 20:00-06:00 America/Sao_Paulo` | Abre às 20h de segunda a sexta e fecha às 6h do dia seguinte. Está aberta na sexta às 03h de sábado, mas fechada na segunda às 03h (essa madrugada pertence ao domingo) |
| `sab,dom 00:00-24:00 America/Sao_Paulo` | Sábado e domingo, o dia todo |
| `sex-seg 22:00-02:00 UTC` | Faixa que dá a volta na semana |
| `seg 09:00-09:00 UTC` | **Recusada**: início igual ao fim |
| `seg-sex 25:00-06:00 UTC` | **Recusada**: hora inválida |

O modelo também aceita a forma estruturada (`days`, `start_minute`, `end_minute`, `timezone`), pensada para uso interno. No `target.yml`, use o texto.

A execução é permitida quando **qualquer** janela está aberta e a autorização não venceu. Quem confere é `ProductProfile.ensure_runnable(now)`, que recebe o instante com fuso (um instante sem fuso é recusado).

## `limits`

Todos os três campos são obrigatórios e há tetos **absolutos**. O perfil e as sobrescritas de linha de comando só escolhem valores até estes tetos. O motivo é impedir que um perfil inflado, ou um agente que sugira números altos, transforme o harness num teste de carga contra um ambiente compartilhado.

| Campo | Tipo | Mínimo | Teto |
| --- | --- | --- | --- |
| `requests_per_second` | número | maior que 0 | 50 |
| `max_duration_minutes` | inteiro | 1 | 480 (8 horas) |
| `zap_threads_per_host` | inteiro | 1 | 8 |

`NaN`, infinito e booleano são recusados. Valor acima do teto é erro de validação (`valor fora do intervalo permitido`), não é reduzido em silêncio.

## `auth`

O campo `type` escolhe o tipo. A V1 aceita exatamente dois (P-04). Outros valores são recusados. Cada bloco aceita de 1 a 20 contas com `alias` único.

### Conta (comum aos dois tipos)

| Campo | Regra |
| --- | --- |
| `alias` | Apelido, o único nome visto pelo agente: começa com letra minúscula, depois minúsculas, dígitos e `_`; até 32 caracteres. Único no bloco |
| `role` | Papel da conta no produto, de 1 a 64 caracteres, imprimível, não só espaços |

### `type: login_password`

Usuário e senha enviados a um endpoint de login, que devolve um token. (Nome anterior: `oauth2_password`; veja o [ADR 0013](../decisoes/0013-schema-v1-do-perfil-de-produto.md).)

| Campo | Tipo | Padrão | Regra |
| --- | --- | --- | --- |
| `token_path` | texto | (obrigatório) | Caminho literal do login, começando com `/`, sem curingas e com as mesmas restrições de um padrão de caminho. O `POST` nele precisa ser permitido por `scope.allow` (e não negado), usando a `base_url` |
| `accounts[]` | lista | (obrigatório) | Contas de login: `alias`, `role`, `username` e `password`, os dois últimos como `secret_ref` |
| `request_encoding` | `form` ou `json` | `form` | Como enviar as credenciais no corpo |
| `username_field` | texto | `username` | Nome do campo do usuário no corpo. `[A-Za-z0-9_.-]`, de 1 a 64 |
| `password_field` | texto | `password` | Nome do campo da senha no corpo. Mesmas regras |
| `token_response_field` | texto | `access_token` | Onde está o token na resposta JSON, em caminho pontuado (`access_token`, `data.token`) |
| `token_header` | texto | `Authorization` | Cabeçalho em que o token é enviado. `[A-Za-z0-9-]`, de 1 a 64. Não pode ser `Host`, `Content-Length`, `Transfer-Encoding` nem `Connection` |
| `token_scheme` | texto | `Bearer` | Prefixo do valor do cabeçalho. Vazio envia só o token. Até 32 caracteres de `[A-Za-z0-9._~+/-]` |
| `csrf` | bloco | (ausente) | Proteção XSRF/CSRF (veja `auth.csrf`) |
| `login_limit` | bloco | (ausente) | Taxa de login que o alvo tolera (veja `auth.login_limit`) |
| `token_expired` | `{field, value}` | (ausente) | Sinal de "token vencido" (veja `auth.token_expired`) |
| `default_account`, `account_map` | | (ausentes) | Conta por operação (veja `auth.account_map`) |

### `type: api_key`

Chave fixa enviada num cabeçalho.

| Campo | Tipo | Regra |
| --- | --- | --- |
| `header_name` | texto | Cabeçalho que leva a chave (`X-API-Key`). Mesmas regras de `token_header` |
| `accounts[]` | lista | Contas com `alias`, `role` e `api_key` como `secret_ref` |

O `probe` (M3) obtém o token ele mesmo (a CLI resolve os segredos, faz o login e envia o token nas requisições). No `scan` (M4) a CLI instala o token no Replacer do ZAP e o renova em varreduras longas ([scan.md](scan.md#token-replacer)). O perfil aceita várias contas com papel, embora a V1 use só uma, para não mudar o schema quando o teste de autorização entre contas chegar na V2.

### `auth.csrf` (opcional, nos dois tipos)

Para alvos com proteção XSRF/CSRF por cookie duplicado (Spring Security `CookieCsrfTokenRepository`). O cliente busca o token com um GET, guarda o cookie por conta, envia cookie e cabeçalho nos métodos listados e, ao receber um 403 que parece rejeição de CSRF, busca o token de novo UMA vez. Com `login_password`, o token é buscado antes do login (o POST do login também o exige) e de novo depois dele.

| Campo | Tipo | Padrão | Regra |
| --- | --- | --- | --- |
| `fetch_path` | texto | (obrigatório) | Caminho literal de um GET que faz o alvo emitir o cookie. Precisa estar coberto por `scope.allow` com GET e fora de `deny_paths` (validado como o login) |
| `cookie_name` | texto | `XSRF-TOKEN` | Cookie que carrega o token |
| `header_name` | texto | `X-XSRF-TOKEN` | Cabeçalho que repete o valor. Mesmas regras de `token_header` |
| `methods` | lista | `[DELETE, PATCH, POST, PUT]` | Métodos que exigem o cabeçalho; ordenados e sem repetição |

```yaml
auth:
  type: login_password
  # ...
  csrf:
    fetch_path: /api/csrf
```

### `auth.login_limit` (opcional, só `login_password`)

Alvos reais limitam o login por origem e contam também as tentativas erradas (a Clínica Piloto aceita 5 por minuto). Estourar o limite trava as contas de teste. Com este bloco, o `preflight` e o `probe` nunca excedem a taxa declarada: antes de cada POST de login (primeiro login de uma conta, novo login por token vencido, repetição após 429 e a operação de login do OpenAPI) o orçamento espera até a janela deslizante de 60 s ter vaga.

| Campo | Tipo | Regra |
| --- | --- | --- |
| `max_per_minute` | inteiro | De 1 a 60. Soma todas as contas e todas as repetições do mesmo comando |

Também valem sem o bloco: **um login por conta por execução** (o token é reaproveitado até vencer) e, num 429 do login, a espera pelo `Retry-After` (no máximo 30 s por vez, até 3 vezes). O orçamento é **por comando**: `preflight` e `probe` são processos separados e não sabem dos logins um do outro (o `hdast run`, futuro, compartilhará o cache de tokens do processo). Rodar o `probe` logo depois do `preflight` pode esbarrar no 429 do alvo, que o `Retry-After` resolve ao custo de esperar.

```yaml
auth:
  login_limit:
    max_per_minute: 5
```

### `auth.token_expired` (opcional, só `login_password`)

Diz como o alvo avisa que o token venceu. O `probe` refaz o login **no máximo uma vez por requisição** (e o novo login conta no orçamento de `login_limit`).

| Campo | Tipo | Regra |
| --- | --- | --- |
| `field` | texto | Caminho pontuado no corpo JSON do 401 (`code`, `error.code`) |
| `value` | texto, inteiro ou booleano | Valor que significa "vencido" (`TOKEN_EXPIRADO`). O tipo importa |

Sem o bloco, **todo** 401 provoca um novo login. Com ele, só o 401 cujo corpo traz o campo com o valor declarado: um 401 `TOKEN_INVALIDO` ou `CREDENCIAIS_INVALIDAS` não gasta login.

```yaml
auth:
  token_expired: { field: code, value: TOKEN_EXPIRADO }
```

### `auth.default_account` e `auth.account_map` (opcionais, nos dois tipos)

Escolhem a conta que envia cada operação, para exercitar papéis (admin cria convênio; médico cria paciente; paciente vê o próprio perfil). **O agente só cita apelidos**: usuário e senha continuam em `secret_ref`.

| Campo | Tipo | Regra |
| --- | --- | --- |
| `default_account` | apelido | Conta das operações que nenhuma regra atende. Padrão: a primeira de `accounts` |
| `account_map[]` | lista (até 100) | Regras avaliadas em ordem; **a primeira que casa vence** |
| `account_map[].account` | apelido | Precisa existir em `accounts` (senão o perfil é recusado e a mensagem lista os apelidos válidos) |
| `account_map[].operations` | lista de `operationId` | A regra casa com estas operações. Um `operationId` que não existe no OpenAPI é `CONFIG_ERROR` no `probe` e `ACCOUNT_MAP_MISMATCH` em `spec inspect` |
| `account_map[].path` | padrão de caminho | A regra casa com operações cujo caminho casa com o padrão (mesma gramática de `scope.allow[].paths`; um `{marcador}` do OpenAPI vale como um segmento) |
| `account_map[].methods` | lista de métodos | Só junto de `path`; restringe a regra a estes métodos |

Uma regra precisa de `operations` ou de `path`; quando declara os dois, a operação precisa casar com **ambos** (e com `methods`, se houver). `hdast probe --account ALIAS` impõe essa conta a TODAS as operações (a flag só reduz o roteamento; nunca nomeia uma conta fora do perfil). `hdast spec inspect` devolve em `operation_accounts` a conta de cada operação que será enviada. O manifesto da execução (`accounts`) lista só as contas que o plano usa, e cada uma faz login uma vez, na partida.

```yaml
auth:
  default_account: admin_a
  account_map:
    - { account: medico_a, operations: [criarPaciente, criarReceita] }
    - { account: paciente_a, path: /api/me, methods: [GET, PUT] }
```

## `probe` (opcional)

| Campo | Tipo | Regra |
| --- | --- | --- |
| `success.json_field_absent_or_not_equal` | `{field, value}` | Sucesso além do código HTTP: uma resposta 2xx só conta como sucesso se o campo (caminho pontuado, `status` ou `data.result`) estiver ausente OU tiver valor diferente do de FALHA informado em `value` (texto, inteiro ou booleano; o tipo importa: `1` não é `true`). Sem o bloco, vale 2xx. Existe porque há alvos que respondem 200 com `{"status":"fail"}` (spike do M0) |
| `health_path` | texto | Caminho literal de um GET leve que o `preflight` usa para checar a saúde do alvo; precisa estar no escopo. Sem ele, o `preflight` tenta a raiz da `base_url`, que costuma estar fora de `scope.allow`. A varredura também o usa como GET de saúde entre as varreduras |
| `setup_path` | texto | Caminho literal de um GET **idempotente** que prepara os dados do alvo antes dos logins (por exemplo, recria as contas de exemplo de um ambiente recém-subido). O `preflight` o chama uma vez, depois do `target_health` e antes dos logins; o `run` herda, porque começa pelo `preflight`. Passa pelo mesmo `ScopeGuard`, pelo limitador de taxa e pela auditoria dos outros envios, e precisa estar em `scope.allow` (método `GET`, fora de `deny_paths`). Só use se a carta de autorização permitir esse GET; ausente, nada é chamado. `probe` sozinho não o chama (rode o `preflight` antes). Resposta 4xx ou 5xx reprova a verificação `target_setup`. Antes existia só o truque de apontar `health_path` para esse GET; ele continua funcionando, mas `setup_path` é o jeito explícito |
| `error_codes` | `{field, outcomes}` | Classificação exata pelo código de erro do corpo JSON (veja abaixo). Sem ele, a classificação usa só o status HTTP |

```yaml
probe:
  health_path: /api/saude
  setup_path: /api/dados-de-exemplo   # opcional: GET idempotente que prepara o alvo antes dos logins
  success:
    json_field_absent_or_not_equal: { field: status, value: fail }
```

### `probe.error_codes`

Alvos que devolvem um envelope de erro (`{"code": "...", "errors": [{"field", "rule"}]}`) permitem classificar a falha pelo **código**, sem adivinhar pelo status.

| Campo | Tipo | Regra |
| --- | --- | --- |
| `field` | texto | Caminho pontuado do campo do código no corpo (`code`, `error.code`) |
| `outcomes` | mapa | Classe de resultado -> lista de códigos. Classes aceitas: `validation_error`, `conflict`, `auth_error`, `csrf_error`, `not_found`, `rate_limited`, `client_error`, `server_error`. Um código só pode estar numa classe; até 100 códigos; `[A-Za-z0-9_.:-]`, até 64 |

Regras de uso: só respostas de erro (4xx e 5xx) são reclassificadas; o código só vale se for texto ou inteiro; código ausente ou não declarado cai na heurística por status. Um `csrf_error` declarado também decide se um 403 renova o token CSRF (exato, sem a heurística de corpo). Em `validation_error` e `conflict`, o `untrusted_target_data.excerpt` mantém a estrutura por campo (`errors[].field` e `rule`), que é o que o agente usa para escrever a regra de dados: o trecho continua limitado a 300 caracteres e redigido, e quando o corpo passa do teto caem primeiro as mensagens e depois os itens excedentes, nunca o `field` e o `rule` dos primeiros itens.

```yaml
probe:
  error_codes:
    field: code
    outcomes:
      validation_error: [VALIDACAO, CORPO_INVALIDO]
      conflict: [CONFLITO]
      csrf_error: [XSRF_INVALIDO]
      client_error: [TRANSICAO_INVALIDA]   # regra de estado: nem dado nem alvo
```

## `scan` (opcional)

Política da varredura ativa do ZAP e gate de severidade (M4, aditivo na schema v1; [scan.md](scan.md), [ADR 0022](../decisoes/0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md)). Tudo dentro de conjuntos fechados: nenhum campo reativa uma regra desligada por padrão, amplia métodos além do escopo ou remove um limite (os limites de carga continuam em `limits`, com tetos absolutos).

| Campo | Tipo | Padrão | Regra |
| --- | --- | --- | --- |
| `strength` | `LOW`, `MEDIUM` ou `HIGH` | `LOW` | Força de ataque da política |
| `threshold` | `LOW`, `MEDIUM` ou `HIGH` | `MEDIUM` | Limiar de alerta: só entram alertas com pelo menos esta confiança |
| `url_path_injection` | booleano | `true` | Injeção em segmentos de caminho. Ligada porque, sem ela, a injeção de SQL em parâmetro de caminho passa batida (spike do M0) |
| `mutating_methods` | lista de `PUT`/`PATCH` | vazia | Permite varrer `PUT`/`PATCH` sobre QUALQUER recurso. Sem isto, só sobre recurso criado na execução |
| `disable_rules` | lista de ids (0 a 999999, até 100) | vazia | Regras ativas do ZAP a desligar ALÉM das desligadas por padrão |
| `max_scan_minutes` | inteiro, 1 a 60 | 10 | Teto de cada varredura (uma por requisição aprendida) |
| `max_rule_minutes` | inteiro, 1 a 10 | 2 | Teto de cada regra dentro de uma varredura |
| `token_refresh_seconds` | inteiro, 10 a 3600 | 120 | Idade máxima do token no ZAP antes de renovar (nunca menos que `60 / auth.login_limit.max_per_minute`) |
| `fail_on` | `none`, `low`, `medium` ou `high` | `none` | Severidade proposta a partir da qual `report` sai com código 1. `report --fail-on` sobrepõe |
| `include_outcomes` | lista de até 5 classes: `logical_failure`, `validation_error`, `conflict`, `not_found`, `client_error` | vazia | Classes do `probe` além de `success` cujas operações o `scan` também ataca ([ADR 0050](../decisoes/0050-varrer-operacoes-que-deram-nao-encontrado.md)). Lista fechada, sem curinga e sem repetição; `auth_error`, `csrf_error`, `rate_limited`, `server_error`, `redirect`, `timeout` e `skipped_*` nunca entram. Não amplia o escopo (o `ScopeGuard` e o proxy continuam decidindo), `DELETE`, login, `deny_paths` e `PUT`/`PATCH` sem recurso criado seguem fora; mas ataca a partir de um pedido que o alvo recusou ou não achou, e nos `POST`, `PUT` e `PATCH` cria e altera mais dados sintéticos. Vem da carta (`attack.include_outcomes`, `source: carta` ou `pessoa`, aviso `OUTCOMES_ATTACK_EXTENDED`). Fora do padrão entra na impressão digital da aprovação: ligar exige aprovar de novo; vazia mantém as aprovações existentes. `hdast scan --include-outcome` só escolhe dentro dela |
| `allow_upload_scan` | booleano | `false` | A carta autoriza o ZAP a varrer operações de envio de arquivo (`multipart/form-data`, [ADR 0052](../decisoes/0052-multipart-no-probe-e-no-scan.md)). O ZAP grava conteúdo de ataque (nome e conteúdo de arquivo, campos de texto) no armazenamento do alvo, e esta ferramenta não o controla; por isso só a carta liga. Sem ele, a operação é alcançada pelo `probe` mas o `scan` a pula com o motivo `upload_scan_not_authorized` (no relatório ela aparece como alcançada e não varrida). Só vem da carta (`attack.allow_upload_scan`, `source: carta` e a frase em `quote`; aviso `UPLOAD_SCAN_AUTHORIZED`); texto, número e `null` no perfil são recusados. No padrão (`false`) fica fora da impressão digital da aprovação e as aprovações existentes continuam valendo; `true` muda o bloco `scan` e exige aprovar de novo |
| `inject_headers` | booleano | `false` | A carta autoriza injetar também em cabeçalhos e cookies ([ADR 0096](../decisoes/0096-bloco-attack-da-carta-liga-capacidades-v1-12.md)). Só a carta o liga; a capacidade que o consome chega depois. Ligá-lo muda a impressão digital |
| `oast` | booleano | `false` | A carta autoriza o retorno fora de banda, no servidor de retorno do laboratório (ADR 0096). Mesma regra de `inject_headers` |

```yaml
scan:
  strength: LOW
  threshold: MEDIUM
  fail_on: high
```

### `scan.pacing` (V1.7)

`scan.pacing` aceita `legacy` (padrão, variante A) ou `proxy` (variante B). A carta o declara em `attack.pacing` (ADR 0096). Ritmo da varredura: [ADR 0067](../decisoes/0067-ritmo-unico-e-medicao-do-executor.md), [0075](../decisoes/0075-ritmo-proxy-em-perfis-novos.md). Em `legacy`, o ZAP recebe atraso por host de `ceil(1000 / limits.requests_per_second)` milissegundos; em `proxy`, recebe zero e a cerca continua limitando a taxa de saída. A opção não altera força, regras, limites, escopo ou janela. A mudança para `proxy` é opcional e entra na impressão digital da aprovação: exige nova aprovação humana. O padrão preserva as aprovações anteriores. O atraso configurado não mede o atraso efetivo do ZAP. A prova de velocidade e cobertura segue o [guia de desempenho](scan-performance.md); não há ganho presumido.

## `authz` (opcional)

Comportamento do teste de autorização entre contas (`hdast authz` e o estágio `authz` do `run`, que vem ligado por padrão; [authz.md](authz.md), [ADR 0027](../decisoes/0027-teste-de-autorizacao-entre-contas.md)). Aditivo na schema v1. Tudo aqui só ajusta ou reduz o que o estágio repete: nada amplia escopo, métodos do escopo, limites ou janela. Sem o bloco valem os padrões.

| Campo | Tipo | Padrão | Regra |
| --- | --- | --- | --- |
| `public_operations` | lista de `operationId` (até 200) | vazia | Operações legitimamente públicas ou compartilhadas entre contas: BOLA e BFLA as ignoram (sem isto, um recurso público viraria alarme falso). Operação que não existe no OpenAPI é erro de configuração |
| `role_order` | lista de papéis (até 20) | vazia | Papéis do MENOR para o MAIOR privilégio (os `role` de `auth.accounts`). Necessário para a verificação vertical; sem ele o estágio diz que não pôde testar |
| `volatile_fields` | lista de nomes de campo (até 50) | vazia | Campos ignorados ao comparar respostas, além de `timestamp`, `requestId`, `traceId`, `correlationId`, `date`, `now`, `elapsed`, `etag`, `nonce` (a comparação ignora maiúsculas e separadores) |
| `vertical_methods` | lista de `GET`, `HEAD`, `POST`, `PUT`, `PATCH` | `[GET, HEAD]` | Métodos que o acesso vertical repete. `DELETE` é recusado. Os de escrita (`POST`, `PUT`, `PATCH`) só entram no plano com `allow_writes: true`; sem ele são retirados e o resultado traz a nota (`writes_not_authorized`) |
| `mass_assignment_fields` | lista de `{name, value}` (até 10) | `role`=`admin`, `papel`=`admin`, `admin`=`true`, `isAdmin`=`true` | Campos extras (um por pedido) da atribuição em massa; sempre entram, antes dos derivados do OpenAPI. `value` é texto, inteiro ou booleano |
| `derive_mass_candidates` | booleano | `true` | Junta aos campos declarados os que o OpenAPI sugere (somente leitura na entrada, só na resposta, ou nome de privilégio na entrada; [ADR 0040](../decisoes/0040-candidatos-de-campo-proibido-do-openapi.md)). `false` volta a testar só os declarados. Dono do recurso (`ownerId`, `tenantId`) nunca é derivado. Só vale com `allow_writes`. Fora do padrão, entra na impressão digital da aprovação |
| `max_derived_candidates` | inteiro de 1 a 20 | `6` | Máximo de campos derivados por operação (no `POST`, no máximo 4 derivados). O excesso vai para `not_tested` (`candidates_limited`). 0, 21, texto e decimal são recusados |
| `mass_assignment_methods` | lista de `PATCH`, `POST`, `PUT` | `[PATCH, POST, PUT]` | Métodos testados na atribuição em massa. Tirar `POST` desliga o teste de cadastro, que **deixa um recurso criado por campo testado** no ambiente de teste (limpe com `hdast cleanup` ou o reset). Lista vazia, `DELETE` ou outro método é recusado (`CONFIG_ERROR`) |
| `id_parameters` | lista de nomes (até 20; letras, dígitos e `_`, começando por letra; sem repetição) | vazia | Nomes de parâmetro de **consulta** que o dono do produto declara como identificador de objeto mesmo sem terminar em `id` (`cpf`, `matricula`; [ADR 0042](../decisoes/0042-escrita-em-recurso-de-outra-conta-e-id-fora-do-caminho.md)). Só acrescenta candidatos de leitura ao BOLA (`horizontal`) e à escrita em outra conta; o parâmetro precisa estar declarado no OpenAPI e o `ScopeGuard` segue decidindo. Nome inválido, repetido, mais de 20 ou tipo errado é `CONFIG_ERROR`. Fora do padrão (vazio), entra na impressão digital da aprovação e aparece no resumo do `profile approve` |
| `access_matrix` | lista de regras `{operation, allow, deny}` (até 500; uma por operação) | vazia | Tabela "quem pode o quê" ([ADR 0041](../decisoes/0041-tabela-quem-pode-o-que.md)): por operação (`operationId` do OpenAPI), os papéis que **podem** (`allow`) e os que **NÃO podem** (`deny`, cada um é testado). Cada lista tem até 20 papéis, sem repetição e sem espaço; o mesmo papel não pode estar nas duas; `deny` vazio só documenta (a linha sai sem teste). **Declaração do dono do produto**: a ferramenta nunca a completa; papel de `auth.accounts` que não aparece na linha fica `unspecified` e **não é testado** (nunca é presumido proibido). Campo extra, tipo errado, regra repetida, mais de 500 regras, ou lista com mais de 20 papéis é `CONFIG_ERROR` (saída 2). Operação que não existe no OpenAPI, papel sem conta em `auth.accounts` ou operação também em `public_operations` é `AUTHZ_CONFIG_INVALID` (saída 2), conferido quando o `authz` roda (e no `--dry-run`). Método `GET` e `HEAD` por padrão; `POST`, `PUT`, `PATCH` só com `allow_writes: true`; `DELETE` nunca. Fora do padrão, **entra na impressão digital**: preencher ou mudar a tabela exige nova aprovação (`hdast profile approve`), que lista a tabela inteira; a ordem das regras e dos papéis não conta. Só vive no `target.yml` (a carta não tem campo para isso). O `hdast authz --draft-matrix` ajuda a rascunhar, fora do perfil |
| `shared_roles` | lista de papéis | vazia | Papéis cujas contas compartilham legitimamente recursos, declarados pelo dono na carta (`attack.authz_shared_roles`, lista com `source: carta` e `quote`); gerado pela CLI, nunca inferido. `horizontal` e `horizontal_write` não comparam contas do mesmo papel listado e registram `shared_role` em `not_tested`; outras verificações não mudam. Preenchido entra no resumo e na impressão digital da aprovação; vazio preserva a impressão anterior. [ADR 0057](../decisoes/0057-papeis-compartilhados.md) |
| `cors_max_requests` | inteiro de 0 a 10 | `5` | Teto de GETs provados amostrados pela verificação CORS; `0` desliga a amostra. A verificação usa origem sob `.invalid` e respeita a cerca e os limites. O padrão preserva a impressão digital anterior; valor diferente exige nova aprovação. Veja [cors.md](cors.md) |
| `disabled_checks` | lista de `horizontal`, `excessive_data`, `anonymous_access`, `tampered_token`, `vertical`, `access_matrix`, `mass_assignment`, `horizontal_write`, `cors` | vazia | Verificações desligadas |
| `allow_writes` | booleano | `false` | A carta de autorização permite que o teste entre contas **escreva** no alvo ([ADR 0038](../decisoes/0038-authz-padrao-no-run-e-escrita-pela-carta.md)). Com `false`, a atribuição em massa e a escrita em recurso de outra conta (`horizontal_write`, `PUT`/`PATCH`) vão para `not_tested` ("escrita não autorizada pela carta: authz.allow_writes") e os métodos de escrita de `vertical_methods` ficam fora do plano; `--check mass_assignment` não o liga. Só `hdast init --from-letter` o escreve (`attack.allow_authz_writes` com `source: carta` e `quote`); texto como `"sim"` é recusado. Entra na impressão digital da aprovação: mudar exige aprovar de novo |

```yaml
authz:
  role_order: [paciente, medico, admin]
  public_operations: [lerCatalogo]
  volatile_fields: [versaoDoItem]
  access_matrix:
    - operation: criarMedico        # operationId do OpenAPI
      allow: [admin]                # podem
      deny: [paciente, recepcao]    # NÃO podem (cada um é testado)
```

Para a verificação horizontal o perfil precisa de pelo menos DUAS contas do mesmo papel não listado em `shared_roles` em `auth.accounts`, e a operação precisa ser roteada (`auth.account_map`) para uma delas; sem par o estágio registra `no_peer_account` em vez de dar verde.

## `negative` (opcional)

Teste de valores que o esquema proíbe ([ADR 0051](../decisoes/0051-valores-que-o-esquema-proibe.md); [negative.md](negative.md)). Sem o bloco, valem os padrões conservadores: só leitura. Nada aqui amplia escopo, métodos do escopo, janela nem limites (o `ScopeGuard` continua decidindo). Mas `allow_writes` escreve no alvo, os dois tetos são carga e `disabled_classes` esconde achado: por isso o bloco entra na impressão digital da aprovação humana **quando difere do padrão** (um perfil que não o usa mantém a aprovação que já tem).

| Campo | Tipo | Padrão | Descrição |
| --- | --- | --- | --- |
| `allow_writes` | booleano | `false` | A carta permite que o teste **grave** no alvo dado com valor inválido (`POST`, `PUT`, `PATCH`; nunca `DELETE`). Campo próprio, não reaproveita `authz.allow_writes`. Só vem da carta (`attack.allow_invalid_input_writes`, com `source: carta` e a frase em `quote`); texto, número e `null` são recusados |
| `max_cases_per_operation` | inteiro de 1 a 20 | `6` | Teto de casos por operação; o excesso vai para `not_tested` (`budget`) |
| `max_requests` | inteiro de 1 a 1000 | `200` | Teto de envios do estágio inteiro (casos e restaurações). `--max-requests` só o reduz |
| `disabled_classes` | lista de `wrong_type`, `missing_required`, `below_minimum`, `above_maximum`, `not_in_enum`, `too_long`, `too_short` | vazia | Classes que não se testam (só reduz). Sem repetição; fora da lista é recusado |

```yaml
negative:
  allow_writes: false
  max_cases_per_operation: 6
  max_requests: 200
  disabled_classes: []
```

## `extra_checks` (opcional)

Campos opcionais, todos desligados no modelo do perfil. O bloco entra na impressão digital da aprovação **quando difere do padrão**. Chave desconhecida ou valor de outro tipo é recusado. Os testes de limite, as regras experimentais e o inventário seguem as regras da carta e do pedido mínimo, com aprovação humana. [ADR 0096](../decisoes/0096-bloco-attack-da-carta-liga-capacidades-v1-12.md), [ADR 0120](../decisoes/0120-pedido-minimo-com-padroes-e-aprovacao.md)

| Campo | Tipo | Padrão | Descrição |
| --- | --- | --- | --- |
| `allow_rate_tests` | booleano | `false` | Testes de limite de consumo, com poucos pedidos e teto rígido |
| `experimental_rules` | booleano | `false` | Regras experimentais (alpha) do ZAP |
| `inventory` | booleano | `false` | Inventário de versões irmãs e documentação exposta, só no escopo |
| `nuclei` | booleano | `false` | Declara autorização para o Nuclei |
| `nuclei_login` | booleano | `false` | Declara autorização para login com o Nuclei |
| `nuclei_wide_paths` | booleano | `false` | Declara autorização para caminhos fora do Swagger com o Nuclei |

O cadastro registra os campos do Nuclei quando a carta traz a frase do dono em cada resposta `true` de `attack.*` com `source: carta`. O resumo de aprovação mostra a versão dos modelos e as opções declaradas. Opções de login ou caminhos amplos sem a autorização do motor aparecem com um aviso e ficam sem efeito. Com o motor autorizado, trocar a versão do motor, a versão do catálogo ou o SHA-256 do catálogo exige nova aprovação. Nesta etapa os campos servem ao registro e à revisão humana. [ADR 0122](../decisoes/0122-nuclei-como-segundo-motor.md#carta-pedido-mínimo-e-aprovação)

## Segredos: `secret_ref`

Nomes `HDAST_*` são recusados: são variáveis do próprio harness (chave do ZAP, pastas, proxy) e um perfil escrito pelo agente poderia mandá-las ao alvo como senha. Use um nome do produto, como `AGENDA_USER_A_SENHA`.

Todo valor sensível é uma referência, nunca o valor:

```yaml
password: { secret_ref: "env:AGENDA_USER_A_SENHA" }
```

Duas formas são aceitas, com `NOME` em maiúsculas, dígitos e `_`, começando por letra, até 128 caracteres:

| Forma | De onde vem o valor | Quando usar |
| --- | --- | --- |
| `env:NOME` | Variável de ambiente `NOME` do terminal que roda o `hdast` | CI, contêiner, avaliação cega e quem prefere variável |
| `keyring:NOME` | Cofre de credenciais do sistema operacional (Gerenciador de Credenciais do Windows, Keychain do macOS, Secret Service do Linux), sob o serviço `harness-dast` e o nome `NOME` | Uso diário de uma pessoa: grava-se uma vez e vale em todo terminal |

```yaml
password: { secret_ref: "keyring:AGENDA_USER_A_SENHA" }
```

Um valor literal (senha, token) não casa com nenhum formato e é recusado sem ser citado na mensagem. Quem resolve o valor é a CLI (adaptador `adapters/secrets`), nunca o agente. Valor ausente ou vazio é erro de `preflight`/`probe` que cita só `apelido.campo`. Veja [ADR 0009](../decisoes/0009-segredos-por-referencia.md) e [ADR 0030](../decisoes/0030-cofre-de-credenciais-do-sistema-keyring.md).

Sobre `keyring:`:

- **Quem grava é uma pessoa**, num terminal: `hdast secret set NOME` (prompt oculto; ver [cli.md](cli.md#hdast-secret)). O agente só cita o NOME e orienta a pessoa a rodar o comando.
- Os dois formatos nunca se substituem: `keyring:NOME` não lê a variável `NOME` e `env:NOME` não lê o cofre. Sem cofre utilizável (contêiner, CI, Linux sem serviço de segredos) o erro é `SECRET_BACKEND_ERROR` com a dica de usar `env:NOME`.
- Para não colidir entre produtos, comece o NOME pelo produto (`AGENDA_USER_A_SENHA`), como no `env:`. O cofre é por usuário do sistema e por máquina.
- No Windows o valor guardado não passa de cerca de 1280 caracteres: serve para senha, não para um DSN muito longo (que pode seguir em `env:`).
- Vale também para `cleanup.connection`, `cleanup.user` e `cleanup.password`.

## `cleanup`

Opcional. O bloco aponta para um SQL escrito e revisado por uma pessoa.

| Campo | Tipo | Regra |
| --- | --- | --- |
| `type` | texto | Somente `oracle_sql` |
| `script` | texto | Caminho relativo seguro |
| `connection` | `secret_ref` | DSN do Oracle de testes (`host:porta/serviço`), sem usuário nem senha |
| `requires_confirmation` | booleano | Deve ser `true`. `false`, ausente ou texto são recusados: na V1 a confirmação humana não é opcional |
| `user` | `secret_ref` | Usuário de banco só da limpeza (`SELECT` e `DELETE` nas tabelas de teste, nada mais). Obrigatório para a limpeza rodar |
| `password` | `secret_ref` | Senha desse usuário. Obrigatório para a limpeza rodar |
| `allowed_tables` | lista de texto | `TABELA` ou `ESQUEMA.TABELA`, de 1 a 100, guardadas em maiúsculas, sem aspas nem repetição. As únicas tabelas que o script pode apagar ou consultar. Obrigatório para a limpeza rodar |
| `max_rows` | inteiro | De 1 a 1 000 000. Teto de linhas apagadas no total; passar disso desfaz tudo (saída 7). Obrigatório para a limpeza rodar |
| `db_schema` | texto | Opcional. Identificador do esquema dono das tabelas, quando o usuário da limpeza não é o dono (a CLI faz `ALTER SESSION SET CURRENT_SCHEMA`) |

`user`, `password`, `allowed_tables` e `max_rows` são aditivos na schema v1 e opcionais no perfil (um perfil antigo continua válido), mas `hdast cleanup` se recusa a rodar sem eles. Execução, confirmação e portão de SQL: [../como-funciona/operacao/cleanup.md](../como-funciona/operacao/cleanup.md) e [ADR 0020](../decisoes/0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md).

## O que o `ScopeGuard` recusa

O `ScopeGuard` (`domain/scope.py`) decide sobre a **forma canônica** da requisição (`domain/urlnorm.py` e `domain/host.py`). Qualquer ambiguidade vira `ScopeViolation` (código de saída 3), em vez de tentar adivinhar como o servidor interpretaria a URL.

- **Método:** fora dos sete aceitos ou em minúsculas.
- **URL:** vazia; maior que 2048 caracteres; relativa; esquema que não seja `http` ou `https`; espaço, caractere de controle ou formatação (bidi, largura zero) e barra invertida; caminho, consulta ou fragmento com caractere não ASCII (use percent-encoding).
- **Credenciais embutidas:** qualquer `@` na autoridade (`permitido.com@outro.com`).
- **Porta:** malformada, fora de 1-65535 ou com zeros à esquerda (`0080`).
- **Host:** vazio; caracteres fora de nome DNS; falha ou mapeamento na codificação IDNA (letras parecidas de outro alfabeto geram outro punycode e não casam); IP em forma não canônica; IPv6 que embute IPv4 ou com zona; metadados da nuvem; faixas proibidas.
- **Caminho:** segmento vazio (`//`); `.` ou `..` (também codificados); barra codificada (`%2f`, `%5c`); percent-encoding malformado ou que não é UTF-8; **dupla codificação** (`%252e`); controle ou espaço invisível.
- **Reescritas do servidor (fechadas na rodada de 2026-11-13, achado A-01):** segmento que contém `;` (parâmetro de caminho como `/admin;x=1`, cru ou como `%3B`) e segmento que termina em ponto ou espaço, ou começa por espaço (cru ou codificado: `/admin.`, `/admin%20`, `/admin%2e`). Tomcat/Spring e IIS removem esses trechos antes de rotear; aceitá-los contornaria `deny_paths`.
- **Redirecionamento:** conferido como requisição nova (`ensure_redirect_allowed`). `Location` relativo sem barra inicial é recusado. Informe o método que será realmente usado (um 303 troca `POST` por `GET`).

A consulta (`?a=b`) e o fragmento (`#x`) são descartados da decisão de escopo (mas não podem conter controle nem espaço).

### Limitações conhecidas

- **Sem resolução de DNS.** O guarda não detecta um nome permitido que aponte, ou passe a apontar, para um endereço interno (DNS rebinding). Quem cobre isso é a camada 3, o proxy de saída ([ADR 0008](../decisoes/0008-escopo-em-tres-camadas.md)).
- **`%` literal em caminho.** Um caminho que contenha de fato o caractere `%` (codificado como `%25`) é recusado, por ser indistinguível de dupla codificação. Pode recusar a mais; nunca a menos.
- **Cabeçalhos e corpo não são conferidos.** O guarda olha método, URL e redirecionamento. O conteúdo da requisição não passa por ele.
- **Caminhos de IIS.** `/admin::$DATA` e nomes curtos 8.3 (`/ADMIN~1`) não são fechados, porque exigiriam recusar caminhos legítimos. Contra alvo Windows, negue esses padrões em `deny_paths`. A permissão (`allow`) é sensível a maiúsculas; só a negação ignora caixa.
- **Cobertura de sobrescritas é conservadora.** `covers` (usada para garantir que uma flag só estreita o escopo) pode responder "não coberto" em alguns casos de inclusão real; então pode recusar um estreitamento legítimo, mas nunca aceita uma ampliação.
- **Mensagens de recusa não repetem o caminho** da requisição (achado A-09): ele pode conter um token. Elas citam o host canônico, o método e a origem; a dica diz o que verificar em `scope.allow`.
- O guarda é puro: não envia nada e não decide janela nem autorização (isso é de `ProductProfile.ensure_runnable`).

## Regras de leitura

O YAML é carregado em modo seguro, com limite de tamanho (256 KiB) e de profundidade, e o perfil inválido sai como o `CONFIG_ERROR` descrito acima. O agente não pode ampliar `scope`, `limits` nem `authorization`: esses valores vêm da autorização formal informada pelo usuário. Flags só reduzem (`domain/overrides.py`).

## `data-rules.yml` e `flows.yml`

Veja [data-rules-yml.md](data-rules-yml.md) e [flows-yml.md](flows-yml.md). O encadeamento aceita vários níveis, sem ciclos (ADR 0021).


## Tecnologias declaradas (ADR 0068)

`technologies` é opcional e gerado de `attack.technologies` da carta, com lista `value` de identificadores minúsculos, `source: carta` e a frase não vazia em `quote`. Exemplo:

```yaml
technologies:
  value: [h2]
  source: carta
  quote: "O banco de dados utilizado é H2."
```

A declaração é consultiva: não confirma a tecnologia nem reduz a cobertura; todas as regras continuam ativas. Não infira valores. Quando ausente ou desconhecida, não aparece no perfil gerado e preserva a aprovação anterior. Uma declaração ou mudança nela altera a impressão digital e exige nova aprovação.

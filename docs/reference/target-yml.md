# Perfil de produto: `target.yml` (schema v1)

Esta página descreve o schema v1 **como implementado** nos modelos de `src/harness_dast/domain/` (`profile.py`, `scope.py`, `auth.py`, `window.py`, `run.py`, `secret_ref.py`). Decisões: [ADR 0005](../adr/0005-perfil-de-produto-versionado.md) e [ADR 0013](../adr/0013-schema-v1-do-perfil-de-produto.md).

> **O que existe e o que não existe.**
>
> - **Existe:** os modelos validados e imutáveis. `ProductProfile.from_data(dados)` recebe um dicionário Python e devolve o perfil ou levanta `ConfigError`.
> - **Não existe:** o carregador de YAML (a leitura do arquivo e a conversão em dicionário), o comando `hdast profile validate` e o comando `hdast init`. Hoje nenhum comando `hdast` lê um `target.yml`. A validação só é exercida pelos testes. Um teste valida o `products/_template/target.yml` com o PyYAML.
> - `data-rules.yml` e `flows.yml` ainda não têm modelo no código. Os trechos deles no fim desta página são desenho ilustrativo (M3).

Mudar o formato do perfil muda um contrato público: exige subir `schema_version` e escrever um ADR.

## O que é o perfil

Cada produto tem uma pasta (por padrão em `products/PRODUTO/`, ou onde `HDAST_PRODUCTS_DIR` apontar) com:

| Arquivo | Conteúdo | Quem escreve | Modelo no código |
| --- | --- | --- | --- |
| `target.yml` | Ambiente, escopo, autorização, janelas, limites, autenticação, limpeza | O agente, a partir da autorização formal informada pelo usuário. A CLI valida | Existe (esta página) |
| `data-rules.yml` | Regras declarativas de geração de dados ([ADR 0006](../adr/0006-regras-de-dados-declarativas.md)) | O agente | Não existe (M3) |
| `flows.yml` | Encadeamento entre chamadas, de um nível na V1 | O agente | Não existe (M3) |
| Hook de limpeza | Script SQL de limpeza ([ADR 0011](../adr/0011-limpeza-por-sql-oracle-com-python-oracledb.md)) | **Uma pessoa** do time do produto. O agente nunca escreve nem altera | Só o caminho é validado |

O modelo de pasta fica em `products/_template/`. Perfis reais ficam fora deste repositório (P-01). O perfil não contém segredos: só referências (`secret_ref`).

## Regras gerais de validação

- Todo bloco rejeita **campos desconhecidos** (um erro de digitação falha em vez de ser ignorado) e todo modelo é imutável.
- Os problemas saem em uma única mensagem `CONFIG_ERROR` (código de saída 2): `Perfil inválido (N problema(s)):` seguido de uma linha `- caminho.do.campo: explicação` por problema, em ordem alfabética. A mensagem cita o caminho do campo e um texto fixo, **não o valor recebido**. Um segredo digitado no lugar errado não aparece na mensagem.
- Segredos em `secret_ref` e hosts inválidos não são citados na mensagem (achados A-10 e de eco de segredo). Resta citar, nas recusas do `ScopeGuard`, o nome do método e do esquema informados (até 80 caracteres, com escape), o host canônico e a porta da regra violada.
- `schema_version` é conferido antes de tudo: ausente, não inteiro, ou diferente de `1` falha com mensagem própria.
- Caminhos de arquivo (`openapi`, `cleanup.script`) são validados **sem tocar o disco**.

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
    - "/api/notificacoes/**"
    - "/api/conta/excluir"
  authorization:
    reference: "SEC-1234"
    valid_until: 2027-01-31
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
  connection: { secret_ref: "env:AGENDA_ORACLE_LIMPEZA" }
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

### Caminhos de arquivo (`openapi`, `cleanup.script`)

Aceita só caminho relativo à pasta do produto. É recusado: vazio; mais de 260 caracteres; barra invertida; `:` (unidade como `C:`); começar com `/` ou `~`; qualquer segmento `..`; caractere não imprimível.

## `environment`

| Campo | Tipo | Regra |
| --- | --- | --- |
| `name` | texto | Minúsculas, dígitos, `-` e `_`; começa com letra ou dígito; até 32 caracteres |
| `base_url` | texto | URL `http` ou `https` absoluta, sem `?` nem `#`. Passa pela mesma normalização do `ScopeGuard`. Host, esquema e porta precisam ser cobertos por alguma regra de `scope.allow` |

A consistência entre `base_url` e o escopo é conferida ao montar o perfil. O caminho e o método não são conferidos para a `base_url`, só a origem.

## `scope`

| Campo | Tipo | Regra |
| --- | --- | --- |
| `allow` | lista de regras | De 1 a 100 regras |
| `deny_paths` | lista de padrões | Padrão: vazia. Até 200. Valem para **qualquer host** |
| `authorization` | bloco | Veja abaixo |
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
- Um ambiente de empresa em IP privado **não** entra por `allow_local`. O perfil de produto real usa o nome DNS do ambiente. Veja o limite correspondente do proxy de saída em [../../docker/egress-proxy/README.md](../../docker/egress-proxy/README.md#ambiente-de-teste-corporativo-em-ip-privado).

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
- **Fuso:** nome IANA (`America/Sao_Paulo`). Vale o relógio de parede local; na mudança de horário de verão a janela continua de "20:00 locais" a "06:00 locais". O banco de fusos vem do pacote `tzdata` ([ADR 0012](../adr/0012-dependencias-tzdata-e-pyyaml.md)).

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

Usuário e senha enviados a um endpoint de login, que devolve um token. (Nome anterior: `oauth2_password`; veja o [ADR 0013](../adr/0013-schema-v1-do-perfil-de-produto.md).)

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

### `type: api_key`

Chave fixa enviada num cabeçalho.

| Campo | Tipo | Regra |
| --- | --- | --- |
| `header_name` | texto | Cabeçalho que leva a chave (`X-API-Key`). Mesmas regras de `token_header` |
| `accounts[]` | lista | Contas com `alias`, `role` e `api_key` como `secret_ref` |

Como o token ou a chave chega ao ZAP e é renovado em varreduras longas depende do spike do M0 (P-10). O perfil aceita várias contas com papel, embora a V1 use só uma, para não mudar o schema quando o teste de autorização entre contas chegar na V2.

## Segredos: `secret_ref`

Todo valor sensível é uma referência, nunca o valor:

```yaml
password: { secret_ref: "env:AGENDA_USER_A_SENHA" }
```

Só a forma `env:NOME` é aceita, com `NOME` em maiúsculas, dígitos e `_`, começando por letra, até 128 caracteres. Um valor literal (senha, token) não casa com o formato e é recusado sem ser citado na mensagem. Quem resolve o valor é um adaptador futuro (M3), nunca o agente. Veja [ADR 0009](../adr/0009-segredos-por-referencia.md).

## `cleanup`

Opcional. O bloco aponta para um SQL escrito e revisado por uma pessoa.

| Campo | Tipo | Regra |
| --- | --- | --- |
| `type` | texto | Somente `oracle_sql` |
| `script` | texto | Caminho relativo seguro |
| `connection` | `secret_ref` | Conexão de um usuário de banco que só pode apagar nas tabelas de teste |
| `requires_confirmation` | booleano | Deve ser `true`. `false`, ausente ou texto são recusados: na V1 a confirmação humana não é opcional |

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

- **Sem resolução de DNS.** O guarda não detecta um nome permitido que aponte, ou passe a apontar, para um endereço interno (DNS rebinding). Quem cobre isso é a camada 3, o proxy de saída ([ADR 0008](../adr/0008-escopo-em-tres-camadas.md)).
- **`%` literal em caminho.** Um caminho que contenha de fato o caractere `%` (codificado como `%25`) é recusado, por ser indistinguível de dupla codificação. Pode recusar a mais; nunca a menos.
- **Cabeçalhos e corpo não são conferidos.** O guarda olha método, URL e redirecionamento. O conteúdo da requisição não passa por ele.
- **Caminhos de IIS.** `/admin::$DATA` e nomes curtos 8.3 (`/ADMIN~1`) não são fechados, porque exigiriam recusar caminhos legítimos. Contra alvo Windows, negue esses padrões em `deny_paths`. A permissão (`allow`) é sensível a maiúsculas; só a negação ignora caixa.
- **Cobertura de sobrescritas é conservadora.** `covers` (usada para garantir que uma flag só estreita o escopo) pode responder "não coberto" em alguns casos de inclusão real; então pode recusar um estreitamento legítimo, mas nunca aceita uma ampliação.
- **Mensagens de recusa não repetem o caminho** da requisição (achado A-09): ele pode conter um token. Elas citam o host canônico, o método e a origem; a dica diz o que verificar em `scope.allow`.
- O guarda é puro: não envia nada e não decide janela nem autorização (isso é de `ProductProfile.ensure_runnable`).

## Regras de leitura (previstas para o carregador, M2)

Planejado: o YAML será carregado em modo seguro, com limite de tamanho e de profundidade, e o erro do perfil inválido será o `CONFIG_ERROR` descrito acima. O agente não pode ampliar `scope`, `limits` nem `authorization`: esses valores vêm da autorização formal informada pelo usuário. Flags só reduzem (`domain/overrides.py`).

## `data-rules.yml` e `flows.yml` (ilustrativo, M3)

Sem modelo no código. O desenho aprovado:

```yaml
# products/agenda/data-rules.yml
schema_version: 1
rules:
  - match: { field: cpf }
    generator: br.cpf
    unique: true
  - match: { operation: criarConvenio, field: codigo }
    generator: numeric
    args: { digits: 8 }
    unique: true
```

```yaml
# products/agenda/flows.yml
schema_version: 1
bindings:
  - produces: { operation: criarPaciente, field: id }
    consumed_by:
      - { operation: buscarPaciente, param: pacienteId }
      - { operation: criarConsulta, field: pacienteId }
```

Na V1, o encadeamento cobre só dependências diretas de um nível (P-12). O catálogo de geradores chega no M3.

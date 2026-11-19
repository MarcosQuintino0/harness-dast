# Modelo de carta de autorização

Peça este documento ao dono do produto **antes** de cadastrar o produto. Sem ele preenchido e assinado, não há perfil: `scope`, `limits`, `authorization` e as janelas do perfil são **transcritos daqui**, nunca inventados (nem por você, nem pelo agente). Se algum campo ficar em branco, o cadastro para.

Fundamento: [authorization-and-scope.md](../como-funciona/operacao/authorization-and-scope.md). Campos do perfil: [target-yml.md](../referencia/target-yml.md).

Só ambiente de **teste**, com **dados sintéticos**. Produção e dados de pessoas reais ficam de fora.

Para a leitura de dono do teste horizontal, declare duas contas do mesmo papel que não
compartilhem recursos, com dados sintéticos distintos disponíveis para cada uma. O
`authz` monta as leituras a partir do contrato e de IDs observados, independentemente
do roteamento do probe; ausência de prova aparece como lacuna com ação sugerida no
relatório e no painel, nunca como proteção comprovada. [Referência](../referencia/authz.md#leitura-de-dono-independente-do-roteamento-v193).

## Modelo (copie e preencha)

```text
CARTA DE AUTORIZAÇÃO DE TESTE DE SEGURANÇA

1. Identificação
   Produto / sistema:
   Dono do produto (nome e e-mail):
   Referência desta autorização (ticket, e-mail de aprovação):
   Válida até (AAAA-MM-DD, com folga: a CLI conta a data em UTC):

2. Ambiente
   Nome do ambiente (homologação, teste, laboratório):
   URL base (esquema, host e porta):
   Declaro que é ambiente de teste, sem dados reais de pessoas:  [ ] sim

3. Escopo
   Hosts autorizados:
   Caminhos autorizados (ex.: /app/api/**):
   Métodos autorizados (liste só os necessários; DELETE só se escrito aqui):
   Caminhos PROIBIDOS, mesmo dentro dos autorizados (ações destrutivas,
   envio de e-mail ou SMS, integrações com terceiros, exclusão de conta):
   Modo de leitura de caminhos pela cerca (marque UM; sem marca vale estrito):
     [ ] estrito (padrão): a cerca recusa caminhos ambíguos (;  %2f  ..  //)
     [ ] amplo: libera mais formas de caminho e nega se QUALQUER leitura do
         caminho casar com um proibido. Risco aceito: um pedido liberado pode
         alcançar outro caminho do mesmo host que não esteja na lista de
         proibidos acima (host e porta nunca mudam). Exige a lista de
         proibidos completa.
   Local do Swagger/OpenAPI (arquivo ou URL de teste):

4. Janela de execução (dias, horário e fuso. Ex.: seg-sex 20:00-06:00 America/Sao_Paulo)

5. Limites de carga
   Requisições por segundo (máximo):
   Duração máxima de uma execução, em minutos:
   Conexões simultâneas do varredor (threads por host):
   O alvo limita logins por minuto? Quanto:

6. Contas de teste (uma por papel necessário)
   Apelido | Papel | Nome da variável de ambiente do usuário | da senha
   (a carta traz os NOMES das variáveis; as senhas são entregues por canal
   seguro direto a quem opera e nunca ao agente)
   O teste de autorização entre contas roda por padrão no `hdast run` (só lê).
   Para ele comparar contas, liste ao menos DUAS contas do MESMO papel; sem
   elas ele diz o que não pôde testar.
   Esse teste manda requisições a mais. Ele só ESCREVE no alvo (atribuição em
   massa, alteração de recurso de outra conta, métodos de escrita) se esta
   carta autorizar:
   [ ] A carta autoriza o teste entre contas a escrever no ambiente
       Frase da carta que autoriza:
   Marque só se o ambiente aguentar. Sem a marca, o teste só lê.
   Com a marca, o teste de cadastro (POST) cria recursos de teste no ambiente;
   eles ficam lá até uma limpeza (cleanup) ou o reset do ambiente.

7. Limpeza dos dados criados
   [ ] Não haverá limpeza automática (ambiente descartável ou recriado)
   [ ] Haverá limpeza por SQL (Oracle). Quem escreve e revisa o script:
       Usuário de banco só da limpeza (SELECT e DELETE nas tabelas abaixo):
       Tabelas permitidas:
       Teto de linhas apagadas:

8. Contato de emergência (nome, telefone, canal) para parar a execução:

9. Assinatura do dono do produto e data:
```

## Como cada campo vira perfil

| Campo da carta | Vira no `target.yml` |
| --- | --- |
| URL base | `environment.base_url` |
| Hosts, caminhos, métodos | `scope.allow` |
| Caminhos proibidos | `scope.deny_paths` |
| Modo de leitura de caminhos | `scope.path_mode`: `strict` (estrito, ou sem marca) ou `wide` (amplo, só se marcado). O agente nunca marca por conta própria |
| Referência e validade | `scope.authorization.reference` e `valid_until` |
| Janela | `scope.windows` |
| Limites | `limits.requests_per_second`, `max_duration_minutes`, `zap_threads_per_host` |
| Logins por minuto | `auth.login_limit.max_per_minute` |
| Contas e nomes dos segredos | `auth.accounts` (`alias`, `role`, `secret_ref: "env:NOME"` ou `"keyring:NOME"`). A carta lista só os **nomes**, nunca a senha: quem a guarda é o time de QA, na própria máquina |
| Quem pode o quê (papéis que podem e que NÃO podem cada função) | **Não vem da carta.** É a tabela `authz.access_matrix` do `target.yml`: conhecimento do produto, decidido por uma pessoa (o dono) e conferido por ela no `hdast profile approve`. O agente só rascunha (`hdast authz <produto> --draft-matrix`); o rascunho não vale nada até a pessoa levá-lo ao perfil e aprovar |
| Limpeza | bloco `cleanup` (escrito pela pessoa; o agente nunca o inventa) |
| OpenAPI | `openapi` |
| Contato de emergência | fora do perfil: quem para a execução (`hdast stop`) e quem autoriza ampliações |

## Formulário `carta.yml` (a carta em formato fechado)

A carta em texto acima continua sendo o documento assinado. Para que o agente **não escreva** `environment`, `scope`, `limits` nem as contas do `target.yml`, as respostas da pessoa são transcritas num arquivo de formato fechado, o `carta.yml`, e a CLI gera esses blocos de forma determinística (ADR 0036):

```bash
hdast init meu-produto --from-letter carta.yml --check   # só confere; lista campo a campo o que falta
hdast init meu-produto --from-letter carta.yml           # confere e cria a pasta com o target.yml gerado
```

O que a carta não responde, o agente pergunta numa rodada só (a entrevista, na ordem do formulário), sem sugerir valor de escopo, limite, janela ou autorização: veja [cadastrar-um-produto.md](cadastrar-um-produto.md#5-a-entrevista-e-a-aprovação-do-escopo). Depois de gerado o perfil, uma pessoa aprova o escopo num terminal dela.

Regras do formulário:

- Cada resposta é `{value, source, quote}`. `source` é `carta` (a carta assinada diz isso), `pessoa` (a pessoa respondeu na entrevista) ou `desconhecido` ("não sei" / "não está na carta", sem `value`). `quote` é a frase de origem (opcional).
- **A resposta vem da pessoa, não do agente.** O agente só transcreve. Campo obrigatório ausente ou `desconhecido` recusa a carta; o agente pergunta de novo à pessoa, nunca preenche por conta própria.
- **`kind`** (no topo, fora de `{value, source}`) é `letter` (carta assinada; vale se ausente) ou `request` (pedido mínimo, [ADR 0120](../decisoes/0120-pedido-minimo-com-padroes-e-aprovacao.md); veja a seção "Pedido mínimo" abaixo). Outro valor é a pendência `INVALID_VALUE` em `kind`; valor que não é texto é erro de forma. Uma carta antiga, sem `kind`, gera exatamente o mesmo `target.yml` e a mesma impressão digital de antes.
- **Portões:** ambiente de teste, dados sintéticos e autorização vigente precisam ser `true`. Um "não" (ou desconhecido) recusa tudo.
- **Valores de exemplo** (`exemplo.com.br`, `SEC-0000`, `MEU_PRODUTO_...`, `CHANGE_ME`) são recusados.
- **Segredos:** só o NOME (`env:NOME` ou `keyring:NOME`). Um valor de senha no lugar do nome é recusado, e a mensagem não o repete.
- **`path_mode: wide`** só vale com `source: carta` e a frase da carta em `quote`. Sem `path_mode`, vale `strict`.
- **`attack.strength`** é opcional; sem ele a CLI não escreve o bloco `scan` e vale o padrão do perfil.
- **`attack.include_outcomes`** é opcional e vale lista vazia se ausente, nulo, `desconhecido` ou `[]` ("não sei" é "não"). É a lista de classes de resposta do `probe` cujas operações o teste ataca **também**: `logical_failure`, `validation_error`, `conflict`, `not_found`, `client_error` (por exemplo, a rota existe, mas o id sorteado deu 404). Aceita `source: carta` ou `pessoa`, sem frase em `quote`: não amplia escopo, método, limite, janela nem conta, só quanto se ataca do que já é permitido. Valor que não é lista, classe fora dessas cinco ou que não é texto é `INVALID_VALUE`. Vira `scan.include_outcomes` no `target.yml`, o resumo da aprovação mostra a lista ("ATACA TAMBÉM OPERAÇÕES QUE DERAM") e a carta pronta traz o aviso `OUTCOMES_ATTACK_EXTENDED`: nos `POST`, `PUT` e `PATCH` isso cria e altera mais dados sintéticos, e achado que parte de uma resposta que não foi sucesso tem menos prova. Só uma pessoa liga (o agente pergunta e transcreve) e a flag `--include-outcome` do `scan` só escolhe dentro dessa lista ([ADR 0050](../decisoes/0050-varrer-operacoes-que-deram-nao-encontrado.md)).
- **`attack.allow_authz_writes`** é opcional e vale `false` se ausente, nulo ou `desconhecido` ("não sei" é `false`). `true` só passa com `source: carta` e a frase da carta em `quote` (`AUTHZ_WRITES_NEEDS_LETTER` caso contrário), e só um booleano é aceito (o texto "sim" é recusado). Vira `authz.allow_writes: true` no `target.yml`, que libera a atribuição em massa e os métodos de escrita do teste entre contas; a carta pronta traz o aviso `AUTHZ_WRITES_AUTHORIZED` para a pessoa confirmar com o dono do produto. Com ele, a atribuição em massa também testa campos tirados do próprio OpenAPI (`authz.derive_mass_candidates`, ADR 0040) e os cadastros (`POST`), e **cada campo testado num cadastro deixa um recurso criado no ambiente de teste**: o `DELETE` é proibido e quem limpa é o `hdast cleanup` ou o reset do ambiente. Dono do recurso (`ownerId`, `tenantId`) só é testado se alguém o declarar. Com ele, a verificação `horizontal_write` ([ADR 0042](../decisoes/0042-escrita-em-recurso-de-outra-conta-e-id-fora-do-caminho.md)) também tenta, com uma conta do mesmo papel, **alterar** o recurso de outra conta por `PUT` e `PATCH` (um campo por pedido, nunca `DELETE`) e a conta dona restaura o valor anterior; se uma parada impedir a restauração, o relatório avisa (`possible_unrestored_change`) e o ambiente de teste precisa ser conferido. A leitura com identificador na consulta (`?pacienteId=2`) não depende deste campo. Sem ele, o teste entre contas só lê. As verificações de pedido sem login e de token adulterado ([ADR 0039](../decisoes/0039-pedido-sem-login-e-token-adulterado.md)) só leem `GET`, não dependem desse campo e rodam por padrão: elas repetem o pedido sem credencial e com o token da conta estragado de propósito (nunca válido, nunca gravado), sempre dentro do escopo e dos limites da carta; operações que o OpenAPI declara anônimas, e login, saúde e preparação, ficam de fora.
- **`attack.allow_upload_scan`** é opcional e vale `false` se ausente, nulo ou `desconhecido` ("não sei" é `false`). `true` só passa com `source: carta` e a frase da carta em `quote` (`UPLOAD_SCAN_NEEDS_LETTER` caso contrário), e só um booleano é aceito (o texto "sim" é recusado). Pergunta própria: o que se autoriza é o **ZAP varrer as operações que recebem arquivo** (`multipart/form-data`), e o varredor grava nelas conteúdo de ataque (nome e conteúdo de arquivo, campos de texto) no armazenamento do alvo, sem que esta ferramenta o controle; a carta pode autorizar o teste de autorização e não isto. Vira `scan.allow_upload_scan: true` no `target.yml` ([ADR 0052](../decisoes/0052-multipart-no-probe-e-no-scan.md)); o resumo da aprovação mostra a linha "VARRE TAMBÉM OPERAÇÕES DE ENVIO DE ARQUIVO" e a carta pronta traz o aviso `UPLOAD_SCAN_AUTHORIZED`, para a pessoa confirmar com o dono do produto. Sem ele o `probe` ainda alcança a operação (com um arquivo sintético), mas o `scan` a pula com o motivo `upload_scan_not_authorized`; o caminho pode também ser proibido em `scope.deny_paths`.
- **`attack.pacing`** (`legacy` ou `proxy`) é opcional e vale `legacy` se ausente, nulo ou `desconhecido`; aceita `source: carta` ou `pessoa`, sem frase. Vira `scan.pacing` só quando é `proxy` ([ADR 0096](../decisoes/0096-bloco-attack-da-carta-liga-capacidades-v1-12.md)).
- **`attack.inject_headers`**, **`attack.oast`**, **`attack.allow_rate_tests`**, **`attack.experimental_rules`** e **`attack.inventory`** são opcionais e valem `false` se ausentes, nulos ou `desconhecido`. `true` só passa com `source: carta` e a frase da carta em `quote` (`ATTACK_FLAG_NEEDS_LETTER` caso contrário), e só um booleano é aceito. Pergunte só se a carta trata do assunto. Cada um gera o aviso `ATTACK_FLAG_AUTHORIZED` e muda a impressão digital da aprovação ([ADR 0096](../decisoes/0096-bloco-attack-da-carta-liga-capacidades-v1-12.md)).
- **`attack.authz_shared_roles`** é uma resposta opcional com lista de nomes de papéis cujas contas compartilham legitimamente os recursos umas das outras. Uma lista preenchida exige `source: carta` e a frase da carta em `quote`; copie apenas o que o dono declarou, sem inferir. Ausente ou desconhecida mantém a lista vazia. A CLI gera `authz.shared_roles`: `horizontal` e `horizontal_write` não comparam contas do mesmo papel listado e registram `shared_role` em `not_tested`. Isso reduz cobertura e não altera as demais verificações. O valor preenchido entra na impressão digital e no resumo da aprovação; o padrão vazio preserva a impressão anterior. [ADR 0057](../decisoes/0057-papeis-compartilhados.md).

  Exemplo ilustrativo, somente quando a carta contiver essa regra:

  ```yaml
  attack:
    authz_shared_roles:
      value: [operador]
      source: carta
      quote: "As contas de operador compartilham os recursos umas das outras."
  ```

- **`attack.allow_invalid_input_writes`** é opcional e vale `false` se ausente, nulo ou `desconhecido` ("não sei" é `false`). `true` só passa com `source: carta` e a frase da carta em `quote` (`NEGATIVE_WRITES_NEEDS_LETTER` caso contrário), e só um booleano é aceito (o texto "sim" é recusado). É outra pergunta que a do teste entre contas: aqui o que se autoriza é **gravar no ambiente dado com valor que o contrato (OpenAPI) proíbe** (um preço negativo, um texto grande demais), para ver se o servidor o rejeita; por isso uma carta pode autorizar uma e não a outra. Vira `negative.allow_writes: true` no `target.yml` ([ADR 0051](../decisoes/0051-valores-que-o-esquema-proibe.md)); a carta pronta traz o aviso `NEGATIVE_WRITES_AUTHORIZED`. Com ele, `PUT` e `PATCH` aceitos são restaurados com o corpo original e um `POST` aceito pode deixar um recurso criado (limpe com `hdast cleanup` ou o reset do ambiente); nunca `DELETE`. Sem ele, o teste só lê (`GET`).
- **`example_data`** (ids, nomes de arquivo, códigos que existem no ambiente) não vira regra: é informação para o agente escrever o `data-rules.yml`.
- Campo desconhecido no arquivo é erro (confira a grafia).

Exemplo comentado, com um produto fictício (uma "Livraria Exemplo" em homologação, sem empresa real; os valores servem só de ilustração, não os copie para outro produto):

```yaml
schema_version: 1
product: livraria-exemplo          # igual ao nome dado ao hdast init

# 1. Portões: sem os quatro respondidos, nada é gerado.
gates:
  test_environment:
    value: true                    # true = é ambiente de teste (não é produção)
    source: carta
    quote: "Ambiente de homologação isolado da loja."
  synthetic_data:
    value: true                    # true = dados sintéticos, sem pessoas reais
    source: carta
  authorization_in_force:
    value: true                    # true = há autorização vigente do dono do produto
    source: pessoa
  product_owner:
    value: "Equipe da loja fictícia (loja@livraria.local)"
    source: carta

# 2. Endereço do ambiente de teste e onde está o OpenAPI (relativo à pasta do produto).
environment:
  name: { value: homologacao, source: carta }
  base_url: { value: "http://livraria-lab:8080", source: carta }
  openapi: { value: ./openapi.json, source: pessoa }

# 3. Escopo: uma regra por host; só o que a carta lista.
scope:
  allow:
    value:
      - host: livraria-lab
        scheme: http
        port: 8080
        allow_local: true          # só para host de laboratório (nome de contêiner, localhost, IP)
        paths: ["/loja/api/**", "/loja/docs"]
        methods: [GET, POST, PUT]  # PATCH e DELETE ficam de fora: a carta não os autoriza
    source: carta
    quote: "GET, POST e PUT em /loja/api/** e /loja/docs; PATCH e DELETE não."
  deny_paths:                      # proibidos mesmo dentro dos autorizados (lista vazia só se a pessoa disser "nenhum")
    value: ["/loja/api/pagamentos/**", "/loja/api/conta/excluir"]
    source: carta
  path_mode: { value: strict, source: carta }   # opcional; wide só com source: carta e quote

# 4. Referência, validade e janela(s).
authorization:
  reference: { value: "LIVRARIA-HML-2027-01", source: carta }
  valid_until: { value: 2027-06-30, source: carta }
  windows: { value: ["seg-sex 19:00-06:00 America/Sao_Paulo"], source: carta }

# 5. Limites de carga.
limits:
  requests_per_second: { value: 20, source: carta }
  max_duration_minutes: { value: 45, source: carta }
  zap_threads_per_host: { value: 4, source: carta }

# 6. Como entrar e com quais contas (só NOMES de segredo, nunca a senha).
auth:
  type: { value: login_password, source: pessoa }      # ou api_key (então use header_name)
  token_path: { value: /loja/api/sessao, source: pessoa }
  login_options:                                        # opcional
    value: { request_encoding: form }
    source: pessoa
  login_max_per_minute: { value: 3, source: carta }     # opcional
  accounts:
    source: carta
    value:
      - alias: gerente_a
        role: gerente
        username: { secret_ref: "env:LIVRARIA_GERENTE_USERNAME" }
        password: { secret_ref: "env:LIVRARIA_GERENTE_PASSWORD" }
      - alias: cliente_a
        role: cliente
        username: { secret_ref: "env:LIVRARIA_CLIENTE_A_USERNAME" }
        password: { secret_ref: "env:LIVRARIA_CLIENTE_A_PASSWORD" }
      - alias: cliente_b
        role: cliente
        username: { secret_ref: "env:LIVRARIA_CLIENTE_B_USERNAME" }
        password: { secret_ref: "env:LIVRARIA_CLIENTE_B_PASSWORD" }

# 7. Intensidade do ataque (opcional): LOW, MEDIUM ou HIGH. Ausente = padrão do perfil.
attack:
  strength: { value: MEDIUM, source: pessoa }

# 8. Dados que existem no ambiente (opcional): informação para o agente, não vira regra.
example_data:
  source: carta
  value:
    - { operation: buscarLivroPorIsbn, field: isbn, value: "9780000000001", note: "livro da semente" }
    - { operation: baixarCapa, field: arquivo, value: capa-0001.png }
```

Do `carta.yml` ao `target.yml`, campo a campo:

| `carta.yml` | `target.yml` |
| --- | --- |
| `environment.name`, `base_url` | `environment.name`, `base_url` |
| `environment.openapi` | `openapi` |
| `scope.allow`, `deny_paths`, `path_mode` | `scope.allow`, `scope.deny_paths`, `scope.path_mode` |
| `authorization.reference`, `valid_until` | `scope.authorization.reference`, `valid_until` |
| `authorization.windows` | `scope.windows` |
| `limits.*` | `limits.*` |
| `auth.type`, `token_path` ou `header_name`, `login_options` | `auth.type`, `auth.token_path` ou `auth.header_name`, os campos de login |
| `auth.login_max_per_minute` | `auth.login_limit.max_per_minute` |
| `auth.accounts` | `auth.accounts` |
| `attack.strength` | `scan.strength` (só se informado) |
| `attack.include_outcomes` | `scan.include_outcomes` (só se a lista não for vazia) |
| `attack.authz_shared_roles` | `authz.shared_roles` (lista preenchida só com `source: carta` e `quote`) |
| `attack.allow_authz_writes` | `authz.allow_writes: true` (só se `true` com `source: carta` e `quote`) |
| `attack.allow_invalid_input_writes` | `negative.allow_writes: true` (só se `true` com `source: carta` e `quote`) |
| `attack.allow_upload_scan` | `scan.allow_upload_scan: true` (só se `true` com `source: carta` e `quote`) |
| `attack.pacing` | `scan.pacing: proxy` (só se `proxy`) |
| `attack.inject_headers` | `scan.inject_headers: true` (só se `true` com `source: carta` e `quote`) |
| `attack.oast` | `scan.oast: true` (só se `true` com `source: carta` e `quote`) |
| `attack.allow_rate_tests` | `extra_checks.allow_rate_tests: true` (só se `true` com `source: carta` e `quote`) |
| `attack.experimental_rules` | `extra_checks.experimental_rules: true` (só se `true` com `source: carta` e `quote`) |
| `attack.inventory` | `extra_checks.inventory: true` (só se `true` com `source: carta` e `quote`) |
| `attack.allow_data_writes` (só `kind: request`) | `authz.allow_writes`, `negative.allow_writes` e `scan.allow_upload_scan`, os três `true` (só se `true`; a chave individual explícita vence) |
| `scope.allow_delete` (só `kind: request`) | acrescenta `DELETE` aos métodos da regra gerada |
| `kind`, `gates.*`, `example_data` | não viram campo do perfil |

O resto do `target.yml` (`probe`, `auth.csrf`, `auth.account_map`, os demais campos de `authz`, `cleanup`) não vem da carta e continua sendo escrito nas etapas seguintes. Isso inclui a tabela "quem pode o quê" (`authz.access_matrix`): a carta registra a autorização para tocar o alvo, e a tabela é o que o dono do produto sabe sobre os papéis; por isso não há campo dela na carta.

## Pedido mínimo (`kind: request`)

Quando o QA entrega só o Swagger, as contas e a documentação de negócio, sem carta assinada, a carta leva `kind: request` e a pessoa responde **só quatro perguntas** ([ADR 0120](../decisoes/0120-pedido-minimo-com-padroes-e-aprovacao.md)). A CLI completa o resto com uma tabela de padrões fixa no código, escreve **cada valor de forma explícita** no `target.yml` e a pessoa o aprova no `hdast setup`. Os padrões do modelo do perfil não mudam, e perfis e aprovações existentes continuam válidos.

| # | Pergunta | Onde vai na carta | Com "não" ou "não sei" |
| --- | --- | --- | --- |
| 1 | Ambiente de teste, dados sintéticos, autorização do dono do produto; quem é o dono | `gates.*` | **Para o cadastro** |
| 2 | Endereço do ambiente de teste (o `servers` do Swagger só aparece como sugestão) | `environment.base_url` | **Para o cadastro** |
| 3 | Força do ataque: `LOW`, `MEDIUM` ou `HIGH` | `attack.strength` | `LOW` |
| 4 | O ambiente pode receber dados gravados pela ferramenta? | `attack.allow_data_writes` (`source: pessoa`, sem frase) | As três escritas ficam desligadas |

Além das quatro respostas, a carta traz `environment.openapi` (o OpenAPI, **ao lado da carta**: a CLI lê o escopo dele; o mesmo nome vale depois dentro da pasta do produto) e `auth` com tipo, rota do login e as contas (apelido, papel e **nome** do segredo; nunca o valor). Carta mínima:

```yaml
schema_version: 1
kind: request
product: meu-produto
gates:
  test_environment: { value: true, source: pessoa }
  synthetic_data: { value: true, source: pessoa }
  authorization_in_force: { value: true, source: pessoa }
  product_owner: { value: "Fulana de Tal (fulana@empresa.com.br)", source: pessoa }
environment:
  base_url: { value: "https://api.hml.empresa.com.br", source: pessoa }
  openapi: { value: ./openapi.json, source: pessoa }
auth:
  type: { value: login_password, source: pessoa }
  token_path: { value: /api/auth/login, source: pessoa }
  accounts:
    source: pessoa
    value:
      - alias: user_a
        role: usuario
        username: { secret_ref: "keyring:MEU_PRODUTO_USER_A_LOGIN" }
        password: { secret_ref: "keyring:MEU_PRODUTO_USER_A_SENHA" }
attack:
  strength: { value: LOW, source: pessoa }
  allow_data_writes: { value: false, source: pessoa }
```

**Padrões aplicados** (tabela única em `domain/request_defaults.py`; cada um gera o aviso `REQUEST_DEFAULT_APPLIED` com o campo e o valor, e uma linha `# Padrão do pedido mínimo:` no cabeçalho do `target.yml`):

| Campo | Padrão |
| --- | --- |
| `scope.allow` | Host, esquema e porta de `environment.base_url` (e o prefixo do caminho, se houver); todos os caminhos do OpenAPI, com `{x}` virando o curinga `*`; métodos `GET`, `POST`, `PUT` e `PATCH`. Host local do laboratório recebe `allow_local: true` |
| `DELETE` | Fora. Só entra com `scope.allow_delete: {value: true, source: pessoa}` |
| `scope.deny_paths` | Sugestão por nome de segmento: recuperação, esquecimento e troca de senha (`forgot`, `forget`, `reset`, `recover`, `password`), `logout` e `signout`, exclusão de conta e `admin`. O que a pessoa escrever **soma** à sugestão e nunca a remove; o caminho do login nunca é sugerido |
| `scope.path_mode` | `strict`, sempre; o `wide` só vale na carta `kind: letter`, com frase |
| `authorization.reference` | `pedido-<produto>-<AAAA-MM-DD> (dono: <nome>)` |
| `authorization.valid_until` | Dia do cadastro mais 30 dias |
| `authorization.windows` | `seg-dom 00:00-24:00 <fuso>`; fuso da variável `TZ` se for um nome IANA válido, senão `America/Sao_Paulo` |
| `limits` | 10 req/s, 30 min, 2 threads; `auth.login_max_per_minute` 5 (só com login por senha) |
| `environment.name` | `teste` |
| `scan.strength` | A resposta 3; sem resposta, `LOW` |
| `scan.include_outcomes` | `not_found`, `validation_error`, `conflict`, `logical_failure` e `client_error` |
| `scan.inject_headers`, `scan.oast`, `extra_checks.*` | Ligados. Sem o serviço de retorno, a varredura segue sem OAST |
| `scan.pacing` | `proxy` |
| `authz.allow_writes`, `negative.allow_writes`, `scan.allow_upload_scan` | **Nunca por padrão.** Ligam todos com a pergunta 4 `true`; uma chave individual explícita (`allow_authz_writes`, `allow_invalid_input_writes`, `allow_upload_scan`) vence a agrupada |

**Resposta explícita vence o padrão**, inclusive para desligar (`value: false`, lista vazia, força escolhida). `desconhecido` e campo ausente recebem o padrão. A exceção é `scope.deny_paths`, que só soma. Na carta `kind: letter`, as chaves `attack.allow_data_writes` e `scope.allow_delete` são recusadas (`REQUEST_ONLY`): ali cada capacidade segue exigindo `source: carta` e a frase. Carta `request` sem o OpenAPI legível ao lado dela fica pendente com `OPENAPI_UNREADABLE`.

## Regras

- Se o escopo parecer curto demais, peça ao dono do produto uma carta nova. Ninguém amplia por conta própria.
- Autorização vencida ou janela fechada: a CLI se recusa (saída `3`). Não há flag que contorne.
- Guarde a carta junto da referência; a referência vai em todo relatório.

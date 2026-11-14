# Modelo de carta de autorização

Peça este documento ao dono do produto **antes** de cadastrar o produto. Sem ele preenchido e assinado, não há perfil: `scope`, `limits`, `authorization` e as janelas do perfil são **transcritos daqui**, nunca inventados (nem por você, nem pelo agente). Se algum campo ficar em branco, o cadastro para.

Fundamento: [authorization-and-scope.md](../operations/authorization-and-scope.md). Campos do perfil: [target-yml.md](../reference/target-yml.md).

Só ambiente de **teste**, com **dados sintéticos**. Produção e dados de pessoas reais ficam de fora.

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
   Para o teste de autorização entre contas (`hdast run --authz`), liste ao
   menos DUAS contas do MESMO papel; sem elas esse teste não compara contas.
   Esse teste manda requisições a mais e escreve no alvo (atribuição em massa):
   autorize só se o ambiente aguentar.

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
- **Portões:** ambiente de teste, dados sintéticos e autorização vigente precisam ser `true`. Um "não" (ou desconhecido) recusa tudo.
- **Valores de exemplo** (`exemplo.com.br`, `SEC-0000`, `MEU_PRODUTO_...`, `CHANGE_ME`) são recusados.
- **Segredos:** só o NOME (`env:NOME` ou `keyring:NOME`). Um valor de senha no lugar do nome é recusado, e a mensagem não o repete.
- **`path_mode: wide`** só vale com `source: carta` e a frase da carta em `quote`. Sem `path_mode`, vale `strict`.
- **`attack.strength`** é opcional; sem ele a CLI não escreve o bloco `scan` e vale o padrão do perfil.
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
| `gates.*`, `example_data` | não viram campo do perfil |

O resto do `target.yml` (`probe`, `auth.csrf`, `auth.account_map`, `authz`, `cleanup`) não vem da carta e continua sendo escrito nas etapas seguintes.

## Regras

- Se o escopo parecer curto demais, peça ao dono do produto uma carta nova. Ninguém amplia por conta própria.
- Autorização vencida ou janela fechada: a CLI se recusa (saída `3`). Não há flag que contorne.
- Guarde a carta junto da referência; a referência vai em todo relatório.

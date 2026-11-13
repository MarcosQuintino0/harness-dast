# Notas do perfil da Clínica Piloto: o que o schema v1 ainda não expressa

Para o orquestrador. O `target.yml`, o `data-rules.yml` e o `flows.yml` desta pasta são aceitos pela CLI atual
(`hdast profile validate` devolve `runnable: true`; `hdast spec inspect` devolve `issues: []`, 29 operações,
`enviarNotificacao` em `skipped_denied`, os dois `DELETE` em `skipped_scope`). Nenhum campo foi inventado.
Esta página lista o que o alvo exige e o schema não consegue dizer. Cada item é um comportamento real do alvo,
verificado nos testes dele (`lab/pilot/src/test`) e nos contêineres.

## 1. XSRF (o maior bloqueio)

Toda escrita (`POST`, `PUT`, `PATCH`, `DELETE`) exige o par XSRF, exceto o login. Sem ele: `403` com
`code = XSRF_INVALIDO`. Como o cliente obtém e envia:

1. `GET /api/csrf` (público). A resposta define o cookie `XSRF-TOKEN=<valor>` (`Path=/`, `SameSite=Strict`, sem
   `HttpOnly`) e devolve o mesmo valor no corpo: `{"token": "...", "headerName": "X-XSRF-TOKEN", "cookieName": "XSRF-TOKEN"}`.
   Qualquer `GET` também define o cookie; `/api/csrf` é o caminho documentado.
2. Na escrita, enviar o cookie `XSRF-TOKEN` **e** o cabeçalho `X-XSRF-TOKEN` com o mesmo valor.
3. O valor não expira nem gira por requisição: vale enquanto o cliente reenviar o mesmo cookie.

O que o schema precisaria expressar (nomes sugeridos, não existentes):

| Necessidade | Sugestão |
| --- | --- |
| Onde buscar o token | `auth.xsrf.fetch: { method: GET, path: /api/csrf }` (precisa passar pelo `scope.allow`) |
| De onde ler o valor | `auth.xsrf.token_from: cookie` + `cookie_name: XSRF-TOKEN` (ou `response_field: token`) |
| Em que cabeçalho devolver | `auth.xsrf.header_name: X-XSRF-TOKEN` |
| Quais métodos exigem | `auth.xsrf.methods: [POST, PUT, PATCH, DELETE]` |
| Exceções | `auth.xsrf.exempt_paths: [/api/auth/login]` |
| Cookie no ZAP | o jar do ZAP precisa guardar o cookie; a regra do cabeçalho (replacer) precisa acompanhar o valor |

Sem isso, `hdast probe` não consegue criar nada (toda escrita volta 403) e a varredura ativa do ZAP também só
vê 403 nas escritas. Para desenvolver a ferramenta em etapas, o alvo aceita `PILOT_XSRF_ENFORCED=0`, que não
exige o par (o cookie e `/api/csrf` continuam existindo). É um botão de depuração do cliente, não uma fraqueza.

## 2. Vida do token e renovação

- O login devolve `{"access_token", "token_type": "Bearer", "expires_in": 300, "papel"}`. O perfil atual lê
  `access_token` (certo) e envia `Authorization: Bearer` (certo), mas não conhece `expires_in`.
- `PILOT_JWT_TTL_SECONDS` muda a vida do token (padrão 300 s). Token vencido: `401` com `code = TOKEN_EXPIRADO`;
  token inválido: `401` com `TOKEN_INVALIDO`; sem token: `401` com `NAO_AUTENTICADO`.
- O token deixa de valer também quando o alvo reinicia (a chave de assinatura é sorteada a cada subida).
- Necessário no schema: `auth.token_expires_field: expires_in` (ou TTL fixo), `auth.refresh: { before_seconds: 30,
  on_status: [401], on_codes: [TOKEN_EXPIRADO] }` e a regra de que uma renovação consome uma tentativa de login
  (item 4). Em varreduras longas o ZAP precisa receber o token novo (P-10 do roadmap).

## 3. Critério de sucesso além de "HTTP 2xx"

- Aqui o código HTTP já diz a verdade (ao contrário do VAmPI): criações devolvem `201`, a notificação `202`,
  remoções `204`, e os erros usam 400/401/403/404/409/422/429.
- Mas o `probe` precisa **classificar o erro** para reagir, e o corpo de erro é sempre
  `{"code", "message", "errors": [{"field", "rule", "message"}]}`. Mapeamento que o schema deveria permitir:

| `code` | Status | Significa para o harness |
| --- | --- | --- |
| `VALIDACAO`, `CORPO_INVALIDO`, `PARAMETRO_INVALIDO` | 400 | dado gerado inválido: pedir regra para o campo em `errors[].field` |
| `CONFLITO` | 409 | valor único repetido (`errors[].field` = `cpf`, `email`, `codigo`, `crm`): gerar valor novo |
| `REFERENCIA_INEXISTENTE` | 422 | encadeamento quebrado: o id do pai não existe |
| `TRANSICAO_INVALIDA`, `CONSULTA_CANCELADA`, `EM_USO` | 409 | regra de estado: não é falha de dado nem de alvo |
| `XSRF_INVALIDO` | 403 | sessão/cookie: refazer `GET /api/csrf` |
| `TOKEN_EXPIRADO`, `TOKEN_INVALIDO` | 401 | renovar o token |
| `ACESSO_NEGADO` | 403 | papel errado para a operação: usar outra conta |
| `LIMITE_EXCEDIDO` | 429 | respeitar `Retry-After` (item 4) |

- Sugestão: `probe.success_status` por operação (ex.: `criarPaciente: [201]`) e `probe.error_code_field: code`.

## 4. Limite de taxa (429) no login

- `POST /api/auth/login` aceita 5 tentativas por minuto por origem (`PILOT_LOGIN_MAX_PER_MINUTE`), **contando
  também as erradas**. A 6ª em 60 s recebe `429`, `code = LIMITE_EXCEDIDO` e cabeçalho `Retry-After: <segundos>`.
- Atrás do proxy de saída do lab todo o tráfego tem a mesma origem, então o limite vale para o conjunto de
  contas e renovações. Com 4 contas no perfil, `preflight` (um login por conta) já gasta 4 das 5 tentativas.
- Necessário: `limits.login_attempts_per_minute` (ou `auth.rate_limit.respect_retry_after: true`) e um orçamento
  de logins no `preflight`/renovação. `limits.requests_per_second` não cobre isso.

## 5. Encadeamento de mais de um nível

O fluxo do alvo é `convenio -> paciente -> consulta -> receita` (3 elos). A regra "produtora OU consumidora"
(P-12) recusa `criarPaciente` ser as duas coisas. O `flows.yml` desta pasta expressa só `criarConvenio ->
(criarPaciente, buscarConvenio, atualizarConvenio)` e `criarMedico -> buscarMedico`. Os elos seguintes usam
`constant` com os ids de semente no `data-rules.yml` (paciente 1, médico 1, consulta 1), o que contorna o limite
mas **não exercita o encadeamento real**. Os ids de semente são estáveis (`POST /internal/eval/reset` os restaura).

## 6. Geradores que faltam

- **CRM único no formato `NNNNN-UF`** (`^\d{4,7}-[A-Z]{2}$`): não há gerador que una dígitos únicos a um sufixo
  fixo. Sem regra, o valor implícito do `pattern` pode repetir entre execuções e dar `409` em `criarMedico`.
  Sugestão: um gerador `template` (`"{numeric:5}-SP"`) com `unique`.
- `email` precisa de domínio de teste e `cpf` de dígitos verificadores: já cobertos por `email` e `br.cpf`.

## 7. Contas e papéis por operação

Criar convênio e médico exige `admin`; criar paciente e receita, `medico` ou `admin`; `paciente` só vê e altera
o que é seu. A V1 usa uma conta (`admin_a`, a primeira da lista, que cobre tudo). Para exercitar permissões é
preciso escolher a conta por operação (`accounts[].operations` ou um mapa papel -> operações). As 4 contas já
estão no perfil para quando isso existir.

## 8. Limpeza (`cleanup`)

- O `cleanup.sql` desta pasta (cópia de `lab/pilot/cleanup/cleanup.sql`) usa as variáveis de ligação
  `:run_start` (TIMESTAMP em UTC do início da execução) e `:account_1` a `:account_4` (usernames das contas).
  O `cleanup/README.md` do modelo cita `:run_id` e `:test_account`: o schema precisa dizer **quais binds a CLI
  fornece e de onde vêm** (`cleanup.binds`), ou o modelo de nomes precisa mudar.
- O script tem 5 comandos terminados em `;` (sem `COMMIT`); a CLI precisa separá-los e contar as linhas de cada um.
- `PILOT_ORACLE_CLEANUP_CONNECTION` (o `secret_ref`) deve ser a cadeia de conexão de um usuário Oracle só com
  `DELETE` nas 5 tabelas (`clinica/<senha>@oracle:1521/FREEPDB1` no perfil `oracle` do compose). Com o banco H2
  padrão não há conexão externa: a limpeza se prova pelo `POST /internal/eval/reset` do avaliador.

## 9. Outros pontos

- O `servers` do OpenAPI é `http://localhost:8080`, fora do escopo do perfil (`clinica-piloto:8080`); o
  `spec inspect` já avisa em `servers_out_of_scope`. Está certo: a CLI deve usar a `base_url` do perfil.
- `GET /api/documentos/download` responde `application/octet-stream`; o `probe` não deve exigir JSON.
- O alvo ignora corpo extra e não exige `Content-Type` além de `application/json` nas escritas (415 caso contrário).
- O estado de avaliação (`/internal/eval/*`, porta 9091) está fora do OpenAPI e do escopo; só o avaliador o usa.

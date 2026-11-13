# Clínica Piloto: alvo de treino local

> **AVISO. Software de treino, intencionalmente vulnerável.** A Clínica Piloto é uma API fictícia, escrita para
> ser testada pelo harness-dast e pelo agente de IA dele em um ambiente que controlamos. No modo padrão
> (`PILOT_VULNERABLE=1`) ela contém falhas deliberadas. **Rode só em localhost / Docker local.** Nunca publique
> a porta fora da máquina, nunca use `--network host` em máquina com IP público (a aplicação se recusa a subir
> quando uma interface tem endereço público e imprime um aviso no início do log), nunca a coloque em servidor
> compartilhado. Todos os dados são fictícios.

## O que é

Uma API REST pequena em Spring Boot 3.5 / Java 21 que imita um produto de uma healthtech brasileira
(Java + Oracle): convênios, médicos, pacientes, consultas e receitas, com JWT, proteção XSRF, validações,
unicidade, propriedade de registros, limite de tentativas de login e um endpoint que simula envio de SMS/e-mail.
Serve de alvo para o piloto final e para a avaliação cega (`docs/adr/0014-avaliacao-cega-como-eval.md`).

- Banco: **H2 em modo Oracle** por padrão (sobe em segundos, sem Oracle) ou **Oracle Database Free** (perfil `oracle`).
- Esquema por Flyway (`src/main/resources/db/migration`), válido nos dois bancos.
- OpenAPI 3 gerado pelo springdoc em `/v3/api-docs`; cópia estática em [`openapi.json`](openapi.json).

## Construir, subir, parar

Não precisa de JDK no computador: o `Dockerfile` compila e **roda os testes de integração** dentro do build.

```bash
cd lab/pilot
cp .env.example .env            # e troque TODOS os CHANGE_ME por valores seus (o .env é ignorado pelo git)
docker compose --env-file .env up -d --build --wait    # constrói (com testes), sobe e espera ficar saudável
docker compose --env-file .env down                    # para e remove
```

Sem as variáveis de conta o compose falha dizendo qual falta. As portas ficam **só em 127.0.0.1**:

| Porta do host | Para quê |
| --- | --- |
| `127.0.0.1:18080` | API e `/v3/api-docs` (`PILOT_HOST_PORT`) |
| `127.0.0.1:19091` | Estado de avaliação `/internal/eval/*`, fora do OpenAPI (`PILOT_MGMT_HOST_PORT`) |

### Alternar o modo

`PILOT_VULNERABLE=1` (padrão do laboratório) ou `0` (versão corrigida). O `openapi.json` é idêntico nos dois.

```bash
PILOT_VULNERABLE=0 docker compose --env-file .env up -d --wait --force-recreate pilot
```

### Zerar o estado

`POST http://127.0.0.1:19091/internal/eval/reset` restaura a semente (e zera contadores e o limite de login). Reiniciar o
contêiner faz o mesmo, inclusive com Oracle (a subida sempre volta ao estado de semente).

```bash
curl -X POST http://127.0.0.1:19091/internal/eval/reset
curl http://127.0.0.1:19091/internal/eval/state     # contadores: notificações, requisições por rota, linhas por tabela
```

## Como um cliente precisa falar com ela

### 1. Login e vida do token

```bash
curl -s -X POST http://127.0.0.1:18080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<usuário>","password":"<senha>"}'
# {"access_token":"<jwt>","token_type":"Bearer","expires_in":300,"papel":"admin"}
```

- Use o token em `Authorization: Bearer <access_token>` em tudo que não é público.
- O token vale `expires_in` segundos (`PILOT_JWT_TTL_SECONDS`, padrão 300). Vencido: `401` com `code = TOKEN_EXPIRADO`;
  refaça o login. A chave de assinatura é sorteada a cada subida, então reiniciar o alvo invalida todos os tokens.
- Contas semeadas na subida a partir do `.env`: `admin`, `medico`, `paciente A` e `paciente B`. Papéis: `paciente`, `medico`, `admin`.
- Limite de login: `PILOT_LOGIN_MAX_PER_MINUTE` tentativas por minuto e por origem (padrão 5, **contando as erradas**).
  Estourou: `429` com `Retry-After: <segundos>` e `code = LIMITE_EXCEDIDO`.

### 2. XSRF nas escritas (`POST`, `PUT`, `PATCH`, `DELETE`)

Padrão de duplo envio (o do `CookieCsrfTokenRepository` do Spring Security). O login é a única escrita isenta.

```bash
# a) obter o token: define o cookie XSRF-TOKEN e devolve o mesmo valor no corpo
curl -s -c jar.txt http://127.0.0.1:18080/api/csrf
# {"token":"<xsrf>","headerName":"X-XSRF-TOKEN","cookieName":"XSRF-TOKEN"}

# b) em cada escrita: enviar o cookie E o cabeçalho com o mesmo valor, mais o Bearer
curl -s -b jar.txt -X POST http://127.0.0.1:18080/api/convenios \
  -H "X-XSRF-TOKEN: <xsrf>" -H "Authorization: Bearer <jwt>" -H 'Content-Type: application/json' \
  -d '{"codigo":"12345678","nome":"Plano Teste","tipo":"INDIVIDUAL","coparticipacaoPercentual":10}'
```

Faltando um dos dois ou com valores diferentes: `403` com `code = XSRF_INVALIDO`. O valor não expira e não gira
por requisição; vale enquanto o cliente reenviar o mesmo cookie. O cookie não é `HttpOnly` (o cliente precisa lê-lo)
e é `SameSite=Strict`. `GET` não exige nada.

### 3. Corpo de erro (sempre o mesmo formato)

```json
{ "code": "VALIDACAO", "message": "...", "errors": [ { "field": "codigo", "rule": "Pattern", "message": "..." } ] }
```

| Situação | Status | Exemplo real |
| --- | --- | --- |
| Validação de campo (regra nomeada) | 400 | `{"code":"VALIDACAO","message":"Requisição inválida. codigo: deve ter exatamente 8 dígitos numéricos","errors":[{"field":"codigo","rule":"Pattern","message":"deve ter exatamente 8 dígitos numéricos"}]}` |
| CPF com dígito verificador inválido | 400 | `... "errors":[{"field":"cpf","rule":"Cpf","message":"dígitos verificadores do CPF inválidos"}]` |
| Enum, JSON ou tipo inválido | 400 | `code`: `CORPO_INVALIDO` ou `PARAMETRO_INVALIDO` (a mensagem lista os valores aceitos) |
| Sem token / token ruim / vencido | 401 | `NAO_AUTENTICADO`, `TOKEN_INVALIDO`, `TOKEN_EXPIRADO`, `CREDENCIAIS_INVALIDAS` |
| XSRF ausente ou diferente | 403 | `{"code":"XSRF_INVALIDO","message":"Token XSRF ausente ou diferente do cookie. Faça GET /api/csrf e envie o valor no cabeçalho X-XSRF-TOKEN junto com o cookie XSRF-TOKEN.","errors":[]}` |
| Papel ou dono errado | 403 | `ACESSO_NEGADO` |
| Id inexistente na URL | 404 | `{"code":"NAO_ENCONTRADO","message":"Paciente 99999 não encontrado(a).","errors":[]}` |
| Valor único repetido (`cpf`, `email`, `codigo`, `crm`) | 409 | `{"code":"CONFLITO","message":"Já existe um registro com este valor de 'codigo'.","errors":[{"field":"codigo","rule":"unique",...}]}` |
| Regra de estado | 409 | `TRANSICAO_INVALIDA`, `CONSULTA_CANCELADA`, `EM_USO` |
| Corpo aponta para pai inexistente | 422 | `{"code":"REFERENCIA_INEXISTENTE","message":"Convênio 99999 não existe. Crie-o antes (ou use um id válido).","errors":[{"field":"convenioId","rule":"exists",...}]}` |
| Limite de login | 429 | `LIMITE_EXCEDIDO` + cabeçalho `Retry-After` |
| Falha interna | 500 | `{"code":"ERRO_INTERNO","message":"Erro interno do servidor.","errors":[]}` |

### 4. Regras de dados que o cliente precisa respeitar

- `convenio.codigo`: exatamente 8 dígitos, único. `medico.crm`: `NNNNN-UF` (ex.: `12345-SP`), único.
- `paciente.cpf`: 11 dígitos **com dígitos verificadores válidos**, único. `paciente.email`: e-mail, único. Nascimento no passado.
- `consulta.dataHora` no futuro; `consulta.valor` de 0 a 5000 com até 2 casas; `receita.duracaoDias` de 1 a 365.
- Enums: `sexo` (FEMININO, MASCULINO, OUTRO, NAO_INFORMADO), `tipo` do convênio, `especialidade`, `status` da consulta, `canal`.
- Ids encadeados: `convenioId` -> paciente; `pacienteId` e `medicoId` -> consulta; `consultaId` -> receita.
  Pai inexistente: `422`. Ids de semente: convênio 1, médicos 1 e 2, pacientes 1 e 2, consultas 1 e 2.
- Um `paciente` só enxerga e altera os próprios registros (o paciente A tem o id 1; o B, o id 2).
- `POST /api/notificacoes/enviar` **só incrementa um contador e registra no log** (nada é enviado), mas **nunca deve ser
  chamado por um teste bem configurado**: o perfil dele a lista em `scope.deny_paths`.

## Entidades e fluxo

```mermaid
erDiagram
    CONVENIO ||--o{ PACIENTE : "convenioId"
    PACIENTE ||--o{ CONSULTA : "pacienteId"
    MEDICO   ||--o{ CONSULTA : "medicoId"
    CONSULTA ||--o{ RECEITA  : "consultaId"
    PACIENTE ||--o| USUARIO  : "conta do paciente"
    MEDICO   ||--o| USUARIO  : "conta do médico"
```

```mermaid
flowchart LR
    A[GET /api/csrf] --> B[POST /api/auth/login]
    B --> C[criarConvenio] --> D[criarPaciente] --> E[criarConsulta] --> F[criarReceita]
    E --> G[PATCH status: REALIZADA ou CANCELADA]
```

## Endpoints

Todos com `Authorization: Bearer`, salvo os públicos (login, csrf, saúde, api-docs). Escritas exigem o par XSRF.

| Método e caminho | operationId | Quem pode |
| --- | --- | --- |
| `GET /api/csrf` | obterCsrf | público |
| `POST /api/auth/login` | login | público (limite de tentativas) |
| `GET /api/saude` | verificarSaude | público |
| `GET /v3/api-docs` | (OpenAPI) | público |
| `GET /api/me`, `PUT /api/me` | obterPerfil, atualizarPerfil | qualquer conta |
| `POST /api/convenios`, `PUT /api/convenios/{id}`, `DELETE /api/convenios/{id}` | criarConvenio, atualizarConvenio, removerConvenio | admin |
| `GET /api/convenios`, `GET /api/convenios/{id}` | listarConvenios, buscarConvenio | qualquer conta |
| `POST /api/medicos` | criarMedico | admin |
| `GET /api/medicos`, `GET /api/medicos/{id}` | listarMedicos, buscarMedico | qualquer conta |
| `POST /api/pacientes` | criarPaciente | medico, admin |
| `GET /api/pacientes?page&size` | listarPacientes | equipe vê todos; paciente só o próprio |
| `GET /api/pacientes/busca?nome=` | buscarPacientesPorNome | medico, admin |
| `GET/PUT /api/pacientes/{id}` | buscarPaciente, atualizarPaciente | equipe ou o próprio paciente |
| `DELETE /api/pacientes/{id}` | removerPaciente | admin |
| `POST /api/consultas` | criarConsulta | equipe; paciente só para si |
| `GET /api/consultas`, `GET /api/consultas/{id}` | listarConsultas, buscarConsulta | equipe vê todas; paciente as próprias |
| `PATCH /api/consultas/{id}/status` | atualizarStatusConsulta | equipe; paciente só cancela a própria |
| `POST /api/receitas` | criarReceita | medico, admin |
| `GET /api/receitas/{id}`, `GET /api/consultas/{id}/receitas` | buscarReceita, listarReceitasDaConsulta | equipe ou o paciente da consulta |
| `GET /api/documentos`, `GET /api/documentos/download?arquivo=` | listarDocumentos, baixarDocumento | qualquer conta |
| `POST /api/notificacoes/enviar` | enviarNotificacao | qualquer conta (**deny_paths**) |

Fora do OpenAPI e só na porta 9091: `GET /internal/eval/state` e `POST /internal/eval/reset`.

## Testes

Os testes de integração (Spring MockMvc sobre o aplicativo inteiro, H2 em modo Oracle) rodam **durante o build**:
`docker compose build` falha se algum quebrar. Cobrem: login e expiração do token, XSRF, cada regra 400/409/422/404,
encadeamento, propriedade, limite de login e `Retry-After`, contador de notificações, endpoints de estado e reset,
o `cleanup.sql` rodando de verdade, e o `openapi.json` sem deriva. Para reexecutá-los sem usar o cache:

```bash
docker build --target build --build-arg TESTS_RERUN=$(date +%s) lab/pilot     # a saída mostra "Tests run: N, Failures: 0"
```

Cada item do modo padrão tem teste que prova o comportamento no modo `1` e o oposto no modo `0`
(`WeaknessesVulnerableModeTest` e `WeaknessesHardenedModeTest`). O que cada um é fica no gabarito
(`evals/answer-keys/`), não aqui.

## OpenAPI

`openapi.json` é gerado pela aplicação e versionado. O teste `OpenApiDriftTest` (e o `OpenApiHardenedModeTest`, para o
modo corrigido) **falha o build** se o arquivo divergir do `/v3/api-docs` gerado. Para regenerar depois de mudar a API:

```bash
docker build --target openapi-out --output type=local,dest=lab/pilot lab/pilot     # reescreve lab/pilot/openapi.json
cp lab/pilot/openapi.json lab/pilot/product-profile/openapi.json
lab/pilot/scripts/check-sync.sh                                                     # confere cópias e a API ao vivo
```

## Limpeza (Oracle)

[`cleanup/cleanup.sql`](cleanup/cleanup.sql) é o hook de limpeza **escrito por uma pessoa**: SQL Oracle com variáveis de ligação
(`:run_start` em UTC e `:account_1` a `:account_4`) que apaga, em ordem de dependência (receita, consulta, paciente, médico,
convênio), só as linhas criadas pelas contas de teste desde o início da execução (`CREATED_BY` e `CREATED_AT`). Linhas da
semente (`seed`) e de outras contas nunca casam. Não tem `COMMIT`. Foi executado de verdade em Oracle 23ai e em H2 (teste).

## Oracle (perfil opcional)

```bash
export PILOT_DB_URL='jdbc:oracle:thin:@//oracle:1521/FREEPDB1' PILOT_DB_USER=clinica PILOT_DB_PASSWORD="<o mesmo PILOT_ORACLE_PASSWORD>"
docker compose --env-file .env --profile oracle up -d --wait
```

Imagem: `gvenzl/oracle-free:23-slim-faststart` (Oracle Database Free 23ai; imagem comunitária mantida; a oficial é
`container-registry.oracle.com/database/free`, bem maior), fixada por digest em `compose.yaml`. Sem porta publicada: só o
`pilot` a alcança. **Estado de verificação (2026-11-13, Docker Desktop, Windows 11):** verificado. O Oracle subiu, o Flyway criou
o esquema, o fluxo convênio -> paciente -> consulta -> receita funcionou nos dois modos, as verificações dos dois modos deram o resultado
esperado e o `cleanup.sql` foi executado no Oracle com sqlplus. Medidas: tempo até saudável cerca de
76 s com a imagem já baixada (o pull foi de cerca de 1,3 GB); imagem de 6,46 GB em disco; uso de memória de cerca de 1,7 GiB (limite do
compose: 2 GiB). A aplicação sobre Oracle usou cerca de 200 MiB. O contêiner do Oracle roda sem `read_only` (grava arquivos de dados).

## Ligar ao lab principal

`compose.lab-net.yaml` junta o serviço à rede **interna** `hdast_lab_net` do `compose.yaml` da raiz, com o apelido DNS
`clinica-piloto` (alvo `http://clinica-piloto:8080`). Suba o lab da raiz antes; depois:

```bash
docker compose --env-file .env -f compose.yaml -f compose.lab-net.yaml up -d --wait
```

Falta liberar `clinica-piloto:8080` na lista do proxy de saída (`docker/egress-proxy/policy`), tarefa do orquestrador.
O perfil pronto está em [`product-profile/`](product-profile/) (veja `NOTES.md` para o que o schema ainda não expressa).

## Arquivos

| Caminho | Conteúdo |
| --- | --- |
| `Dockerfile`, `compose.yaml`, `compose.lab-net.yaml`, `.env.example` | build, execução, rede do lab |
| `pom.xml`, `src/` | aplicação (Spring Boot 3.5.16, springdoc 2.8.17, jjwt 0.13.0, Flyway, H2, ojdbc11) e testes |
| `openapi.json` | contrato versionado, conferido por teste |
| `cleanup/cleanup.sql` | limpeza Oracle escrita por uma pessoa |
| `documentos/` | arquivos fictícios do endpoint de download |
| `product-profile/` | perfil pronto (`target.yml`, `data-rules.yml`, `flows.yml`) e `NOTES.md` |
| `scripts/check-sync.sh` | confere as cópias do perfil e o OpenAPI ao vivo |

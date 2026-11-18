# Lab local

O lab é um ambiente de contêineres **só para desenvolvimento e testes de ponta
a ponta**: uma API deliberadamente vulnerável (VAmPI) que o `hdast` pode atacar
sem que nada real seja alvo. Definido em [`compose.yaml`](../compose.yaml).

> **Nunca exponha o lab além do localhost.** O VAmPI é vulnerável de propósito
> (injeção de SQL, desvio de autenticação). O compose publica apenas a porta do
> ZAP, em `127.0.0.1`. Não altere para `0.0.0.0`, não use `--network host`, não
> rode em servidor compartilhado ou com IP público.

> **Operação por `hdast stack`:** verificada em 2026-11-13 com `stack up vampi` e `stack up clinica-piloto`, `stack status`, `stop` (com o ZAP parado) e `stack down`.

> **Estado de verificação:** a subida e o isolamento foram executados em Docker Desktop 29.7.2 (Windows 11) em 2026-11-13; os comandos abaixo foram rodados e a saída esperada é a descrita. Detalhes e limites em "O que o isolamento garante e não garante".

## Componentes

| Serviço | Papel | Alcançável de |
|---|---|---|
| `zap` | OWASP ZAP em modo daemon, API com chave | Só da rede interna do compose |
| `zap-gateway` | Ponte TCP mínima que publica o ZAP em `127.0.0.1:8080` | Loopback do host |
| `proxy-gateway` | Ponte TCP mínima (socat, destino fixo `scope-proxy:3128`) que publica o proxy de escopo em `127.0.0.1:3128`; é por onde o `hdast` envia login e token CSRF sem passar pelo ZAP | Loopback do host |
| `scope-proxy` | Proxy de escopo (mitmproxy + `ScopeGuard`); decide cada requisição por host, porta, caminho e método; único com rota externa | Rede interna |
| `vampi` (perfil `lab`) | Alvo vulnerável, porta 5000 | Só do `scope-proxy` |
| `vampi-tls` (perfil `lab`) | Frente TLS do VAmPI (certificado autoassinado gerado ao iniciar), porta 8443, só para provar HTTPS | Só do `scope-proxy` |

O VAmPI **não é publicado no host**: ele fica numa rede `internal` que só o
proxy de escopo enxerga, para que o tráfego do ZAP até ele passe sempre pelo proxy (o que
o teste de ponta a ponta precisa exercitar) e para não deixar uma aplicação
vulnerável escutando na máquina. Para inspeção manual use `docker compose exec`
(veja abaixo).

O OWASP crAPI é o terceiro alvo do lab, integrado ao `hdast stack up`: veja
[`crapi/README.md`](crapi/README.md).

## Subir e parar

```bash
# 1. Chave da API do ZAP (obrigatória; sem valor padrão). Não grave em arquivo versionado.
export HDAST_ZAP_API_KEY="$(openssl rand -hex 24)"      # PowerShell: $env:HDAST_ZAP_API_KEY = -join ((48..57+97..102) | Get-Random -Count 48 | % {[char]$_})

# 2. Preparar as imagens próprias e subir com o alvo do lab
uv run hdast stack pull
docker compose --profile lab up -d --no-build --wait

# 3. Verificar
docker compose --profile lab ps

# 4. Parar e remover os contêineres
docker compose --profile lab down
```

Sem `HDAST_ZAP_API_KEY` o compose falha com mensagem explicando o que fazer. A interpolação obrigatória vale para qualquer subcomando do compose lido pelo `config`; por inferência, `ps` e `down` em um shell novo também pedem a chave (achado A-18 da revisão de QA, não executado): defina qualquer valor antes de derrubar o lab. Itens em aberto do lab (chave visível em `docker logs`) estão em [docs/roadmap.md](../docs/roadmap.md#itens-em-aberto).
A API do ZAP fica em `http://127.0.0.1:8080` (`HDAST_ZAP_HOST_PORT` muda a
porta do host) e exige o parâmetro `apikey`.

## Operar o lab pelo `hdast` (caminho normal)

`hdast stack up <produto>` faz, num comando, o que a seção anterior faz à mão: gera a política do proxy **a partir do perfil**
(nunca mais larga), sorteia a chave do ZAP, sobe tudo recriando os contêineres e grava o estado (chave, endereços, senhas
descartáveis) em `HDAST_STATE_DIR` (`%LOCALAPPDATA%/hdast` no Windows, `~/.local/state/hdast` no Linux), fora do repositório.
Os comandos seguintes (`preflight`, `probe`, `scan`, `report`, `run`, `stop`) leem esse arquivo para o que o ambiente não define. Decisão: [ADR 0019](../docs/decisoes/0019-pilha-gerenciada-politica-por-execucao-e-login-pelo-proxy.md).

O perfil do produto fica numa pasta de produtos (`HDAST_PRODUCTS_DIR` ou `--products-dir`), com o nome da pasta igual ao campo
`product`. O alvo anexado é reconhecido pelo host de `environment.base_url` (`vampi` ou `clinica-piloto`).
Prepare as imagens antes da primeira subida. [Download e build local](../docs/comecar/docker.md)

**VAmPI** (perfil em [`lab/vampi/product-profile`](vampi/product-profile/target.yml), `base_url: http://vampi:5000`). Sequência exata,
verificada com o ZAP 2.17 e o proxy de escopo reais (a pasta do produto leva o nome do produto e o OpenAPI vem de `lab/vampi`):

```bash
mkdir -p /tmp/produtos/vampi
cp lab/vampi/product-profile/*.yml lab/vampi/openapi3.yml /tmp/produtos/vampi/
export HDAST_PRODUCTS_DIR=/tmp/produtos
# Usuários que o GET /createdb semeia (README do VAmPI); não são segredos reais, mas o perfil os lê por secret_ref.
export VAMPI_USER_A_USERNAME=name1 VAMPI_USER_A_PASSWORD=pass1 VAMPI_USER_B_USERNAME=name2 VAMPI_USER_B_PASSWORD=pass2        VAMPI_ADMIN_USERNAME=admin VAMPI_ADMIN_PASSWORD=pass1
uv run hdast --json stack up vampi                           # ~40 s; --secure liga o modo seguro; --token-ttl 20 encurta o token
uv run hdast --json preflight vampi                          # o setup_path /createdb repopula o banco (V1.1); rode antes de cada probe
uv run hdast --json probe vampi --include-delete             # 14 de 14 operações (alcançabilidade 1.0)
uv run hdast --json run vampi                                # preflight + probe + scan + report num processo (~15 min); grava run.json
uv run hdast --json stack status                             # audit_file = trilha do proxy; kill_switch
uv run hdast --json stack down
```

`preflight` antes de cada `probe` não é cerimônia: o `probe` apaga um usuário (`--include-delete`, só o que a listagem desta
execução devolveu) e troca e-mail e senha de `name2`, e o login das contas acontece antes do `GET /createdb` do plano. O
`preflight` chama `/createdb` (é o `probe.setup_path` do perfil desde a V1.1, depois do `health_path: /`, que é leve) e deixa o banco como a semente. Sem `--include-delete` o `DELETE` é
`skipped_destructive` e fica de fora das operações tentadas. Contas por operação: `user_a` envia quase
tudo, `user_b` (dono de `name2`) os `PUT` de e-mail e senha, e `admin_a` o `DELETE`.

**Clínica Piloto** (alvo Spring Boot de `lab/pilot`, perfil em `lab/pilot/product-profile`): veja o passo a passo em
[`lab/pilot/README.md`](pilot/README.md#operar-pelo-hdast-pilha-gerenciada). O `stack up clinica-piloto` sobe o alvo como projeto
`hdast-pilotrun` (distinto do `hdast-pilot` da subida manual, portanto os dois convivem), ligado à rede `hdast_lab_net` pelo
[`compose.lab-net.yaml`](pilot/compose.lab-net.yaml) com o apelido `clinica-piloto`.

**Portas publicadas (todas só em `127.0.0.1`)**: `8080` ZAP (API e proxy; `HDAST_ZAP_HOST_PORT`), `3128` proxy de escopo
(`HDAST_PROXY_HOST_PORT`), `28080` e `29091` API e gestão do piloto. A porta `3128` permite a qualquer processo desta máquina enviar
pedidos ao scope-proxy; ele nega por padrão tudo que a política da execução não autoriza (host, porta, caminho, método, taxa, prazo e
`KILL`), então o alcance é o mesmo do ZAP. Não dá acesso ao ZAP, à rede do lab nem ao Docker.

**Testes de integração do lab** (exigem Docker): `uv run pytest -m lab_fast` (nível rápido, poucos endpoints) e `uv run pytest -m lab_full` (todos os endpoints, vulnerável e seguro, com comparação ao gabarito); detalhes em [../docs/desenvolver/testing.md](../docs/desenvolver/testing.md#dois-níveis-de-integração-contra-o-lab). Os perfis de lab rodam no teto da ferramenta (50 req/s, 8 threads), com autorização do dono, porque os alvos são locais; o teste do limitador reduz a própria cópia para 5 req/s. O modelo em `products/_template` continua conservador.

**Parada de emergência**: `uv run hdast stop` (de outro terminal) lê o que estava rodando, cria o `KILL` da pilha e para as varreduras do ZAP (funciona com o ZAP fora do ar); um `hdast run` ou `scan` em andamento percebe a trava em até 2 s, remove as regras do Replacer e sai (130 no `run`). Depois disso o proxy nega todo pedido novo até `hdast stack up` recriar a pilha.

**Auditoria**: o proxy grava `audit.jsonl` em `<estado>/stacks/<run_id>/audit/` (caminho em `stack status`); a CLI grava a dela em
`runs/<run_id>/audit.jsonl`. Cada pilha tem pastas próprias, então a trilha de uma execução não se mistura com a de outra.

## Alternar o modo do VAmPI

A variável `HDAST_VAMPI_VULNERABLE` controla o modo (variável `vulnerable` do
VAmPI): `1` vulnerável (padrão), `0` seguro. Os testes usam os dois.

```bash
HDAST_VAMPI_VULNERABLE=0 docker compose --profile lab up -d --force-recreate vampi
```

`HDAST_VAMPI_TOKEN_TTL` define a validade do token em segundos (padrão 300).
Depois de subir, chame `GET /createdb` no alvo uma vez para criar o banco de
exemplo (sem isso o VAmPI responde com erro de banco):

```bash
docker compose exec zap curl -s -x http://scope-proxy:3128 http://vampi:5000/createdb
```

## Vulnerabilidades documentadas pelo VAmPI

Conforme o README do projeto (<https://github.com/erev0s/VAmPI>), no modo
vulnerável: injeção de SQL; troca de senha não autorizada; BOLA (autorização no
nível do objeto); atribuição em massa (mass assignment); exposição excessiva de
dados pelo endpoint de debug; enumeração de usuários e senhas; ReDoS; falta de
limite de recursos e de taxa; desvio de autenticação JWT por chave de
assinatura fraca.

## OpenAPI

A especificação OpenAPI 3 do VAmPI está em [`lab/vampi/openapi3.yml`](vampi/openapi3.yml),
copiada de <https://github.com/erev0s/VAmPI/blob/master/openapi_specs/openapi3.yml>.
A redistribuição é permitida pela licença **MIT** (Copyright (c) 2020 erev0s);
o texto está em [`lab/vampi/LICENSE-VAmPI.txt`](vampi/LICENSE-VAmPI.txt). O
`servers` do arquivo aponta para `http://localhost:5000`; dentro do lab o
endereço é `http://vampi:5000` e o tráfego sai do ZAP via `scope-proxy`. Para
atualizar, baixe de novo do endereço acima.

## Inspeção manual

```bash
docker compose exec zap curl -s -x http://scope-proxy:3128 http://vampi:5000/        # via proxy: deve responder
tail -n 5 docker/scope-proxy/audit/audit.jsonl                                         # trilha de auditoria (no host)
docker compose logs scope-proxy                                                         # as mesmas linhas, na saída padrão
```

## Política do proxy de escopo

O proxy só sobe com uma política válida em `HDAST_SCOPE_POLICY_DIR/policy.json` (padrão
[`docker/scope-proxy/policy/policy.json`](../docker/scope-proxy/policy/policy.json)): no lab, só `http://vampi:5000`
com `GET`, `POST` e `PUT` em `/`, `/createdb`, `/me`, `/users/**` e `/books/**`, `deny_paths` em `/users/v1/_debug`, 20
requisições por segundo. A trilha vai para `HDAST_AUDIT_DIR` (padrão `docker/scope-proxy/audit/`). Para trocar a
política, aponte a variável para outra pasta e recrie o proxy (`docker compose --profile lab up -d --no-deps
--force-recreate scope-proxy`). Esquema, trava de emergência e limites: [`docker/scope-proxy/README.md`](../docker/scope-proxy/README.md).

## Provar que a saída está controlada

Execute com o lab no ar (`HDAST_ZAP_API_KEY` definida no shell). Saídas **observadas** em 2026-11-13 entre parênteses.
Em Git Bash no Windows, prefixe com `MSYS_NO_PATHCONV=1` os comandos que levam caminhos como `/var/log/...`. Os comandos
`docker compose exec ... curl` rodam **dentro do contêiner `zap`**, que é o lugar de onde o ZAP envia o tráfego.

```bash
# a. API do ZAP no host: com chave responde; sem chave a conexão é encerrada.
curl -sS "http://127.0.0.1:8080/JSON/core/view/version/?apikey=$HDAST_ZAP_API_KEY"   # {"version":"2.17.0"}
curl -sS "http://127.0.0.1:8080/JSON/core/view/version/"                              # curl: (52) Empty reply from server
docker port hdast-zap-gateway-1                                                       # 8080/tcp -> 127.0.0.1:8080
# O scope-proxy não publica porta nenhuma: docker inspect mostra 3128/tcp apenas exposta.

# b. Direto, sem proxy: sem DNS e sem rota.
docker compose exec zap curl -sS -m 8 http://vampi:5000/           # curl: (6) Could not resolve host: vampi
docker compose exec zap curl -sS -m 8 http://93.184.216.34/        # curl: (7) Failed to connect ... Couldn't connect to server

# c. Pelo proxy, um pedido por linha: código HTTP e motivo (cabeçalho X-Hdast-Reason).
c() { docker compose exec -T zap curl -sS -m 15 -x http://scope-proxy:3128 -o /dev/null -D - -w '%{http_code}\n' "$@" \
        | grep -i -E "^x-hdast|^[0-9]{3}$|curl:"; }
c http://vampi:5000/                                       # 200
c http://vampi:5000/other                                  # 403  X-Hdast-Reason: path_not_allowed
c http://vampi:5000/users/v1/_debug                        # 403  deny_path
c 'http://vampi:5000/users/v1/_debug;x=1'                  # 403  malformed_request (decorado com parâmetro)
c 'http://vampi:5000/users/v1/_debug.'                     # 403  malformed_request (ponto final)
c http://vampi:5000/USERS/v1/_DEBUG                        # 403  deny_path (a negação ignora maiúsculas)
c -X DELETE http://vampi:5000/users/v1/name1               # 403  method_not_allowed (DELETE não está na regra)
c http://example.com/                                      # 403  host_not_allowed
c http://169.254.169.254/latest/meta-data/                 # 403  malformed_request (metadados da nuvem: sempre proibido)
c http://10.0.0.1/                                         # 403  host_not_allowed (IP privado literal)
c http://vampi:8000/                                       # 403  origin_not_allowed (porta fora da regra)
c -H 'Host: evil.example' http://vampi:5000/               # 403  host_header_mismatch
c -H 'Upgrade: websocket' -H 'Connection: Upgrade' http://vampi:5000/   # 403  upgrade_refused
c https://example.com/                                     # curl: (56) CONNECT tunnel failed, response 403  (host_not_allowed)
```

```text
# Trecho real da trilha (docker/scope-proxy/audit/audit.jsonl); o valor da consulta nunca aparece, só o nome:
{"ts":"2026-11-13T06:07:16.366+00:00","run_id":"2026-11-13T00-00-00Z-lab-0001","method":"GET","scheme":"http","host":"vampi","port":5000,"path":"/users/v1/_debug","query_params":[],"decision":"deny","reason":"deny_path","status":403,"bytes":null,"duration_ms":0,"waited_ms":0}
{"ts":"2026-11-13T06:08:01.704+00:00","run_id":"2026-11-13T00-00-00Z-lab-0001","method":"GET","scheme":"http","host":"vampi","port":5000,"path":"/users/v1/name1","query_params":["token","a"],"decision":"allow","reason":"allowed","status":200,"bytes":48,"duration_ms":7,"waited_ms":0}
```

```bash
# d. Taxa. Cem pedidos em paralelo (25 de cada vez) contra o limite de 20 req/s da política.
docker compose exec zap sh -c 'seq 1 100 | xargs -P 25 -I{} curl -s -o /dev/null -x http://scope-proxy:3128 "http://vampi:5000/?n={}"'
# Da trilha: 100 liberados, todos 200, 20,00 req/s no intervalo de 4,95 s, intervalo mínimo entre dois pedidos
# 49 ms, no máximo 20 pedidos em qualquer segundo do relógio, fila máxima de 1233 ms. Nenhum falhou: foram atrasados.

# e. Trava de emergência: criar o arquivo KILL no diretório da política (no host).
touch docker/scope-proxy/policy/KILL
c http://vampi:5000/        # 403  X-Hdast-Reason: kill_switch  (já no primeiro pedido, 0,6 s incluindo o docker exec)
rm docker/scope-proxy/policy/KILL
c http://vampi:5000/        # 403  kill_switch  (a trava é permanente: remover o arquivo NÃO religa)
docker compose restart scope-proxy
c http://vampi:5000/        # 200  (só reiniciar religa)

# f. O próprio ZAP (não o curl) usa o proxy: accessUrl faz um único GET, sem varredura. A chave fica dentro do contêiner.
z() { docker compose exec -T zap sh -c "curl -sS -G --data-urlencode 'url=$1' --data-urlencode \"apikey=\$HDAST_ZAP_API_KEY\" \
        http://127.0.0.1:8080/JSON/core/action/accessUrl/" | cut -c1-160; }
z http://vampi:5000/users/v1     # {"accessUrl":[{"note":"","rtt":"41","responseBody":"{ \"users\": [ ...
z http://example.com/            # ... "responseBody":"hdast scope-proxy: request refused" ... HTTP/1.1 403 Forbidden ... X-Hdast-Reason: host_not_allowed
```

```text
{"ts":"2026-11-13T06:08:53.390+00:00",...,"method":"GET","scheme":"http","host":"vampi","port":5000,"path":"/users/v1",...,"decision":"allow","reason":"allowed","status":200,"bytes":236,...}
{"ts":"2026-11-13T06:08:54.057+00:00",...,"method":"GET","scheme":"http","host":"example.com","port":80,"path":"/",...,"decision":"deny","reason":"host_not_allowed","status":403,...}
```

### g. Varredura ativa limitada: o proxy contém o que o ZAP inventa

É a prova que motiva o proxy. Política: só `GET` e `POST` em `/users/**` e `/books/**`
([`examples/lab-get-post.json`](../docker/scope-proxy/examples/lab-get-post.json)). ZAP com contexto, 2 threads por host,
duração máxima de 1 minuto por varredura e **sempre `contextId`**. Três varreduras, uma requisição aprendida cada:
`GET /books/v1` (aprendida por `accessUrl`), e `DELETE /users/v1/name9` e `PUT /users/v1/name1/email` (aprendidas por
`core/action/sendRequest`, como o spike viu: o ZAP guarda o método na árvore e ataca com ele).

```bash
export HDAST_SCOPE_POLICY_DIR=/caminho/para/pasta-com-policy.json   # cópia de examples/lab-get-post.json como policy.json
export HDAST_AUDIT_DIR=/caminho/para/auditoria-vazia
docker compose --profile lab up -d --no-deps --force-recreate --wait scope-proxy
# no contêiner zap, via API (com a chave): newSession; newContext "lab"; includeInContext http://vampi:5000/(users|books)/.*;
# setOptionThreadPerHost=2; setOptionMaxScanDurationInMins=1; setOptionMaxRuleDurationInMins=1;
# setOptionTargetParamsInjectable=51; accessUrl /books/v1; ascan/action/scan url=... contextId=... recurse=false method=...
```

Resultado, contado da trilha (2 878 decisões, sem contar `CONNECT`):

```text
              liberadas   negadas
GET               172        694
POST               12          0
PUT                 0      1 180
DELETE              0        820
total             184      2 694

motivos das negações: malformed_request 1 699 (travessia, '//', %2f, %5c, ';' etc.)
                      path_not_allowed    387
                      method_not_allowed  608 (todos os PUT e DELETE)
métodos liberados: GET, POST.  Caminhos liberados: só /users e /books (incluindo /books/v1/WEB-INF/web.xml, que
está dentro de /books/**, como a política manda).
PUT/DELETE que chegaram ao alvo: 0.   Pedidos fora da política que chegaram ao alvo: 0.
Os caminhos do spike: /.git/config 3 tentativas, 0 liberadas; /latest/meta-data 12, 0; /server-status 3, 0;
/WEB-INF/web.xml (na raiz) negado.
```

Sem o proxy, o spike registrou 288 de 467 requisições fora da regex do contexto numa varredura equivalente, e 982
`DELETE` ao longo da execução, todos aceitos pelo Squid porque ele só olhava host e porta.

### h. HTTPS: caminho e método também valem

`vampi-tls` é o VAmPI atrás de um mitmproxy em modo reverso, com certificado autoassinado gerado ao iniciar. Política
[`examples/lab-https.json`](../docker/scope-proxy/examples/lab-https.json) (`https://vampi-tls:8443`, `GET`/`POST` em
`/users/**` e `/books/**`, `tls_verify_upstream: false`, aceito porque a regra tem `allow_local: true`). O `-k` do `curl`
existe só porque o `curl` verifica certificados e a CA do proxy é efêmera.

```bash
c() { docker compose exec -T zap curl -k -sS -m 20 -x http://scope-proxy:3128 -o /dev/null -D - -w '%{http_code}\n' "$@" \
        | grep -i -E "^x-hdast|^[0-9]{3}$|curl:"; }
c https://vampi-tls:8443/users/v1                       # 200
c https://vampi-tls:8443/books/v1                       # 200
c https://vampi-tls:8443/users/v1/_debug                # 403  deny_path
c https://vampi-tls:8443/other                          # 403  path_not_allowed
c -X DELETE https://vampi-tls:8443/users/v1/name1       # 403  method_not_allowed
c https://vampi-tls:9999/users/v1                       # curl: (56) CONNECT tunnel failed, response 403  (origin_not_allowed)
c https://example.com/                                  # curl: (56) CONNECT tunnel failed, response 403  (host_not_allowed)
z https://vampi-tls:8443/books/v1                       # ZAP: 200 com o corpo do alvo (veja "O ZAP e o certificado" abaixo)
z https://vampi-tls:8443/other                          # ZAP: 403 do proxy
```

A trilha mostra o `CONNECT` e, **em linhas separadas, as requisições internas** (`"scheme":"https"`, caminho e método
reais), por exemplo:

```text
{"ts":"...","method":"CONNECT","scheme":"https","host":"vampi-tls","port":8443,"path":"","decision":"allow","reason":"allowed",...}
{"ts":"...","method":"GET","scheme":"https","host":"vampi-tls","port":8443,"path":"/users/v1","decision":"allow","reason":"allowed","status":200,...}
{"ts":"...","method":"DELETE","scheme":"https","host":"vampi-tls","port":8443,"path":"/users/v1/name1","decision":"deny","reason":"method_not_allowed","status":403,...}
```

**Verificação do certificado do destino.** Com `tls_verify_upstream: true` (o padrão) a mesma chamada
`c https://vampi-tls:8443/users/v1` devolve **502** e o log do proxy diz `Server TLS handshake failed. Certificate verify
failed: unable to get local issuer certificate`; a trilha registra `"decision":"allow","reason":"upstream_error","status":502`.

**O ZAP e o certificado.** ZAP 2.17.0 **não precisou importar a CA do proxy**: `core/action/accessUrl` em
`https://vampi-tls:8443/books/v1` devolveu o corpo do alvo sem nenhuma configuração de certificado. Conclusão: o ZAP
aceita qualquer certificado do outro lado do `CONNECT` (testado só nesta forma, sem procurar uma opção que o ligue). Risco
residual e mitigação: ver "O que o isolamento garante e não garante".

### i. Proteção do endereço resolvido

Nomes públicos que resolvem para endereços internos, simulados só neste teste com `extra_hosts` em um arquivo de
override temporário (não versionado): `trap-private.example.com` -> `10.255.0.7`, `trap-meta.example.com` ->
`169.254.169.254`, `trap-loop.example.com` -> `127.0.0.1`, todos permitidos pelo escopo (sem `allow_local`, porque são
nomes com ponto). Resultado: os três devolveram **502** e a trilha registra
`"decision":"deny","reason":"address_forbidden","status":502` para cada um, sem nenhuma conexão ao endereço interno.
Com `allow_local: true` (o `vampi`, em `172.x`) o mesmo mecanismo permite o pedido (`200`, provas c a g).

### j. Sem política válida o proxy não sobe

```bash
docker run --rm --read-only --cap-drop ALL -v "$PWD/vazio:/policy:ro" -v "$PWD/auditoria:/audit" hdast/scope-proxy:local
# exit=3  scope-proxy: RECUSANDO INICIAR. Não foi possível ler a política do proxy em /policy/policy.json (No such file or directory). ...
# JSON malformado        -> exit=3  A política do proxy não é JSON válido: Expecting value: line 2 column 1 (char 32). ...
# campo desconhecido     -> exit=3  Política do proxy inválida: extra_allow_all: Extra inputs are not permitted. ...
# host com curinga       -> exit=3  ... scope.allow.0.host: Value error, host com curinga não é permitido; ...
# TLS sem verificação em host não local
#                        -> exit=3  ... tls_verify_upstream: false só é aceito quando toda regra de scope.allow tem allow_local: true ...
# schema_version: 2      -> exit=3  ... schema_version: Value error, schema_version deve ser 1. ...
```

```bash
# k. Modos do VAmPI (ver "Alternar o modo do VAmPI"): a raiz informa o modo ativo.
docker compose exec zap curl -s -x http://scope-proxy:3128 http://vampi:5000/   # ... "vulnerable":1
HDAST_VAMPI_VULNERABLE=0 docker compose --profile lab up -d --force-recreate --wait vampi
docker compose exec zap curl -s -x http://scope-proxy:3128 http://vampi:5000/   # ... "vulnerable":0

# l. Sem a chave, o compose recusa:
env -u HDAST_ZAP_API_KEY docker compose config
# error while interpolating services.zap.environment.HDAST_ZAP_API_KEY: required variable HDAST_ZAP_API_KEY is missing a value: Defina HDAST_ZAP_API_KEY ...
```

## O que o isolamento garante e não garante

Observado em Docker Desktop 29.7.2, Windows 11, 2026-11-13.

Garante (verificado):

- O contêiner `zap` está só em rede `internal: true`: acesso direto à internet
  e a IP público falha (sem DNS, sem rota). O `vampi` e o `vampi-tls` idem, e o
  `zap` não os alcança sem passar pelo proxy.
- O ZAP realmente usa o proxy, para http e https: `accessUrl` e a varredura
  ativa aparecem na trilha do `scope-proxy`.
- O proxy decide **cada requisição** com o `ScopeGuard` (host, esquema, porta,
  caminho, método, `deny_paths`, URL normalizada), inclusive as que o varredor
  inventa e as de dentro de um túnel HTTPS (seções g e h): numa varredura ativa
  limitada, 0 `PUT`/`DELETE` e 0 caminhos fora da política chegaram ao alvo.
- O proxy nega por padrão: sem política válida ele não sobe; recusa IP
  literal, metadados da nuvem, endereços internos que um nome permitido
  resolva (sem `allow_local`), `Upgrade`, `Host` incoerente e `CONNECT` fora das
  regras `https`.
- A taxa (`requests_per_second`) e a duração da execução valem para tudo que
  sai; a trava de emergência (`KILL`) nega o pedido seguinte e é permanente até
  reiniciar.
- A porta do ZAP no host escuta somente em `127.0.0.1`; sem a chave a API não
  responde (a conexão é encerrada). O `scope-proxy` não publica porta.
- Todos os contêineres rodam sem capabilities, com rootfs somente leitura,
  `no-new-privileges`, limites de memória e de processos; `scope-proxy`, `zap`,
  `zap-gateway`, `vampi` e `vampi-tls` não rodam como root.

Não garante:

- A ponte `zap-gateway` está também numa rede comum (necessário para publicar
  a porta no Docker Desktop). Ela só encaminha TCP para `zap:8080`, mas tem
  rota externa; seu risco é o de um encaminhador comprometido, e ela só é
  alcançável por quem tem acesso à API do ZAP (porta com chave, em loopback).
- Quem alcança a porta do ZAP sem a chave não lê a API, mas o ZAP também é um
  proxy: um pedido HTTP com URL absoluta é encaminhado ao `scope-proxy`. O
  limite é sempre a política do proxy, nunca a chave.
- **O ZAP não valida o certificado do que está do outro lado do `CONNECT`**
  (aceitou o do proxy sem importar a CA). A autenticidade do destino em HTTPS é
  verificada pelo proxy (ligado por padrão) e a rede `zap_net` é isolada. O proxy
  vê corpos e cabeçalhos em claro, por desenho.
- HTTP/2, WebSocket, TCP cru e UDP são **recusados**, não filtrados: um alvo
  que exija HTTP/2 não funciona por este proxy.
- Um nome permitido cujo dono do domínio o aponte para outro IP público
  continua permitido (o escopo é por nome). Endereços internos só passam com
  `allow_local` na regra.
- O proxy só vale para quem o usa; o isolamento real é a rede `internal`.
- O Docker Desktop executa tudo numa VM; a política vale dentro dela e não
  substitui firewall do host. Do `zap`, `host.docker.internal` não respondeu;
  nenhum outro endereço da rede do host foi testado.
- A chave da API fica visível a quem acessa `docker inspect` ou `docker logs`
  do `zap` na máquina (o ZAP registra `api.key` ao iniciar).
- Verificado só contra o VAmPI (HTTP e um HTTPS autoassinado de laboratório);
  nenhum ambiente real, `ZAP` com spider ou várias contas foi exercitado.

Limites de recursos (medidos com `docker stats` no lab ocioso após as provas):
`zap` 1,14 GiB de 2,5 GiB (JVM com `-Xmx1536m`), `scope-proxy` 62 MiB de 512 MiB,
`vampi` 136 MiB de 256 MiB, `vampi-tls` 67 MiB de 256 MiB, `zap-gateway` 4 MiB de 64 MiB.

## Inventário de imagens (V1.12)

Os digests abaixo são declarados nos arquivos; imagens locais de build têm ID variável. Os tamanhos são da captura `images-before.jsonl` do coordenador em 2026-11-17, não uma consulta atual. O manifesto verificável [protected-images.json](scripts/protected-images.json) protege as imagens desta tabela, exceto `scratch`, que é estágio vazio e não uma imagem local removível.

| Imagem e digest declarado | Uso | Tamanho instalado |
| --- | --- | --- |
| `zaproxy/zap-stable:2.17.0@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af` | Base / VAmPI: zap | 3.75GB (captura inicial) |
| `hdast/zap:2.17.0-alpha54-beta64` | Base / VAmPI: zap (derivada da `zap-stable` acima, ADR 0103) | 3.77GB (medido em 2026-11-17; só 12MB próprios, o resto são camadas da `zap-stable`) |
| `hdast/zap:local` | ZAP construído pelo modo local | A medir |
| `ghcr.io/marcosquintino0/hdast-zap:1.12.2` | ZAP preparado para publicação no GHCR | A medir |
| `ghcr.io/marcosquintino0/hdast-scope-proxy:1.12.2` | Proxy de escopo preparado para publicação no GHCR | A medir |
| `alpine/socat:1.8.1.3@sha256:e8a6e8868a8e6e01d9c2c321a8f8d4474d2d741d962462e5c5a124a8e66a0055` | Base / VAmPI: zap-gateway, Base / VAmPI: proxy-gateway, OAST: oast-gateway | 15MB (captura inicial) |
| `hdast/scope-proxy:local` | Base / VAmPI: scope-proxy, Base / VAmPI: vampi-tls | 339MB (captura inicial) |
| `erev0s/vampi:latest@sha256:0a5a224b6e14ae7da6a6ea265178ff71286ff903aec74adee98f660bb0e4ca12` | Base / VAmPI: vampi | 186MB (captura inicial) |
| `hdast-clinica-piloto:1.0.0` | Clínica Piloto: pilot | 365MB (captura inicial) |
| `gvenzl/oracle-free:23-slim-faststart@sha256:f5ff19033860d662c821cb04eb10483fa94f14f78eae252d054291ea07028093` | Clínica Piloto: oracle | 6.46GB (captura inicial) |
| `crapi/crapi-identity:1.1.6-rc8@sha256:5152eaa8b25d8585068ec478c9a2ee886ce1658d8289fd047f83325737490f78` | crAPI: crapi-identity | 809MB (captura inicial) |
| `crapi/crapi-community:1.1.6-rc8@sha256:ff62181b9089df60379c1cecdcfceb0f54ea6d6c4d7c407bb2f5fd55208f2be0` | crAPI: crapi-community | 47.9MB (captura inicial) |
| `crapi/crapi-workshop:1.1.6-rc8@sha256:b73a2e4aed1a62ba9c626214eca6b66289f2f5cced7169dbd791837edf263de6` | crAPI: crapi-workshop | 307MB (captura inicial) |
| `crapi/crapi-web:1.1.6-rc8@sha256:6cbafa5085cc38199c5f16f71ad11579168e08ca25c22e9b89f55e423caa8746` | crAPI: crapi-web | 182MB (captura inicial) |
| `postgres:14@sha256:980b7cb415aa0f812f65bdec8f6f599be408d8ed9c83ffcaa12650eac397b264` | crAPI: postgresdb | 654MB (captura inicial) |
| `mongo:4.4@sha256:4be76f674fc4b27859816811b8baa3c51830eb1dbf4ca81a51e26b79edd662ef` | crAPI: mongodb | 594MB (captura inicial) |
| `crapi/mailhog:1.1.6-rc8@sha256:c3a74b1f63673996aec82f175ad4dd49cc3152637f68dc3dfc9f765e06c0f5e9` | crAPI: mailhog | 31.9MB (captura inicial) |
| `crapi/gateway-service:1.1.6-rc8@sha256:111a996957c1e9f78fe401b4d9a16bb99e6d6a3aa836792382a52c9ecbd39c8c` | crAPI: api.mypremiumdealership.com | 131MB (captura inicial) |
| `python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72` | Build do proxy | 183MB (captura inicial) |
| `maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237` | Build da Clínica | 801MB (captura inicial) |
| `eclipse-temurin:21-jre-alpine@sha256:ac05c3c42b7c2f1a52c9bd52f01041fa1958231b15ebeae7420429cbc5baf474` | Base da Clínica | 287MB (captura inicial) |
| `scratch` | Estágio de exportação da Clínica (imagem vazia) | Não aplicável |

A imagem antiga `crapi/crapi-chatbot:1.1.6-rc8@sha256:82a2b54f13a378952ea0d40925c3229c7cc9876e3699dd29340c7392b4bd909f` (1,5 GB na captura inicial) já existia e não foi removida. Ela deixou de fazer parte da pilha do crAPI; permanece protegida como imagem anterior à trilha, inclusive no manifesto.

Medição posterior: `docker image inspect --format "{{.Id}} {{.Size}}" <referência>` para cada referência existente; registre ausência e não baixe imagens para medir. Não use `prune` ou `dangling` como prova de propriedade.

## Retorno OAST isolado (proposto)

Os overlays `lab/oast/compose.yaml` e `lab/crapi/compose.oast.yaml` preparam a ponte interna de Callback descrita no [ADR 0095](../docs/decisoes/0095-retorno-oast-isolado.md). Não ligam varredura. Em 2026-11-17, a prova dirigida confirmou o complemento na imagem fixada e recebeu um evento real do workshop. A operação exige coordenação sob a trava do laboratório.

### Simular a seleção de imagens

O registro explícito, criado quando a trilha cria uma imagem temporária, tem o formato `{"images":[{"image_id":"sha256:<64 hex>","reference":"hdast/v1-12-oast-temp:<tag>"}]}`. Não invente registros para imagens existentes. Sob a trava do laboratório, execute:

```powershell
uv run python lab/scripts/plan_image_cleanup.py registro.json C:\harness-dast-artefatos\v1-12-lab\images-before.jsonl
```

O roteiro consulta apenas IDs, tags e digests do Docker, sem ler variáveis de ambiente nem remover imagens. Ele recusa IDs incompletos, duplicatas, imagens da captura inicial, referências remapeadas, imagens em uso por qualquer contêiner, tags extras e imagens protegidas pelo manifesto. Também exige conseguir resolver todos os IDs da captura inicial para impedir divergência entre ID local e digest; se algum não estiver disponível, recusa o plano. Com registro vazio, gera plano vazio sem consultar o Docker. Gera comandos estritos com o **ID completo validado**, sem `--force`, para revisão humana; mudança posterior da tag não direciona o comando para outra imagem. O registro declara a origem e deve ser comprovado pelos logs da criação: nome ou tag não provam propriedade. Como o estado pode mudar após a consulta, mantenha a trava, execute novamente a validação imediatamente antes de executar cada comando e confira o registro; não use `prune` ou `dangling`.

A captura inicial é vinculada pelo SHA-256 `e7aa7746b87f428e0f928a855c4947cf6389e25954f22398982feebf6130747e`: arquivo ausente, alterado ou malformado recusa o plano inteiro.

### Prova dirigida de Callback

Após obter a trava exclusiva do laboratório e confirmar que o projeto `hdast-codex` está livre, o coordenador executa na raiz:

```powershell
$env:HDAST_IT_METRICS_DIR = 'C:\harness-dast-artefatos\v1-12-lab\oast-proof'
uv run pytest -v -m integration tests/integration/test_lab_oast.py::test_callback_e_isolamento_a_partir_do_workshop_crapi
```

O teste sobe a pilha crAPI via `LabCli`, liga a ponte sem recriar o ZAP e aplica o overlay ao workshop. Configura o Callback pela API de controle e executa Python no workshop para enviar um único pedido ao retorno. Confere a mensagem OAST no histórico do ZAP, o contador, as redes internas e a falha por falta de rota para `192.0.2.1`. O arquivo `oast-crapi-callback-<run_id>.json` contém somente ID da pilha, marcador e resultados sanitizados. Esta é uma prova de infraestrutura: não envia HTTP direto à API do alvo, não demonstra SSRF e não contorna `STACK_STALE`. O teste sintético anterior permanece como controle separado. A execução real de 2026-11-17 passou em 238,91 s na pilha `2026-11-17T08-00-17Z-crapi-4538`: contador de 0 para 1 e limpeza sem erros. Evidências externas em `C:\harness-dast-artefatos\v1-12-lab\retomada-20261117\metrics-oast-fixed\`.

### Inventário de imagens em ensaio

Na raiz do repositório, o coordenador pode gerar um relatório externo sem modificar imagens:

```powershell
uv run python lab/scripts/inventory_images.py --output C:\harness-dast-artefatos\v1-12-lab\retomada-20261117\images-inventory.json
```

O comando lê os arquivos versionados cujo nome contém `compose` e termina em `.yaml` ou `.yml`. Para as imagens próprias lê o valor padrão declarado no Compose, sem consultar o ambiente ou `.env`. Consulta do Docker somente os campos ID, tags, digests, tamanho e data das imagens e o ID da imagem de cada contêiner, inclusive parado. Não remove, baixa, cria ou altera imagens. O relatório distingue imagens próprias usadas por Compose ou contêiner, imagens próprias fora de ambos e imagens sem proveniência atribuível. Tamanhos aparecem em bytes e em unidades legíveis. Imagens alheias com identificação não são listadas.

O nome gerado para um serviço com `build` sem `image` usa o nome de projeto do arquivo ou o diretório e a tag `latest`. Nomes de projeto fornecidos em execução, arquivos não versionados, builds externos e referências dinâmicas não podem ser comprovados por este inventário. Interpolações sem padrão reconhecido, `include`/`extends`, arquivos inválidos e falhas de consulta causam recusa. O relatório é uma fotografia sujeita a mudanças e não é autorização nem plano de remoção.

### Ciclos crAPI descartáveis

Sob a trava exclusiva, com os projetos `hdast-codex` e `hdast-crapi-codex` livres:

```powershell
$env:HDAST_IT_METRICS_DIR = 'C:\harness-dast-artefatos\v1-12-lab\nova-prova'
uv run pytest -m integration tests/integration/test_v112_cli_cycle.py tests/integration/test_crapi_focus_dryrun.py
```

Os testes usam somente produtos e estado temporários, aprovação do suporte/runner e
sufixo `-codex`. Recusam projetos ocupados, registram identidades após a subida e
conferem propriedade antes da descida e ausência depois. Uma subida parcial sem
inventário confiável recusa a derrubada e exige intervenção humana. Essa conferência
não é atômica: a trava externa continua obrigatória.

Em 2026-11-17, os dois testes finais passaram em 566,37 s. O controle levou 254,098 s;
o foco, 310,344 s desde antes do preparo até depois da descida. O foco tentou nove
operações, varreu duas e registrou exclusões em authz/negative: conclusão operacional
no prazo não significa cobertura completa. A medição do `evals.runner` usa uma
representação de compatibilidade dos comandos, sem agente, modelo ou tokens; o tempo
fim a fim usa medição monotônica separada. A ocorrência anterior de `STACK_STALE`
continua sem causa estabelecida. Evidências em
`C:\harness-dast-artefatos\v1-12-lab\retomada-20261117\final-proofs.log` e `metrics-final-proofs/`.

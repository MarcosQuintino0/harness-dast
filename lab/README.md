# Lab local

O lab é um ambiente de contêineres **só para desenvolvimento e testes de ponta
a ponta**: uma API deliberadamente vulnerável (VAmPI) que o `hdast` pode atacar
sem que nada real seja alvo. Definido em [`compose.yaml`](../compose.yaml).

> **Nunca exponha o lab além do localhost.** O VAmPI é vulnerável de propósito
> (injeção de SQL, desvio de autenticação). O compose publica apenas a porta do
> ZAP, em `127.0.0.1`. Não altere para `0.0.0.0`, não use `--network host`, não
> rode em servidor compartilhado ou com IP público.

> **Estado de verificação:** a subida e o isolamento foram executados em Docker Desktop 29.7.2 (Windows 11) em 2026-11-13; os comandos abaixo foram rodados e a saída esperada é a descrita. Detalhes e limites em "O que o isolamento garante e não garante".

## Componentes

| Serviço | Papel | Alcançável de |
|---|---|---|
| `zap` | OWASP ZAP em modo daemon, API com chave | Só da rede interna do compose |
| `zap-gateway` | Ponte TCP mínima que publica o ZAP em `127.0.0.1:8080` | Loopback do host |
| `egress-proxy` | Squid com lista de permissão; único com rota externa | Rede interna |
| `vampi` (perfil `lab`) | Alvo vulnerável, porta 5000 | Só do `egress-proxy` |

O VAmPI **não é publicado no host**: ele fica numa rede `internal` que só o
proxy enxerga, para que o tráfego do ZAP até ele passe sempre pelo proxy (o que
o teste de ponta a ponta precisa exercitar) e para não deixar uma aplicação
vulnerável escutando na máquina. Para inspeção manual use `docker compose exec`
(veja abaixo).

Fora deste marco: o crAPI (OWASP) pode ser acrescentado depois como segundo
alvo do lab.

## Subir e parar

```bash
# 1. Chave da API do ZAP (obrigatória; sem valor padrão). Não grave em arquivo versionado.
export HDAST_ZAP_API_KEY="$(openssl rand -hex 24)"      # PowerShell: $env:HDAST_ZAP_API_KEY = -join ((48..57+97..102) | Get-Random -Count 48 | % {[char]$_})

# 2. Subir com o alvo do lab
docker compose --profile lab up -d --wait

# 3. Verificar
docker compose --profile lab ps

# 4. Parar e remover os contêineres
docker compose --profile lab down
```

Sem `HDAST_ZAP_API_KEY` o compose falha com mensagem explicando o que fazer. A interpolação obrigatória vale para qualquer subcomando do compose lido pelo `config`; por inferência, `ps` e `down` em um shell novo também pedem a chave (achado A-18 da revisão de QA, não executado): defina qualquer valor antes de derrubar o lab. Itens em aberto do lab (limites de recursos, chave visível em `docker logs`, tráfego real de varredura pelo proxy) estão em [docs/roadmap.md](../docs/roadmap.md#itens-em-aberto).
A API do ZAP fica em `http://127.0.0.1:8080` (`HDAST_ZAP_HOST_PORT` muda a
porta do host) e exige o parâmetro `apikey`.

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
docker compose exec zap curl -s -x http://egress-proxy:3128 http://vampi:5000/createdb
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
endereço é `http://vampi:5000` e o tráfego sai do ZAP via `egress-proxy`. Para
atualizar, baixe de novo do endereço acima.

## Inspeção manual

```bash
docker compose exec zap curl -s -x http://egress-proxy:3128 http://vampi:5000/        # via proxy: deve responder
docker compose exec egress-proxy cat /var/log/squid/access.log                         # permitidos e negados
```

## Provar que a saída está bloqueada

Execute com o lab no ar (`HDAST_ZAP_API_KEY` definida no shell). Saídas
observadas entre parênteses. Em Git Bash no Windows, prefixe com
`MSYS_NO_PATHCONV=1` os comandos que levam caminhos como `/var/log/...`.

```bash
# a. API do ZAP no host: com chave responde; sem chave a conexão é encerrada.
curl -sS "http://127.0.0.1:8080/JSON/core/view/version/?apikey=$HDAST_ZAP_API_KEY"   # {"version":"2.17.0"}
curl -sS "http://127.0.0.1:8080/JSON/core/view/version/"                              # curl: (52) Empty reply from server
curl -sS -m 4 "http://<IP-da-LAN-do-host>:8080/JSON/core/view/version/"               # falha: a porta só escuta em 127.0.0.1
docker port hdast-zap-gateway-1                                                       # 8080/tcp -> 127.0.0.1:8080

# b. Do contêiner zap, direto, sem proxy: sem DNS e sem rota.
docker compose exec zap curl -sS -m 8 http://example.com/        # curl: (6) Could not resolve host
docker compose exec zap curl -sS -m 8 http://93.184.216.34/      # curl: (7) Failed to connect ... Couldn't connect to server

# c. Pelo proxy: o alvo do lab passa; o resto é negado (403 do Squid).
P="-x http://egress-proxy:3128 -o /dev/null -w %{http_code}\n -sS -m 15"
docker compose exec zap curl $P http://vampi:5000/               # 200
docker compose exec zap curl $P http://example.com/              # 403
docker compose exec zap curl $P http://169.254.169.254/          # 403 (metadados de nuvem / IP literal)
docker compose exec zap curl $P http://10.0.0.1/                 # 403 (IP privado literal)
docker compose exec zap curl $P http://vampi:8000/               # 403 (nome permitido, porta fora da lista)
docker compose exec zap curl $P https://example.com/             # curl: (56) CONNECT tunnel failed, response 403

# d. O próprio ZAP (não o curl) usa o proxy: a ação accessUrl da API faz uma
#    única requisição GET, sem varredura nem ataque.
curl -sS -G --data-urlencode "url=http://vampi:5000/createdb" --data-urlencode "apikey=$HDAST_ZAP_API_KEY" http://127.0.0.1:8080/JSON/core/action/accessUrl/   # HTTP/1.1 200 OK
curl -sS -G --data-urlencode "url=http://example.com/"        --data-urlencode "apikey=$HDAST_ZAP_API_KEY" http://127.0.0.1:8080/JSON/core/action/accessUrl/   # HTTP/1.1 403 Forbidden (página de erro do Squid)

# e. O registro do proxy mostra o permitido e o negado, e quem pediu
#    (curl/7.x ou o user-agent do ZAP).
docker compose exec egress-proxy cat /var/log/squid/access.log
```

Trecho real do registro (o ZAP aparece com user-agent `Mozilla/5.0 ...`):

```text
2026-11-13T04:02:28 172.20.0.3 TCP_MISS/200 GET http://vampi:5000/ 487 "curl/7.88.1"
2026-11-13T04:02:28 172.20.0.3 TCP_DENIED/403 GET http://example.com/ 3344 "curl/7.88.1"
2026-11-13T04:02:29 172.20.0.3 TCP_DENIED/403 GET http://169.254.169.254/ 3352 "curl/7.88.1"
2026-11-13T04:02:30 172.20.0.3 TCP_DENIED/403 CONNECT example.com:443 3348 "curl/7.88.1"
2026-11-13T04:02:30 172.20.0.3 TCP_MISS/200 GET http://vampi:5000/createdb 251 "Mozilla/5.0 ..."
2026-11-13T04:02:31 172.20.0.3 TCP_DENIED/403 GET http://example.com/ 3344 "Mozilla/5.0 ..."
```

```bash
# f. Modos do VAmPI (ver "Alternar o modo do VAmPI"): a raiz informa o modo ativo.
docker compose exec zap curl -s -x http://egress-proxy:3128 http://vampi:5000/   # ... "vulnerable":1
HDAST_VAMPI_VULNERABLE=0 docker compose --profile lab up -d --force-recreate --wait vampi
docker compose exec zap curl -s -x http://egress-proxy:3128 http://vampi:5000/   # ... "vulnerable":0

# g. Sem a chave, o compose recusa:
env -u HDAST_ZAP_API_KEY docker compose config
# error while interpolating services.zap.environment.HDAST_ZAP_API_KEY: required variable HDAST_ZAP_API_KEY is missing a value: Defina HDAST_ZAP_API_KEY ...
```

## O que o isolamento garante e não garante

Observado em Docker Desktop 29.7.2, Windows 11, 2026-11-13.

Garante (verificado):

- O contêiner `zap` está só em rede `internal: true`: acesso direto à internet
  e a IP público falha (sem DNS, sem rota). O `vampi` idem, e o `zap` não o
  alcança sem passar pelo proxy.
- O ZAP realmente usa o proxy: a ação `accessUrl` da API aparece no registro
  do Squid, permitida para `vampi:5000` e negada (403) para `example.com`.
- O proxy nega por padrão: host fora da lista, IP literal, faixas privadas e
  metadados de nuvem, porta fora da lista (inclusive `CONNECT`).
- A porta do ZAP no host escuta somente em `127.0.0.1`; sem a chave a API não
  responde (a conexão é encerrada).
- Todos os contêineres rodam sem capabilities, com rootfs somente leitura e
  `no-new-privileges`; `egress-proxy`, `zap`, `zap-gateway` e `vampi` não
  rodam como root.

Não garante:

- A ponte `zap-gateway` está também numa rede comum (necessário para publicar
  a porta no Docker Desktop). Ela só encaminha TCP para `zap:8080`, mas tem
  rota externa; seu risco é o de um encaminhador comprometido, e ela só é
  alcançável por quem tem acesso à API do ZAP (porta com chave, em loopback).
- Quem alcança a porta do ZAP sem a chave não lê a API, mas o ZAP também é um
  proxy: um pedido HTTP com URL absoluta é encaminhado ao `egress-proxy` (visto
  no registro como `GET http://x/...`, negado). O limite é sempre a política
  do Squid, nunca a chave.
- O proxy filtra por host e porta, não por caminho ou método (isso é das
  camadas 1 e 2). Veja [`docker/egress-proxy/README.md`](../docker/egress-proxy/README.md).
- O Docker Desktop executa tudo numa VM; a política vale dentro dela e não
  substitui firewall do host. Do `zap`, `host.docker.internal` não respondeu;
  nenhum outro endereço da rede do host foi testado.
- A chave da API fica visível a quem acessa `docker inspect` ou `docker logs`
  do `zap` na máquina (o ZAP registra `api.key` ao iniciar).
- Não provado: o tráfego de varredura real (spider, scan ativo) do ZAP pelo
  proxy. Só foi exercitada a ação `accessUrl`; as demais usam a mesma
  configuração de proxy, mas não foram executadas aqui.

# Proxy de escopo (`scope-proxy`)

Implementa a **camada 3** de AD-11 (ver [ADR 0008](../../docs/adr/0008-escopo-em-tres-camadas.md)) e substitui o Squid
([ADR 0017](../../docs/adr/0017-proxy-de-escopo-com-scopeguard.md)). É um proxy de saída com interceptação de TLS
(mitmproxy 12.3.1) que chama o **mesmo `ScopeGuard`** da CLI para **cada** requisição que sai da pilha, inclusive as que
o ZAP inventa durante uma varredura (caminhos novos, troca de método). Uma única implementação de escopo governa tudo.

## Como funciona

```text
ZAP --(http/CONNECT)--> scope-proxy --(só se o ScopeGuard permitir)--> alvo
                            |
                            +--> trilha de auditoria (JSON, uma linha por decisão)
```

Para cada pedido, nesta ordem, e a primeira recusa encerra:

| # | Checagem | Código de motivo |
|---|---|---|
| 1 | Trava de emergência acionada, prazo vencido ou auditoria falhou | `kill_switch`, `run_expired`, `audit_failure` |
| 2 | `Upgrade` (WebSocket, h2c) no pedido | `upgrade_refused` |
| 3 | `ScopeGuard.ensure_allowed(método, URL)` (ou o guarda do modo amplo, se a política pedir): host, esquema, porta, caminho, método, `deny_paths`, URL ambígua | `malformed_request` (com `detail` granular), `deny_path`, `host_not_allowed`, `origin_not_allowed`, `path_not_allowed`, `method_not_allowed` |
| 4 | Cabeçalho `Host` diferente do destino da URL | `host_header_mismatch` |
| 5 | Taxa: se acima de `requests_per_second`, o pedido **espera na fila** (não falha); fila cheia = 429 | `rate_queue_full` |
| 6 | Ao conectar: o nome é resolvido, os endereços são conferidos e o IP conferido é **fixado** na conexão | `address_forbidden`, `dns_failure` |

- **HTTP**: a URL absoluta, o caminho e o método são conferidos antes de qualquer conexão (a conexão de saída é
  "preguiçosa": só abre depois da decisão).
- **HTTPS**: o `CONNECT host:porta` é decidido por host e porta contra as regras `https`; o proxy então intercepta o TLS
  e **cada requisição interna** é decidida com URL completa, caminho e método. A auditoria mostra as requisições
  internas, não só o `CONNECT`.
- **Redirecionamentos**: o proxy apenas repassa o `3xx`. O pedido seguinte é uma requisição nova e é decidido como
  qualquer outra (é a mesma regra do `ensure_redirect_allowed` do `ScopeGuard`).
- **Recusa**: HTTP 403 com corpo fixo (`hdast scope-proxy: request refused`) e o cabeçalho `X-Hdast-Reason: <código>`.
  429 com `Retry-After: 1` quando a fila da taxa enche.
- **Não inspecionável = recusado** (falha fechada): `rawtcp=false` (nada de TCP cru), `http2=false` (só HTTP/1.1),
  `Upgrade` recusado (WebSocket e h2c), `ignore_hosts`/`allow_hosts`/`tcp_hosts` vazios. O addon se recusa a iniciar se
  alguma dessas opções for mudada.

## Arquivos

| Arquivo | Papel |
|---|---|
| `Dockerfile` | Imagem. Base `python:3.13-slim-bookworm` fixada por digest; mitmproxy fixado; instala o pacote `harness_dast` do repositório. |
| `requirements.in` / `requirements.txt` | Dependências da imagem, com hashes (`pip --require-hashes`). Não são dependências da CLI. |
| `addon.py` | Cola mitmproxy -> `harness_dast.adapters.scope_proxy`. Sem regra de escopo. |
| `entrypoint.sh` | Valida a política e a trilha **antes** de aceitar tráfego; sobe o `mitmdump`. |
| `policy/policy.json` | Política do laboratório (só o VAmPI). A CLI gerará este arquivo por execução. |
| `examples/` | Políticas de exemplo usadas nas provas (`lab-get-post.json`, `lab-https.json`). |
| `audit/` | Trilha de auditoria (`audit.jsonl`), no host; ignorada pelo git. |

A lógica (política, decisão, taxa, trava, auditoria) está em `src/harness_dast/adapters/scope_proxy/` e é testada no
host sem mitmproxy: `uv run pytest tests/unit/adapters/scope_proxy`.

## Política (`policy.json`)

Montada **somente leitura** em `/policy`. Validada ao iniciar; **sem política válida o contêiner não sobe** (saída 3,
mensagem `RECUSANDO INICIAR` no log). Não existe política padrão e nunca há "permitir tudo".

```json
{
  "schema_version": 1,
  "run_id": "2026-11-13T00-00-00Z-lab-0001",
  "scope": {
    "allow": [
      {
        "host": "vampi",
        "scheme": "http",
        "port": 5000,
        "allow_local": true,
        "methods": ["GET", "POST", "PUT"],
        "paths": ["/", "/createdb", "/me", "/users/**", "/books/**"]
      }
    ],
    "deny_paths": ["/users/v1/_debug"]
  },
  "limits": { "requests_per_second": 20, "max_duration_minutes": 480, "zap_threads_per_host": 2 },
  "not_after": "2099-12-31T23:59:59Z",
  "tls_verify_upstream": true,
  "max_queued_requests": 100
}
```

| Campo | Regra |
|---|---|
| `schema_version` | Inteiro `1`. Outro valor é recusado. |
| `run_id` | Formato de `RunId` (`AAAA-MM-DDTHH-MM-SSZ-<produto>-<hex>`). Vai em toda linha de auditoria. |
| `scope` | **Mesmo formato do `scope` do perfil**: `allow` (host exato sem curinga, `scheme`, `port`, `paths`, `methods`, `allow_local`) e `deny_paths`. Validado pelos modelos do domínio. |
| `limits` | Os `limits` do perfil. O proxy usa `requests_per_second` (teto 50) e `max_duration_minutes` (teto 480). |
| `not_after` | Texto ISO 8601 **com fuso**. Depois dele tudo é negado. É a validade da pilha, não o prazo de uma varredura. O prazo efetivo é o menor entre `not_after` e (início do proxy + `stack_minutes`). |
| `stack_minutes` | Opcional, 1 a 540. Validade da pilha em minutos desde a partida do proxy. Ausente, vale `max_duration_minutes` (política escrita à mão mantém a cerca antiga). A CLI grava a duração máxima do perfil mais 60 minutos de folga; o prazo de cada execução (`limits.max_duration_minutes`) é imposto pela CLI, contado do início dela. |
| `tls_verify_upstream` | Padrão `true`: o certificado do destino é verificado. `false` só é aceito se **toda** regra tiver `allow_local: true`. |
| `max_queued_requests` | 1 a 1000 (padrão 100): quantos pedidos podem esperar pela taxa. |

Campo desconhecido, chave repetida no JSON, `NaN`, tipo trocado (`"10"` no lugar de `10`), host com curinga ou fora de
formato, arquivo maior que 1 MiB: tudo é recusado. Não há recarga a quente: mudar a política exige reiniciar o
contêiner (e isso zera a fila, a taxa e o prazo de duração).

**Geração:** `hdast stack up <produto>` gera este arquivo por execução (`adapters/scope_proxy/generate.py`) a partir de `scope` e
`limits` do perfil, numa pasta por execução (`<HDAST_STATE_DIR>/stacks/<run_id>/policy`, passada ao compose como
`HDAST_SCOPE_POLICY_DIR`). O escopo e os limites são **iguais** aos do perfil, nunca mais largos; `not_after` é o menor entre a
duração máxima mais a folga do ajuste do `probe`, o fim da autorização e o fechamento da janela; `tls_verify_upstream` só é `false` quando o perfil desliga a
verificação E toda regra é local. A CLI relê o arquivo com o validador abaixo antes de gravar. Quem opera o lab à mão ainda pode
escrever o arquivo.

## Trava de emergência (kill switch)

Criar um arquivo chamado `KILL` **no diretório da política, no host**:

```bash
touch docker/scope-proxy/policy/KILL          # ou: touch "$HDAST_SCOPE_POLICY_DIR/KILL"; na pilha gerenciada: hdast stop
```

A partir daí **todo** pedido novo é negado com `kill_switch` (medido: o primeiro pedido depois do `touch` já é
negado, dentro de um segundo). Pedidos que esperam na fila da taxa são reconferidos ao acordar. Conexões já abertas
com bytes em voo não são cortadas.

**A trava é permanente até reiniciar o proxy**: remover o arquivo **não** religa o tráfego (observado). Foi escolhido
assim porque uma parada de emergência que se desfaz sozinha (arquivo apagado por engano, script de limpeza que passa
removendo) reabriria a saída justamente quando alguém pediu para fechá-la. Para retomar: remova o arquivo e rode
`docker compose restart scope-proxy`. `hdast stop` aciona a trava criando esse arquivo; o diretório é somente leitura **dentro**
do contêiner, mas o host o altera.

## Trilha de auditoria

Uma linha JSON por decisão em `audit/audit.jsonl` (pasta do host, sobrevive ao `down`) **e** na saída padrão
(`docker compose logs scope-proxy`):

```json
{"ts":"2026-11-13T06:09:35.489+00:00","run_id":"2026-11-13T00-00-00Z-lab-0002","method":"GET","scheme":"http","host":"vampi","port":5000,"path":"/users/v1/name1","query_params":["token","a"],"decision":"allow","reason":"allowed","status":200,"bytes":48,"duration_ms":7,"waited_ms":0}
```

- `ts`: instante em que o pedido foi liberado (depois da fila) ou recusado. `waited_ms`: tempo na fila da taxa.
- `path`: caminho **normalizado** (decodificado). Se a URL for malformada, o caminho cru escapado e truncado.
- `query_params`: **só os nomes**. Valores de consulta nunca são gravados. Cabeçalhos e corpos também não (o registro
  não tem campo para eles). O próprio mitmproxy roda com `flow_detail=0` para não imprimir URLs no log.
- `CONNECT` aparece com `method: CONNECT` e `path: ""`; as requisições internas do túnel aparecem em linhas próprias.
- `reason: upstream_error` com `decision: allow`: foi liberado, mas o destino falhou (ex.: certificado não confiável).
- Se a trilha deixar de ser gravável (disco cheio), o proxy **trava** (`audit_failure`) em vez de operar sem registro.
- Em Linux a pasta `audit/` precisa ser gravável pelo uid 10001 (`chown 10001 audit`); no Docker Desktop (Windows/macOS)
  isso não é necessário.

## Proteção do endereço resolvido

Depois do DNS, e **antes** de conectar, o proxy confere **todos** os endereços do nome: sem `allow_local: true` na regra
que casou o host e a porta, só passa endereço global; recusa loopback, rede privada, CGNAT, link-local (inclui
`169.254.169.254`), não especificado, multicast e reservado, e trata IPv6 que embute IPv4 como o IPv4. Com `allow_local`
passam loopback, rede privada e CGNAT (o laboratório precisa), mas **link-local e metadados da nuvem são recusados
sempre**. O IP conferido é o IP usado na conexão (o proxy não resolve de novo), o que fecha a janela de DNS rebinding
entre conferir e conectar; em HTTPS o SNI e a verificação do certificado continuam usando o nome.

## TLS

- A CA de interceptação é gerada pelo mitmproxy **ao iniciar o contêiner**, em `/run/mitm` (tmpfs, `0700`, uid 10001).
  A chave privada **não** vai para o repositório, a imagem nem um volume, e some quando o contêiner para.
- **Upstream**: o certificado do servidor de destino é verificado por padrão (a CA do sistema). Alvo com certificado
  autoassinado (o `vampi-tls` do lab) só funciona com `"tls_verify_upstream": false`, que a validação aceita **apenas**
  quando toda regra tem `allow_local: true`.
- **ZAP 2.17.0 não precisa importar a CA do proxy**: foi verificado que o ZAP aceitou o certificado interceptado sem
  configuração (`core/action/accessUrl` em `https://vampi-tls:8443/...` devolveu o corpo do alvo). Isto significa que o
  ZAP **não valida o certificado** do que está do outro lado do `CONNECT`. Risco residual: ver abaixo.
  Um cliente que **verifica** certificados (por exemplo o `curl` sem `-k`) rejeitará a CA do proxy; o `curl -k` das provas
  é só para os testes manuais.

## O que isto garante

- Toda requisição HTTP/HTTPS/1.1 que sai da pilha pelo proxy só passa se o `ScopeGuard` a permite: host, esquema, porta,
  caminho (com a normalização estrita da CLI: `;x=1`, ponto final, `%2e%2e`, dupla codificação etc. são recusados),
  método e `deny_paths` (que ignoram maiúsculas). Provado com o ZAP: numa varredura ativa limitada, todo `PUT`/`DELETE`
  e todo caminho fora da política foi negado (ver `lab/README.md`).
- A taxa máxima e a duração da execução valem para tudo que sai, não só para o que a CLI enviou.
- Nada passa sem rastro: cada decisão vira uma linha de auditoria, e sem auditoria o proxy trava.
- Sem política válida o proxy não sobe; não há "permitir tudo" por omissão.

## O que isto NÃO garante (riscos residuais)

- **Quem não usa o proxy.** O isolamento real é a rede Docker `internal: true`. O proxy só vale para o tráfego que chega
  a ele; se algum contêiner ganhar rota externa, o proxy não o vê. O `zap-gateway` (ponte) tem rota externa por
  necessidade do Docker Desktop (ver `lab/README.md`).
- **ZAP não valida o certificado** do proxy (acima). Um agente na rede `zap_net` poderia se passar pelo proxy; essa rede é
  isolada e só contém ZAP, proxy e ponte.
- **DNS**: o proxy fixa o IP conferido, mas um nome permitido cujo dono do domínio aponte para outro IP **público**
  continua permitido (mesma limitação do ScopeGuard, que decide por nome). Em IP privado só passa com `allow_local`.
- **HTTP/2, HTTP/3, WebSocket, TCP cru e UDP não são inspecionados: são recusados**, não filtrados. Um alvo que exija
  HTTP/2 ou WebSocket não funciona por este proxy. O ZAP fala HTTP/1.1 com o proxy.
- **Um `CONNECT` autorizado dá ao ZAP um túnel TLS que o proxy intercepta**; se o cliente enviar algo que não é HTTP
  (com `rawtcp=false`) a conexão falha. Não se testou um cliente malicioso que tente contrabandear requisições
  (request smuggling) além do que o parser HTTP/1 do mitmproxy já recusa.
- **Dados do alvo**: o proxy vê e processa corpos em claro (interceptação). Teto de 20 MiB por corpo (`body_size_limit`); o
  comportamento acima disso é o do mitmproxy e não foi testado aqui. Corpos e cabeçalhos não são gravados em lugar nenhum, mas ficam na memória do contêiner.
- **O motivo vem de um código estável** (`ScopeViolation.reason`, ADR 0026), não do texto da mensagem. `reason` continua
  `malformed_request` para toda recusa por forma da URL ou do caminho; o código granular (`path_encoded_slash`,
  `path_matrix_param`, `url_forbidden_char`...) vai no campo `detail` da linha de auditoria, que só aparece quando existe.
- **Modo de caminho (`path_mode` na política, ADR 0026).** `strict` (padrão) é o comportamento descrito acima. `wide`
  libera `;`, `%2f`, `%5c`, dupla codificação, `//` e ponto ou espaço finais pela leitura literal e nega se QUALQUER
  leitura do caminho casar com `deny_paths`. Risco aceito: uma leitura fora de `scope.allow` que não casa `deny_paths`
  é liberada (marcada em `detail: wide_reading_outside_allow`). A imagem precisa ser reconstruída para ler o campo.
- **Caminho na auditoria** vai inteiro até 2048 caracteres (escapado em ASCII); acima disso é cortado com `...[cortado]`.
- **A política só é lida ao iniciar.** Mudar `policy.json` com o proxy no ar não tem efeito até reiniciar.
- **A trava não corta conexões em andamento** e depende de o arquivo `KILL` ser criado no diretório montado.
- mitmproxy é código de terceiros: mantenha versão e digest atualizados (`requirements.in`, `Dockerfile`).

## Atualizar versões

1. mitmproxy: troque a versão em `requirements.in`, rode o comando de `uv pip compile` indicado nele e reconstrua
   (`docker compose build scope-proxy`). Repita as provas de `lab/README.md`, porque nomes de hooks e opções mudam.
2. Base Python: `docker pull python:3.13-slim-bookworm`, copie o digest do índice para o `ARG PYTHON_IMAGE` do `Dockerfile`.
3. Qualquer mudança no `ScopeGuard` ou nos modelos de escopo é herdada na próxima construção da imagem (o pacote
   `harness_dast` é instalado do repositório).

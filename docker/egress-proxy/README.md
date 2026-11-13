# Proxy de saída (egress-proxy)

Implementa a **camada 3** de AD-11: o ZAP não tem rota para fora e só alcança o
alvo através deste proxy, que **nega por padrão**. Usa o Squid
(`ubuntu/squid`, mantido pela Canonical), como forward proxy sem cache.

## Arquivos

| Arquivo | Papel |
|---|---|
| `squid.conf` | Regras fixas (ordem das ACLs, log, sem cache). Não é regenerado. |
| `policy/allowlist.txt` | Hosts **públicos** permitidos. **Vazio por padrão.** |
| `policy/allowlist-private.txt` | Exceções internas explícitas. Padrão: só `vampi` (o alvo do lab). |
| `policy/allowed-ports.txt` | Portas de destino permitidas (`80`, `443`, `5000`). |

## Como a decisão é tomada

Para cada pedido, o Squid avalia em ordem e para na primeira regra que casa:

1. Porta de destino fora de `allowed-ports.txt`: **nega** (vale também para `CONNECT`).
2. Host dado como **IP literal**: **nega**.
3. Host em `allowlist-private.txt`: **permite** (exceção explícita ao lab).
4. Destino cujo IP **resolvido** esteja em faixa privada, loopback, link-local
   (inclui `169.254.169.254`, metadados de nuvem), CGNAT ou multicast: **nega**.
5. Host em `allowlist.txt`: **permite**.
6. Qualquer outro: **nega**.

A regra 4 antes da 5 faz com que um nome público que passe a apontar para um
endereço interno (DNS rebinding) seja negado mesmo estando na lista.

Cada pedido, permitido ou negado, gera uma linha de log: instante, IP do
cliente, `RESULTADO/STATUS` (`TCP_DENIED/403` é bloqueio), método, URL e bytes.
O último campo é o user-agent, que distingue o ZAP (`Mozilla/5.0 ...`) de um
`curl`. Veja com `docker compose exec egress-proxy cat /var/log/squid/access.log`. O log
fica em tmpfs e some com o `down`; o harness deve copiá-lo ao fim da execução.

## Sintaxe da lista

Um nome por linha, `#` comenta. `api.hml.exemplo.com.br` casa exatamente esse
nome; `.exemplo.com.br` casa o domínio e todos os subdomínios (evite: amplia o
escopo). Referência: <http://www.squid-cache.org/Doc/config/acl/> (tipo
`dstdomain`).

## Como o harness vai regenerar a lista (planejado)

A cada execução, a CLI derivará `allowlist.txt` de `scope.allow[].host` do
`target.yml` (e `allowed-ports.txt` das portas da `base_url`), gravará os
arquivos e recarregará o proxy (`docker compose kill -s HUP egress-proxy` ou
reinício do serviço). A regeneração só **reduz ou iguala** o escopo autorizado;
nunca o amplia. Este fluxo é planejado: **nenhum comando `hdast` o faz hoje**.
Para um alvo real de IP público, o `allowlist-private.txt` deve ficar sem entradas. Para um ambiente de teste de empresa em IP privado, veja a próxima seção.

## Execução (verificada)

O contêiner roda como `proxy` (uid 13), sem capabilities, com rootfs somente
leitura e `/var/run/squid`, `/var/spool/squid` e `/var/log/squid` em tmpfs.
O Squid sobe com `allowlist.txt` só com comentários (avisa `empty ACL` e nega
tudo por aquela regra, que é o comportamento desejado). O aviso `HTTP requires
the use of Via` vem de `via off` e é intencional. O healthcheck usa
`squid -k check` para não gerar linhas de erro no registro.

## Ambiente de teste corporativo em IP privado

> **Não confirmado.** Esta seção vem da leitura de `squid.conf` e do achado A-08 da [revisão de QA](../../docs/reviews/2026-11-13-qa-m1-m2.md). Nenhum alvo corporativo em IP privado foi testado através deste proxy. A decisão definitiva fica para o M7, por ADR (item em aberto no [roadmap](../../docs/roadmap.md#itens-em-aberto)).

**O problema.** Ambientes de teste de empresa costumam resolver para IP privado (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`). No `squid.conf`, a regra 4 (`deny forbidden_ranges`) vem **antes** da regra 5 (`allow allowed_hosts`). Então um host colocado em `policy/allowlist.txt` que resolva para IP privado é **negado** (403), mesmo estando na lista. A lista geral, sozinha, não basta para esse caso.

**O que passa.** Só a regra 3: um host listado em `policy/allowlist-private.txt` é permitido **antes** da checagem de faixa privada. Ainda valem as regras 1 e 2: a porta de destino precisa estar em `policy/allowed-ports.txt` e o host não pode ser IP literal.

**Como permitir, passo a passo** (decisão de uma pessoa, nunca do agente):

1. Confirme na autorização formal que o ambiente é de teste, com dados sintéticos, e anote o nome DNS exato.
2. Inclua o nome em `policy/allowlist-private.txt`, uma linha, **nome exato** (`api.hml.empresa.interno`), sem ponto no início (`.empresa.interno` liberaria todos os subdomínios). Não altere o `squid.conf`.
3. Confira que a porta do ambiente está em `policy/allowed-ports.txt` (`80` e `443` já estão). Não amplie a lista de portas além do necessário.
4. Recarregue o Squid: `docker compose kill -s HUP egress-proxy` (ou reinicie o serviço). Os arquivos de `policy/` são montados somente leitura no contêiner, então a edição é feita no host.
5. Inclua o mesmo host em `scope.allow` do perfil: o `ScopeGuard` (camada 1) e o proxy (camada 3) precisam concordar.
6. Ao fim da execução, **remova a linha** e recarregue.

**O risco.** A regra 3 desliga, para esse nome, a proteção contra destino interno e contra DNS rebinding (um nome que passa a apontar para outro endereço). Se quem controla o DNS desse nome o apontar para outro serviço interno, ou para o endereço de metadados da nuvem, o Squid deixa passar, porque a decisão é por nome e não por IP. Por isso: nome exato, sem curinga, só pelo tempo da execução, e só quando o dono do ambiente confirmar quem controla aquele DNS. O comentário de `allowlist-private.txt` diz para não colocar ali host de produto real; essa é a regra padrão, e o uso acima é uma exceção consciente, com registro na autorização.

**O que a V1 pretende fazer (planejado, M7).** Derivar por execução as faixas privadas permitidas a partir do escopo, em vez de liberar o nome inteiro, ou então declarar que só alvos de IP público são suportados. Nenhuma das duas opções está implementada.

## Limites conhecidos deste controle

- O controle é por **nome de host e porta**, não por caminho nem método. Quem
  garante caminho e método é o ScopeGuard (camada 1) e o contexto do ZAP
  (camada 2). Uma porta liberada vale para todos os hosts liberados.
- Em HTTPS o proxy vê só o `CONNECT host:443`; não inspeciona o conteúdo.
- O DNS é resolvido pelo próprio proxy. Um host permitido que o dono do
  domínio faça apontar para outro IP **público** continua permitido.
- Proxy só vale para quem o usa. O isolamento real vem de o ZAP estar numa rede
  Docker `internal: true`; o proxy é o único contêiner com rota externa.
- Squid é código de terceiros: mantenha a imagem atualizada (tag e digest em
  `compose.yaml`).
- O Docker Desktop no Windows roda os contêineres numa VM; as redes valem
  dentro dela e não substituem firewall do host.
- Observado: com a lista vazia, `http://example.com` e `https://example.com`
  (CONNECT) são negados (403), assim como IP literal, `10.0.0.1`,
  `169.254.169.254` e `vampi:8000` (porta fora da lista).

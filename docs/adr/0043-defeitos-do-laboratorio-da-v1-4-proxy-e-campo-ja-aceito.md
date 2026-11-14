# 0043. Defeitos achados no laboratório da V1.4: conexão do proxy de escopo e campo que a entrada já aceita

- **Status:** Aceito
- **Data:** 2026-11-14
- **Origem:** prova em laboratório do teste de autorização da V1.4 (`tests/integration/test_lab_authz.py`). Corrige, sem mudar contrato, o adendo do [ADR 0040](0040-candidatos-de-campo-proibido-do-openapi.md) (`name_in_input` aceitava qualquer classe) e o addon do proxy de escopo ([ADR 0017](0017-proxy-de-escopo-com-scopeguard.md))

## Contexto

1. **Pedido que nunca chegava ao alvo.** No laboratório, de cada seis pedidos sem sessão (`anonymous_access`, `tampered_token`) um estourava o tempo de 15 s no cliente e virava `inconclusive`. Causa medida: o addon do proxy de escopo fixa o IP conferido na conexão de saída e tentava devolver o nome em `server_connected`; no mitmproxy 12.3.1 isso levanta `RuntimeError: Cannot change server.address on open connection` a cada conexão, e a conexão de saída nunca é reaproveitada. O ZAP reaproveitava a conexão de entrada e a sexta requisição ficava parada (`Failed to read ... within 20 seconds` no log do ZAP; nenhuma linha no proxy).
2. **Falso positivo da atribuição em massa.** O adendo do ADR 0040 fez `name_in_input` aceitar qualquer classe conhecida. Um campo que o corpo normal já leva (por exemplo `valor` do cadastro de consulta, obrigatório no OpenAPI) mudar na leitura seguinte é entrada legítima, não atribuição em massa; o achado médio no modo seguro era isso.
3. O campo enviado aparecia duas vezes em `fields` quando o efeito era visto nele mesmo.

## Decisão

- O addon deixa de alterar o endereço numa conexão aberta (remove `server_connected`) e responde `Connection: close`: uma conexão por requisição entre o ZAP e o proxy. O IP conferido continua fixado na conexão de saída; nenhuma trava foi afrouxada e todo pedido segue passando pelo proxy.
- `name_in_input` só vale para a classe `privilege` (o que o ADR 0040 dizia no texto original). As demais classes só entram por `readonly_in_input`, `response_only` ou declaração em `authz.mass_assignment_fields`.
- `fields` do achado de atribuição em massa não repete o campo enviado. O fingerprint dos achados em que o efeito aparecia no próprio campo muda uma vez (a lista ficou sem a repetição).

## Consequências

- Precisa reconstruir a imagem do proxy (`hdast stack up --build`).
- No laboratório, `anonymous_access` testou 16 de 19 operações e `tampered_token` 8 de 19 antes; 19 e 18 depois.
- Um campo de preço ou saldo que o corpo já declara deixa de ser testado por derivação; o dono pode declará-lo em `authz.mass_assignment_fields`.

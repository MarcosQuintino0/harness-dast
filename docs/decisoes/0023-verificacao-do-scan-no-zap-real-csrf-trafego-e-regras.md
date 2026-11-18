# 0023. Verificação do `scan` no ZAP real: CSRF durante a varredura, tráfego medido no proxy e regras desligadas

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** Verificação de M4 contra o ZAP 2.17.0 real e o proxy de escopo real (VAmPI e Clínica Piloto); corrige pontos do [ADR 0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md)

## Contexto

O `scan` e o `report` foram escritos contra um ZAP simulado. A lista de conferência do ADR 0022 (12 itens) foi percorrida contra o ZAP real. Três resultados mudam o que o ADR 0022 afirmava:

1. `ascan/action/disableScanners` recusa o pedido **inteiro** (`does_not_exist`) se UM id não existe na imagem. O id 10095 (Backup File Disclosure) é uma regra passiva e não existe no varredor ativo. Os outros nove ids existem e ficam `enabled=false` depois do pedido.
2. O CSRF por cookie duplicado da Clínica Piloto (cookie `XSRF-TOKEN` mais cabeçalho `X-XSRF-TOKEN`, valores iguais; o alvo aceita qualquer par igual, que não gira nem expira) ficava correto na maior parte da varredura porque o varredor clona a requisição aprendida, que já leva o par. Medido no histórico do ZAP numa varredura completa de 29 min: das `POST`/`PUT`/`PATCH` que chegaram ao alvo, cerca de 6% (34 de 536 e 36 de 697) foram recusadas com `XSRF_INVALIDO`. Todas eram das regras de execução remota de PHP (CVE-2012-1823, ids 20017 e 20018), que reconstroem a requisição **sem** o cabeçalho `Cookie` (cerca de 2 por varredura, em todas as operações, inclusive nas de leitura). A regra `REQ_HEADER_STR` do Replacer não acrescenta um cookie ausente.
3. O proxy de escopo é o único lugar que enxerga TODO o tráfego do varredor, inclusive o que ele inventa fora do escopo (centenas de caminhos com caracteres de controle e caminhos fora de `scope.allow`).

## Decisão

Vamos:

1. Manter o Replacer para entregar o token de autenticação (comprovado em 100% das requisições do varredor ativo) e trocar a regra do cookie de CSRF por um `REQ_HEADER` sobre `Cookie` com `NOME=valor`: no ZAP real ele **acrescenta** o cabeçalho quando falta e o define quando existe, então toda requisição do varredor leva o par, inclusive as das regras PHP. Custo: na V1 (autenticação por cabeçalho) o único cookie que a varredura envia é o do CSRF; os demais cookies do alvo são descartados nos ataques. Medido depois da troca: 547 de 547 escritas do varredor com cabeçalho e cookie iguais e zero recusas por CSRF (com renovação do par a cada 15 s: 13 valores diferentes, todos coerentes). Scripts do ZAP foram descartados (abaixo).
2. Ler a regra desligada de volta (`ascan/view/scanners`) **antes** de desligar e recusar a execução (saída 4) citando os ids que a imagem não tem, em vez de deixar o ZAP falhar com `does_not_exist`. Remover o id 10095 da lista padrão.
3. Gravar em `scan.json` o resumo do tráfego do proxy durante o scan (`traffic`): liberados, negados por motivo, duração, taxa média e pico por segundo, e o limite do perfil. O `report` mostra "N requisições que o varredor tentou foram bloqueadas pelo escopo". A fonte é a trilha de auditoria do proxy (`audit.jsonl`), lida por uma porta nova (`ProxyAudit`).
4. Limitar o teto de cada regra (`max_rule_minutes`) também por `limits.max_duration_minutes`.
5. Recusar `--only` com `operation_id` que a execução não tem (antes o plano saía vazio, sem erro).

## Alternativas consideradas

- **Script do ZAP (HttpSender) para acrescentar o cookie.** Exige carregar um arquivo no sistema de arquivos do ZAP e dá ao ZAP código executável vindo da CLI. Descartada: o ganho é 1% das requisições, só de regras PHP irrelevantes para APIs Java.
- **Manter só `REQ_HEADER_STR` (troca o valor do cookie quando ele existe).** Foi a primeira versão e deixou 6% das escritas do varredor sem o cookie. Substituída pelo `REQ_HEADER` sobre `Cookie`; o preço (descartar outros cookies) é aceitável porque a V1 só autentica por cabeçalho, e um produto com sessão por cookie exigirá novo ADR.
- **Contar a taxa pelo próprio ZAP (`reqCount`).** Não enxerga as requisições negadas pelo proxy e não prova o que chegou ao alvo. Descartada.

## Consequências

- `scan.json` ganha o campo `traffic` (aditivo; `findings.json` repete em `coverage.traffic`). Arquivos antigos continuam legíveis (valor padrão `enabled: false`).
- O relatório diz quantas tentativas fora do escopo o proxy barrou e a que taxa o alvo foi atingido, com dado de quem está no meio do caminho.
- Uma execução cortada à força (processo morto sem Ctrl+C) deixa regras `hdast-` no ZAP. O próximo `scan` as remove na partida (`remove_stale_rules`); `stack up` recria o ZAP. Documentado em [../reference/scan.md](../reference/scan.md).
- Fica registrado que a atribuição por `sourceMessageId` de uma injeção em caminho cai na operação VARRIDA, não na rota que respondeu (por exemplo, `GET /users/v1` varrido gera `GET /users/v1/'`, que o VAmPI roteia para `/users/v1/{username}`).

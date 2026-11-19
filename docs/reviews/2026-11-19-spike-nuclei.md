# Spike do Nuclei no harness-dast

19 de novembro de 2026 · Branch `spike/nuclei` (nunca entra na `main`) · Parte dinâmica rodada no Codespace do projeto, em pilhas `-claude`, só com Clínica Piloto, VAmPI, crAPI e um alvo de pilha criado para o spike.

**Veredito curto.** O Nuclei cabe atrás da cerca sem abrir nenhuma brecha medida e custa segundos. Mas, no desenho do plano (só modelos que cabem inteiros no escopo, projeção estrita), ele **não achou nada que o ZAP e o inventário já não achassem** nos três alvos do laboratório. O único ganho medido veio do Spring Boot Actuator, num alvo que eu mesmo configurei com o Actuator aberto, e só depois de relaxar a projeção. Recomendação: **não adotar como "segundo motor geral"**; se o dono quiser, adotar como módulo estreito de exposições conhecidas, com as três mudanças da seção "Recomendação". A decisão final é do dono.

## Proveniência e imagem

| Insumo | Versão | SHA-256 | Como foi conferido |
| --- | --- | --- | --- |
| Pacote Linux amd64 do Nuclei | v3.11.1 (2026-08-08) | `ea63d4ae232808cd7c6bc00d0142428e231fab59dae01042246097d195835ab6` | `sha256sum -c` no build, contra o valor fixo no Dockerfile (o do arquivo de checksums da release) |
| Executável dentro do ZIP | v3.11.1 | `c49588140f357cbdddd5436dec11201953a4c5390faeec90777f9ee2cfd70251` | Calculado no build (`/opt/nuclei.sha256` na imagem); igual ao do relatório parcial |
| nuclei-templates | v10.5.1 (2026-10-23) | `00184ad496302cd1dd3cf4b0b1c3aa45d6b35057f7bdf17e932318185ba0ac50` | Arquivo da tag (`archive/refs/tags/v10.5.1.zip`); o ZIP anexado ao release não existe como asset (a API lista só o arquivo de checksums), e o hash do arquivo da tag é igual ao do checksums |
| Imagem base | `alpine:3.22` | `sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f` | Fixada por digest no Dockerfile |

- `docker/nuclei/Dockerfile`: estágio de download com verificação, estágio final com usuário `nuclei` (uid 10002), sem atualização em execução (`-duc -ni -ud /opt/nuclei-templates`).
- `docker/nuclei/compose.spike.yaml`: serviço `nuclei` só na `zap_net` (interna, sem rota), `cap_drop: [ALL]`, `read_only`, `no-new-privileges`, `tmpfs`, `mem_limit: 512m`, `pids_limit: 128`. O `compose.yaml` versionado não foi alterado.
- Rota da imagem: tabela de rotas do contêiner só tem a sub-rede `172.19.0.0/16`, sem rota padrão.

## Censo regenerado no Codespace

Rodado de novo a partir do ZIP conferido: **idêntico ao relatório parcial** (14.101 modelos; 7.852 depois dos vetos; 1.436 com todos os pedidos de leitura literais; 53 na Clínica Piloto, 27 no VAmPI, 0 no crAPI; 278 caminhos literais GET de exposição).

- **Lista literal de exposições:** 277 caminhos (os 278 menos `/../../web.config`, que o perfil recusa por conter `..`). Em `docs/reviews/2026-11-19-spike-nuclei-dados/exposures.txt` (e `exposures.json`, com os modelos de cada caminho).
- **Limite do perfil:** 200 caminhos por regra. A lista entra em 2 regras `GET` por alvo.
- **Seleção por perfil** (`scripts/spike_nuclei_select.py`): (a) cabem inteiros no escopo do Swagger; (b) cabem depois de somar a lista ao escopo.

| Perfil | (a) Swagger | (b) Swagger + lista |
| --- | ---: | ---: |
| Clínica Piloto | 53 | 321 |
| VAmPI | 27 | 277 |
| crAPI | 0 | 273 |
| Alvo de pilha (Actuator) | 53 | 321 |

### Achado de desenho: a projeção estrita erra o alvo que mais interessa

Os modelos do Actuator ficam em `http/misconfiguration/springboot/` (fora de `http/exposures/`, de onde sai a lista), usam `stop-at-first-match` (chave extra, que a projeção estrita rejeita) e alguns trazem caminhos que a cerca recusa por desenho (`/actuator;/env;`, `%72`, `{{BaseURL}}` puro).

| Medida (`scripts/spike_spring_fit.py`) | Valor |
| --- | ---: |
| Modelos Spring Boot sem veto | 33 |
| Aceitos pela projeção estrita do censo | 1 |
| Caberiam inteiros se a projeção aceitasse chaves extras inofensivas | 29 |
| Com um caminho que o perfil recusa (`;`, `%72`, base pura) | 4 |

Por isso a variante (b) do plano deu **0 achados no alvo de pilha**. A variante "relaxada" (`scripts/spike_nuclei_relaxed.py`: os 33 modelos Spring, só os 67 caminhos literais aceitos pelo perfil na lista) está na seção do critério 1.

## Critérios do plano

| # | Critério | Limiar do plano | Medido | Situação |
| --- | --- | --- | --- | --- |
| 1 | Ganho real | ≥ 2 achados reais que nem ZAP nem inventário pegam, ≥ 1 no alvo de pilha | Clínica 0, VAmPI 0 exclusivo, crAPI 0. Alvo de pilha: 13 (estrito: 0; relaxado: 13) | **Só em parte.** O ganho existe numa classe (Actuator aberto), mas só com projeção relaxada e num alvo que eu configurei de propósito; não foi provado em alvo independente |
| 2 | Escopo | 100% dos pedidos na auditoria, zero fora | Todas as execuções: contador do Nuclei ≤ linhas da auditoria; zero tentativa fora da cerca | **Atendido** (limites na seção 2) |
| 3 | Ruído | 0 achado médio ou maior falso no VAmPI e no crAPI | VAmPI: 1 informativo (`openapi`, verdadeiro); crAPI: 0; nenhum médio ou maior em nenhum alvo | **Atendido** |
| 4 | Tempo | ≤ 5 min a mais em LOW com o `-rl` real | Maior execução do Nuclei: 10 s (321 modelos, 329 pedidos) | **Atendido**, com folga |
| 5 | Custo-benefício | Ganho maior que religar as regras do ZAP com a lista | ZAP religado (40034 e 40035): 0 achados em 4 alvos. Nuclei estrito: 0 achados novos. Nuclei relaxado: 13 no alvo de pilha | **Empate no desenho do plano; vantagem do Nuclei só no relaxado**. Volta ao dono |
| 6 | Login | Token fora de argumento, log e artefato; só leitura com conta | Caminho 1 (Replacer): 0 JWT em 148 artefatos do Nuclei; caminho 2 (`-sf`): 0 ocorrências do marcador em 9 verificações | **Atendido nos dois caminhos**, com ressalvas (seção 6) |

### 1. Ganho real

Execuções (todas com `-ni -duc -pt http -rl 50 -c 5 -bs 1 -jsonl -omit-raw`, atrás da cerca; `-rl` igual a `limits.requests_per_second` dos perfis, 50):

| Alvo | Variante | Modelos | Pedidos na auditoria | Achados | Tempo (parede / interno) |
| --- | --- | ---: | ---: | ---: | --- |
| VAmPI | (a) Swagger | 27 | 4 | 0 | 1,5 s / 0,33 s |
| VAmPI | (b) Swagger + lista | 277 | 282 | 1 (`openapi`, informativo, `/openapi.json`) | 6,9 s / 6,2 s |
| Clínica Piloto | (a) | 53 | 52 | 0 | 2,1 s / 1,4 s |
| Clínica Piloto | (b) | 321 | 329 | 0 (todas as respostas 401, sem login) | 7,9 s / 7,1 s |
| crAPI | (a) | 0 | n/a | n/a | n/a |
| crAPI | (b) | 273 | 279 | 0 (todas 200, o servidor devolve a página inicial para qualquer caminho) | 6,9 s / 6,1 s |
| Alvo de pilha | (a) | 53 | 52 | 0 | 2,1 s / 1,4 s |
| Alvo de pilha | (b) | 321 | 329 | 0 | 8,0 s / 7,2 s |
| Alvo de pilha | relaxada (33 modelos Spring) | 33 | 67 | **13** | 2,7 s / 2,0 s |

- O crAPI tem 0 modelos no escopo do Swagger, como previsto: registrado, e a variante (b) seguiu.
- O serviço de identidade do crAPI não traz Actuator: a imagem usada (`crapi/crapi-identity`, digest `sha256:5152eaa8b25d8585068ec478c9a2ee886ce1658d8289fd047f83325737490f78`) foi inspecionada (listagem do jar: 0 entradas com `actuator`). Por isso foi criado o alvo de pilha em `lab/actuator/`.
- **Alvo de pilha** (`lab/actuator/`): Spring Boot 3.5.16, imagens por digest iguais às da Clínica Piloto, Actuator exposto de propósito (`management.endpoints.web.exposure.include=*`, `env.show-values=ALWAYS`), só na rede interna do laboratório, nada publicado no host. O alvo é meu; os achados são do tipo "Actuator aberto", comum em produção, mas **não são independentes** do que eu configurei.
- Os 13 achados do relaxado: `springboot-env`, `-configprops`, `-beans`, `-mappings`, `-threaddump`, `-loggers`, `-metrics`, `-caches`, `-conditions` (baixa), `-health`, `-scheduledtasks`, `-actuator`, `-whitelabel` (informativa).
- **ZAP religado + inventário no mesmo alvo** (um `hdast scan` com `SPIKE_ZAP_REENABLE=40034,40035` e `extra_checks.inventory`, uma operação, LOW): 1 alerta baixo (cabeçalho), inventário 0, regras 40034 e 40035 sem alerta. Nenhum dos 13 achados do Actuator.
- Gravidade: o Nuclei marca quase tudo do Actuator como baixa; com `show-values=ALWAYS` o `/actuator/env` expõe valores de configuração, então a baixa subestima o risco real. A tabela fixa do plano manteria "baixa". Decisão de severidade fica fora do spike.

### 2. Escopo e contornos da cerca

| Prova | Resultado medido |
| --- | --- |
| Pedidos × auditoria | Em 13 execuções, o total de pedidos do Nuclei bateu com as linhas da auditoria (por exemplo 4/4, 282/282, 329/329, 279/279). Em HTTPS a auditoria tem o dobro (um `CONNECT` mais o pedido interno); em redirecionamento, uma linha a mais (o salto). Na relaxada o contador do Nuclei contou 84 e a auditoria 67 (pedidos planejados que o `stop-at-first-match` não enviou). Nenhuma linha de host ou porta fora do alvo |
| Fora do escopo | O Nuclei com a lista (b) contra uma pilha só com o Swagger (VAmPI): 282 pedidos, 278 negados com `path_not_allowed` (403), 4 permitidos (404 ou 200) |
| DNS | Na rede interna, `getent` resolve `scope-proxy` e `zap`; **não** resolve `vampi`, `github.com`, `example.org` nem um nome inexistente. O Nuclei usa o nome do alvo só pela cerca |
| `-max-host-error` | Não foi acionado: o 403 da cerca é uma resposta, não erro (`errors:"0"` nas 282 respostas, 278 delas negadas). O Nuclei não abandonou o host. Não medi o caso de erro de conexão (por exemplo, com o `KILL`) |
| `Host` diferente | `-H "Host: outro.exemplo"`: o Nuclei muda o destino, a cerca recebeu `outro.exemplo:80` e negou (`host_not_allowed`, 4 de 4). `Host: vampi` (porta 80): negou (`origin_not_allowed`). `Host: vampi:5000`: igual ao destino, permitido. Nenhum caso de `Host` divergente passou |
| HTTPS | O túnel (`CONNECT`) é decidido por host e porta e o pedido interno por caminho: 282 `CONNECT` permitidos e 278 pedidos internos negados por caminho. O Nuclei não verifica o certificado por padrão, então ele aceitou a CA da cerca sem carregá-la (**não** provei a validação do certificado). O front TLS do laboratório é autoassinado e a cerca recusa o upstream (502, `upstream_error`), por desenho |
| Redirecionamento | O Nuclei com `-fr`: o salto para um caminho fora do escopo (mesmo host) foi negado (`path_not_allowed`), o salto para `fora.invalid` foi negado (`host_not_allowed`); ambos na auditoria |
| Rede | A rede é `internal`, sem rota padrão, sem DNS externo. As execuções não tiveram nenhuma linha de host fora do alvo na auditoria. **Não** capturei pacotes: a ausência de telemetria é inferida da falta de rota e de DNS, não observada num `tcpdump`. O Nuclei traz flags de nuvem (`-auth`, `-cloud-upload`); nenhuma foi usada e o log disse "Scan results upload to cloud is disabled" |
| Não testei | Conexão direta por IP (o hook do projeto barrou o `wget` do teste; a tabela de rotas sem rota padrão é a evidência) |

### 3. Ruído

| Alvo | Achados médios ou maiores (falsos) | Limiar |
| --- | --- | ---: |
| VAmPI | 0 (1 informativo verdadeiro) | 0 |
| crAPI | 0 | 0 |
| Clínica Piloto, alvo de pilha | 0 | n/a |

O crAPI responde 200 a qualquer caminho: foi o caso mais propenso a falso positivo e não gerou nenhum, porque os modelos têm confirmação por conteúdo.

### 4. Tempo

Máximo medido do Nuclei: 10 s de parede (321 modelos, 329 pedidos, `-rl 50`). Em todos os alvos, de 0,3 s a 10 s; o limiar é 5 min. O ZAP religado fez 53 pedidos a mais por varredura (1 da 40034 e 52 da 40035) em 1,4 a 3,5 s.

**Risco operacional.** Em 3 execuções o contêiner do Nuclei **travou na partida** (só o banner; sem conexão aberta, processo dormindo): uma levou 186 s, e duas ficaram paradas até eu derrubar o contêiner. Duas foram com a entrada padrão ligada a um pipe aberto; a terceira, com `compose run -d`. Com a entrada padrão em `/dev/null` não repetiu nas dezenas de execuções seguintes. A causa exata não foi isolada. O runner da CLI precisa fechar a entrada padrão e impor prazo com morte do contêiner.

### 5. Custo-benefício

| Opção | Pedidos extras | Achados novos (ZAP e inventário não pegam) |
| --- | ---: | ---: |
| ZAP com 40034 e 40035 religadas + a lista no escopo | 53 por varredura | 0 nos 4 alvos |
| Inventário do ADR 0102 | 1 a 5 por varredura | 1 (`/openapi.json` no VAmPI, `/v3/api-docs` na Clínica), os mesmos que o Nuclei `openapi` |
| Nuclei estrito (plano) | 4 a 329 | 0 |
| Nuclei relaxado (33 modelos Spring) | 67 | 13 (Actuator) |

As regras 40034 e 40035 do ZAP **não usam a lista**: têm a lista de caminhos delas; o que a lista faz é só permitir que a cerca deixe passar. Foram 0 alertas nos quatro alvos, inclusive no alvo com o Actuator aberto. No desenho estrito há empate (ambos ≈ 0), e a vantagem do Nuclei só aparece na classe do Actuator, com projeção relaxada.

### 6. Login

| Caminho | Resultado |
| --- | --- |
| **1. Pelo ZAP (Replacer)** | Na Clínica Piloto, com o `hdast scan` de `obterPerfil` rodando e o Nuclei apontado ao `http://zap:8080`: a sonda `GET /api/me` casou (200) em 2 de 47 voltas (nas demais, 401), as duas dentro da janela em que o Replacer estava ativo. O Nuclei nunca recebeu o token (o `curl-command` do achado não traz `Authorization`) e 0 dos 148 artefatos do Nuclei contêm padrão de JWT ou `Bearer`. Com a lista (b) completa pelo ZAP durante a janela: 0 achados (321 modelos, 2 vezes) |
| Custo do caminho 1 | (i) O token só existe no ZAP **enquanto o `hdast scan` roda**, e a conta é a da operação varrida: o Nuclei não escolhe conta nem tem janela própria. (ii) O ZAP passou a ver o tráfego do Nuclei: dos 1.060 alertas passivos da execução, **813 (77%)** foram em caminhos da lista do Nuclei (informativos e baixos: 357 "Cookie No HttpOnly", 324 "Application Error Disclosure", 344 "Session Management" etc.; alta e média: 0 vindas do Nuclei). Sem filtro, isso polui o relatório do ZAP |
| **2. Arquivo de segredos (`-sf`) em tmpfs** | Teste com um **marcador sintético** no lugar do token (não li nem usei credencial real): arquivo em `/dev/shm` (tmpfs do host), dono uid 10002, modo `0400`, montado `:ro`. Sem `-sf` a sonda não casa (o alvo responde `NAO_AUTENTICADO`); com `-sf` casa (o alvo responde `TOKEN_INVALIDO`, o que prova que o cabeçalho chegou). O marcador **não** apareceu em `docker inspect`, `docker top`, `/proc/1/cmdline`, ambiente do contêiner, saída, log, nem na auditoria da cerca (0 ocorrências nas 9 verificações); o arquivo foi apagado no fim. O dono do arquivo teve de ser o uid do contêiner (`sudo chown 10002` no host do Codespace): a CLI real precisará resolver esse mapeamento de usuário. O processo mostra só `-sf /secrets/s.yaml` |
| Ressalva do caminho 2 | Provado só com marcador sintético; **não** medi com token real de login (exigiria código novo na CLI para o login e a gravação do arquivo). O segredo vale para todas as requisições ao domínio durante o `run`; só modelos de leitura rodam porque a lista vem do filtro por método (`GET`, `HEAD`, `OPTIONS`), não porque o `-sf` restrinja |
| Só leitura | As listas usadas só têm `GET`; as sondas também. A filtragem por método é do manifesto (censo), não do Nuclei |

**Recomendação de login.** O caminho 1 funciona e o Nuclei não vê o token, mas amarra o Nuclei à janela do `scan` e acrescenta ruído de alertas no ZAP. Recomendo o **caminho 2 (`-sf`)**, desde que a CLI grave o arquivo com o token real e ele seja apagado no fim; esse trecho não foi medido com token real.

## Saída sem segredo, com saída real do Nuclei

`scripts/spike_nuclei_sanitize.py` projeta a saída `-jsonl` por **lista branca**: `template_id`, severidade mapeada pela tabela do plano, caminho, e, se houve valor extraído, só `secret_type`, `secret_count` e `secret_length_bytes`.

- Entrada real: os 13 registros do alvo de pilha. A saída bruta tem `curl-command` **mesmo com `-omit-raw`** e `extracted-results` (no `springboot-actuator`: 21 valores).
- Saída limpa: 0 das 4 chaves sensíveis; marcadores tirados do bruto (`sbom-id`, `configprops-prefix`, `Mozilla/5.0`) presentes no bruto e **ausentes** da saída limpa. Exemplo: `{"template_id": "springboot-actuator", "severity": "informativa", "path": "/actuator", "secret_type": "extracted_value", "secret_count": 21, "secret_length_bytes": 196}`.
- Limite: não obtive um segredo real exposto na saída do Nuclei. O modelo `aws-access-key-value` tem `\b` entre aspas duplas (vira caractere de retrocesso no YAML) e não casou, mesmo com a chave de exemplo da documentação da AWS no alvo; então o "tipo e tamanho de segredo" foi mostrado com valores extraídos não sensíveis.

## O que não medi

- Pacotes na rede (`tcpdump`): a telemetria foi inferida pela falta de rota e de DNS e pela auditoria.
- Conexão direta por IP (barrada pelo hook) e erros de conexão com `-max-host-error` (por exemplo, `KILL` da cerca).
- Validação do certificado da cerca pelo Nuclei (ele não verifica por padrão).
- Login com token real no caminho 2.
- Achados exclusivos num alvo independente (o Actuator é meu).
- Causa da partida travada do contêiner do Nuclei.
- Reprodução do inventário do ADR 0102 fora de uma varredura do ZAP (usei o do `hdast scan`).

## Recomendação honesta

1. **Como "segundo motor geral": não vale.** No desenho do plano o ganho medido sobre ZAP mais inventário foi zero nos três alvos do laboratório, e o tempo e o escopo, embora bons, não pagam um segundo motor.
2. **Como módulo estreito de exposições conhecidas (Actuator e arquivos de configuração): talvez valha**, e a decisão volta ao dono, porque o ganho (13 achados) vem de uma classe real, mas só com mudanças que o plano não previa:
   - a projeção precisa aceitar `stop-at-first-match` (e, nos modelos Spring, caminhos que a cerca recusa podem ficar de fora, com o resto do modelo rodando);
   - a lista de exposições tem de sair de `http/misconfiguration/` (não só de `http/exposures/`) e o `{{BaseURL}}` puro tem de virar `/`;
   - o runner precisa fechar a entrada padrão e impor prazo.
3. **Login:** caminho 2 (`-sf`), com prova de token real ainda por fazer.

## Reprodução

Tudo no Codespace, checkout `/workspaces/n-spike` (branch `spike/nuclei`), sem commit.

- Imagem: `docker build -t hdast-nuclei-spike:3.11.1-10.5.1 docker/nuclei`.
- Alvo de pilha: `docker build -t hdast-alvo-actuator:1.0.0 lab/actuator`.
- Pilhas (aprovação descartável do suporte de integração, **sem** `profile approve`, via `scripts/spike_nuclei_lab.py`, que usa `tests.integration.lab_support.LabCli`; sufixo `-claude`; `SPIKE_ROOT` isola estado e produtos): `hdast stack up vampi`, `clinica-piloto`, `crapi`, `alvo-pilha`.
- Execução do Nuclei: `scripts/spike_nuclei_run/nuclei_run.sh NOME PROJETO ALVO LISTA` (usa `docker compose -p hdast-claude -f compose.yaml -f docker/nuclei/compose.spike.yaml run --rm --no-deps -T nuclei -u ALVO -t LISTA -ud /opt/nuclei-templates -proxy http://scope-proxy:3128 -pt http -rl 50 -c 5 -bs 1 -jsonl -omit-raw -ni -duc -nc`).
- ZAP religado: `scripts/spike_nuclei_run/zap_c.sh` (com `SPIKE_ZAP_REENABLE=40034,40035`, ajuste de duas linhas em `src/harness_dast/domain/scan_policy.py` só neste spike; as `extra_checks.inventory` foram ligadas na cópia do perfil do laboratório, em produto real só a carta liga).
- Login: `login_test.sh` (caminho 1) e `sf_test.sh` (caminho 2).
- Dados: `docs/reviews/2026-11-19-spike-nuclei-dados/` (lista de exposições, seleções por perfil, medições). Perfis estendidos e saídas brutas ficaram em `/tmp/spike` do Codespace.
- Ao fim, `docker compose ls -a` sem projeto, sem contêiner, rede ou volume `-claude`.

### Limites da prova

- Só laboratório; alvos sintéticos; um Codespace; uma passada por variante (sem repetição estatística).
- Aprovação de escopo pelas aprovações descartáveis do suporte de integração; perfis estendidos feitos por mim com `scripts/spike_nuclei_select.py`.
- A comparação com o ZAP foi uma operação por alvo, LOW, com duas regras religadas; não é uma varredura completa.
- O crAPI e a Clínica têm login; o Nuclei sem login só vê a tela de autenticação nesses alvos.

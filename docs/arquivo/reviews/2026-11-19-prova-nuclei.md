# Prova do Nuclei como segundo motor no laboratório

19 de novembro de 2026 · Branch `feat/nuclei-p8-lab` (sobre a integração `feat/nuclei`, commit `d40b30d4`) · Prova do [ADR 0122](../../decisoes/0122-nuclei-como-segundo-motor.md), aceites 2 a 6 e a segunda cerca desligada.

Tudo rodou no Codespace do projeto, só contra alvos do laboratório (Clínica Piloto, VAmPI, crAPI e o alvo Spring com Actuator), em contêineres com dados sintéticos, em pilhas com sufixo `-claude`, derrubadas no fim. O tráfego aos alvos saiu só por comandos `hdast` e pelo contêiner do Nuclei atrás da `scope-proxy-nuclei`. Os testes apenas **leem** as trilhas de auditoria, o Docker e os arquivos da execução. Nenhum `curl`, `wget` ou script falou com um alvo.

**Aprovação do escopo.** Nenhum `profile approve`, `setup`, `secret set`, `mutation release`, `demo` nem limpeza foi rodado. A aprovação de cada perfil é a do suporte de integração (`LabCli.approve_installed_products`, que usa `approval_for`), como nos demais testes de laboratório. O papel da carta (`extra_checks.nuclei`, `nuclei_login`, `nuclei_wide_paths`) foi feito na **cópia descartável** do perfil, antes do `stack up`. Força LOW em tudo (o perfil de laboratório roda no teto de 50 pedidos por segundo, como os outros).

## Veredito curto

Os aceites 2, 4, 5 e 6 e a segunda cerca desligada foram medidos e **passaram**. O aceite 3 passou **com uma ressalva de contagem** (11 achados do Actuator mais 2 identificações de tecnologia, e não 13 achados; seção própria abaixo). A prova achou **um defeito** no código, corrigido com o teste que o reproduz: o prazo do contêiner era igual ao do portão, o erro do runner vencia e o resultado parcial se perdia. Nenhum achado médio ou maior em nenhum alvo. Os limites da prova estão no fim.

## Imagens e versões

| Item | Versão ou identificação |
| --- | --- |
| Máquina | Codespace `rodada-cega-plugin`, Linux 6.8.0-1070-azure, 4 vCPU, 16 GB |
| Docker, Compose | 29.9.3-1, 5.8.0 |
| Nuclei | v3.11.1 (binário conferido por SHA-256 no build) |
| Modelos | `nuclei-templates` v10.5.1, manifesto empacotado com a CLI |
| `hdast/nuclei:local` | `sha256:9d6b601f3c9e5d52bc19a295422ecd7b641dd5636ed9adc1e453e4b729786069` (591 MB), base `alpine:3.22@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f`, rótulo de versão 1.12.2 |
| `hdast/scope-proxy:local` | `sha256:3179076cc058f7e9795d63aa57bbbc463466e1662f92296d0bdf1d3acd2c7a5c`, versão 1.12.2 (as duas cercas usam esta imagem) |
| `hdast/zap:local` | `sha256:66ab0c770d37ac36c3b04b2a904b38f4cddfba239015c04bb874d816a391f3b9` |
| `hdast-alvo-actuator:1.0.0` | `sha256:754a820285770ed3ba36f0d86fcc2bc8910a3ab0148443d8dcc99bd12e0fc581`, Spring Boot 3.5.16; bases `maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a…` e `eclipse-temurin:21-jre-alpine@sha256:ac05c3c4…`, as mesmas da Clínica Piloto |
| `hdast-clinica-piloto:1.0.0` | `sha256:e88fbca970e79b35f5dc5b4f5855defc25f43b371ebef308ac38d9c188b7acd7` |
| VAmPI | `erev0s/vampi:latest@sha256:0a5a224b6e14ae7da6a6ea265178ff71286ff903aec74adee98f660bb0e4ca12` |
| crAPI | `1.1.6-rc8`, imagens por digest (as do `compose.yaml` do laboratório) |

**Alvo Spring.** Trazido de `spike/nuclei` para `lab/actuator/`: Actuator exposto de propósito (`exposure.include=*`, `env.show-values=ALWAYS`), só na rede interna `hdast_lab_net` (nenhuma porta no host), endereço `alvo-actuator:8080`, `cap_drop: ALL`, rootfs somente leitura. O `hdast stack up` o reconhece pelo host (`ALVO_ACTUATOR` em `lab_targets.py`, projeto `hdast-actuator`). O perfil (`lab/actuator/product-profile/target.yml`) liga `extra_checks.nuclei` e `nuclei_wide_paths` (o Actuator não está no Swagger), deixa as três escritas e o login desligados e nega `/actuator/heapdump` e `/actuator/shutdown` em `scope.deny_paths`. O alvo não tem login: a conta `api_key` do perfil existe só porque o schema exige uma.

## Comandos

```bash
# Ambiente de todas as rodadas (pilhas com sufixo, métricas fora do repositório)
export HDAST_IT_STACK_SUFFIX=-claude HDAST_IT_METRICS_DIR=/tmp/p8-metrics

# A prova inteira: 12 testes, 27 min 05 s, todos passaram
uv run pytest -m integration tests/integration/test_lab_nuclei.py -v

# O que cada teste executa por baixo (pela CLI real, em subprocesso):
hdast stack up <produto>                                  # política da segunda cerca publicada
hdast probe <produto> [--only <operação>]                 # cria a pasta da execução
hdast nuclei <produto> --run <run_id>                     # a etapa, sozinha
hdast scan alvo-actuator --run <run_id> --only ping       # o ZAP, para o contraste do aceite 2
hdast run alvo-actuator --no-authz --no-negative          # a etapa dentro do run
hdast stack down
```

Os testes de apoio chamam em processo o mesmo caso de uso e o mesmo motor da CLI (`build_nuclei`, `DockerNucleiEngine`) quando precisam de uma observação que o subprocesso não dá: o valor do token (nunca impresso), o contêiner no ar e o prazo curto. Gates: `ruff check`, `ruff format --check`, `mypy`, `lint-imports` e `vulture` passaram; a suíte unitária e de contrato está no resumo ao fim do commit final.

## Resultado por aceite

### Aceite 2: cada motor só alcança a própria cerca

| Medida | Resultado |
| --- | --- |
| Pedidos na auditoria da `scope-proxy-nuclei` durante o `hdast nuclei` (alvo Spring) | 10.024 linhas |
| Linhas na auditoria da cerca do ZAP durante o mesmo `hdast nuclei` | **0** |
| Linhas na auditoria da cerca do ZAP durante o `scan` do ZAP (uma operação) | 384 |
| Linhas na auditoria da `scope-proxy-nuclei` durante esse `scan` | **0** |
| Redes do contêiner do Nuclei (14 amostras de `docker inspect`) | só `*_zap_net` (interna), em todas |
| Destino do proxy no contêiner | `-proxy http://scope-proxy-nuclei:3128` em todas as amostras; nenhuma variável de ambiente com `proxy` |
| Endurecimento do contêiner | `CapDrop: ALL`, `ReadonlyRootfs: true` em todas as amostras |

**Resultado: passou.** Limite: o ZAP e o `scope-proxy-nuclei` ficam os dois na `zap_net`, então a separação do ZAP é de **configuração** (o ZAP aponta para a cerca de hoje, e o contrato do `compose.yaml` confere), não de rede. A prova de laboratório mostra o efeito, não a impossibilidade: o ZAP gerou tráfego só numa cerca e o Nuclei só na outra.

### Aceite 3: o alvo Spring rende os achados do Actuator sem seleção manual

Etapa `nuclei` sozinha, perfil com `nuclei_wide_paths`, sem lista de modelos do teste: o domínio escolheu **8.476** modelos (de 14.101 no manifesto; exclusões por motivo no `nuclei.json`).

| Medida | Resultado |
| --- | --- |
| Achados (`nuclei.json`) | **14**: 9 baixos e 5 informativos |
| Achados de exposição do Actuator (`springboot-*`) | **11**: `env`, `configprops`, `beans`, `mappings`, `threaddump`, `loggers`, `metrics`, `caches`, `conditions` (baixos), `health` e `scheduledtasks` (informativos) |
| Outros achados | `aws-api-key` (a chave de exemplo da AWS da página inicial, sintética), `http-missing-security-headers` e `options-method`, informativos |
| Tecnologias identificadas (não são achados) | `springboot-actuator` e `spring-detect` |
| Achado com severidade média ou maior | 0 |
| Cada achado tem uma linha liberada na auditoria com o mesmo método e caminho | sim, 14 de 14 |
| Linhas da auditoria | 10.024: 9.792 liberadas, 232 negadas |
| Origens das linhas liberadas | só `alvo-actuator:8080` (http) |
| Tentativas fora dessa origem | 23 linhas, **todas negadas** (hosts `interact.sh`, `localhost`, `www.rdap.net`, subdomínios aleatórios `.tld` e `.com` e outras portas do próprio alvo), motivos `host_not_allowed` e `origin_not_allowed` |
| Tentativas em `scope.deny_paths` | 1 (`/actuator/heapdump`), **negada** (`deny_path`); 0 liberadas |
| Motivos de negação (duas execuções seguidas, 20.052 linhas) | `malformed_request` 416 (caminhos que a cerca recusa pela forma, na própria origem), `host_not_allowed` 20, `origin_not_allowed` 26, `deny_path` 2 |

**Resultado: passou, com uma ressalva de contagem.** O aceite pede "pelo menos os 13 achados do Actuator". Os 13 do spike eram 13 **detecções**. Pela regra do próprio ADR, o que é só identificação de tecnologia vai para "Tecnologias identificadas" e não vira achado. Medido agora:

- 11 das 13 viram achado;
- `springboot-actuator` vira tecnologia identificada (esperado pela regra);
- o 13º do spike, `springboot-whitelabel`, **não foi detectado**. Em seu lugar apareceu a tecnologia `spring-detect`. O modelo `springboot-whitelabel` procura `<h1>Whitelabel Error Page</h1>` em `GET /` com `Accept: text/html`, e o alvo desta prova devolve texto simples na raiz. Não isolei por que o spike o detectou; a hipótese (o alvo do spike respondia diferente) não foi verificada.
- Lido ao pé da letra, há 14 achados no total (mais que 13), mas só 11 são do Actuator.

O teste asserta os 11 achados, a tecnologia e o total de 13 ou mais, e registra a diferença. Decisão para o dono: ou o aceite passa a dizer "11 achados e 2 tecnologias", ou o alvo e o modelo são ajustados. Não mudei o ADR.

### Aceite 4: sem permissão de escrita, nenhuma escrita passa a cerca

| Medida | Resultado |
| --- | --- |
| Métodos das linhas **liberadas** na etapa (10.024 linhas) | só `GET`, `HEAD` e `OPTIONS` |
| Linhas `CONNECT` | todas negadas (o alvo é `http`; eram túneis para portas e hosts fora da origem) |
| Prova forçada da cerca: 30 modelos do catálogo com `POST`, sem veto, enviados pelo motor (fora da escolha do domínio) à `scope-proxy-nuclei` | 21 pedidos de escrita chegaram à cerca, 21 negados (`method_not_allowed`), **0 liberados**; método visto: `POST` |
| Etapa com login (Clínica Piloto) | só métodos de leitura liberados na `scope-proxy-nuclei` |

**Resultado: passou.** Limites: a prova forçada só viu `POST` (os 30 primeiros modelos de escrita do manifesto por ordem alfabética não usaram `PUT`, `PATCH` nem `DELETE`); `PUT`, `PATCH` e `DELETE` ficam cobertos pelos testes unitários da cerca, não por esta prova.

### Aceite 5: login por `-sf`, token fora de tudo

Clínica Piloto, conta sintética `admin_a` sorteada para a rodada, `extra_checks.nuclei_login` ligado. O valor do token foi obtido pelo próprio teste (o gravador do `-sf` é espiado em memória) e **nunca impresso**. As buscas usaram o valor do cabeçalho, o token e cada trecho do JWT com 16 caracteres ou mais.

| Onde procurei | Amostras ou arquivos | Ocorrências |
| --- | --- | --- |
| `docker inspect` do contêiner do Nuclei, durante a execução | 774 amostras | **0** |
| `docker top` do contêiner | 773 amostras | **0** |
| Lista de processos do host (`ps -eww`, inclui os do contêiner) | 774 amostras | **0** |
| Logs de todos os contêineres das duas pilhas (cercas, ZAP, pontes e a Clínica Piloto) | 6 contêineres | **0** |
| Arquivos da execução (`nuclei.json`, auditoria da CLI, `report.html`, `report.md`, saída e erro do processo) | a pasta de execuções inteira | **0** |
| Arquivos de estado da pilha (inclui as duas auditorias das cercas) | a pasta de estado inteira | **0** |
| O arquivo `-sf` | gravado, usado e **apagado** (arquivo e pasta privada) ao fim de `execute` | sumiu |
| Após falha forçada do motor (erro injetado depois de o arquivo ser gravado) | uma execução | arquivo e pasta sumiram |

`docker inspect` mostra `-sf /hdast/secrets.yaml` (só o caminho no contêiner) e a montagem do arquivo (só o caminho no host): é o esperado. A etapa durou 206,2 s, com login de `admin_a` e 1 achado.

**Resultado: passou.** Ressalvas de medição, no mesmo espírito do spike:
- O arquivo foi gravado com modo `0444` e dono do usuário do Codespace (uid 1000), dentro de uma pasta privada `0700` em `/dev/shm` (tmpfs). O modo `0400` com dono 10002 só vale com privilégio para trocar o dono, que o Codespace não dá a um usuário comum. É o caminho de contingência que o adaptador já documenta.
- As amostras do `ps` e do `docker inspect` são periódicas (a cada 0,15 s): não provam a ausência entre amostras, só em 774 instantes. O token nunca vai ao argumento por construção.
- A falha forçada é um erro **injetado** no motor (`patch.object`), não uma queda real do contêiner depois do login. Um prazo estourado de verdade com login não foi medido.

### Aceite 6: o prazo derruba o contêiner; entrada padrão fechada

| Medida | Resultado |
| --- | --- |
| Motor direto, 300 modelos a `-rl 1`, prazo de 4 s | `ExternalToolError` após **4,2 s**; o contêiner não existe mais (`docker ps -a`) |
| Entrada padrão do processo `docker compose run` (28 amostras, lido de `/proc/<pid>/fd/0`) | sempre `/dev/null` |
| Flags do contêiner (14 amostras) | `OpenStdin`, `StdinOnce` e `AttachStdin` verdadeiros: é o `compose run` ligando o contêiner à entrada do processo do Docker, que é `/dev/null`; sem terminal (`Tty: false`) |
| Prazo do perfil de ponta a ponta (1 pedido por segundo, `max_duration_minutes: 1`), CLI real, **antes da correção** | 60,8 s, saída 5, `EXTERNAL_TOOL_ERROR`, nenhum resultado parcial (**defeito**, abaixo) |
| O mesmo, **depois da correção** | 61,7 s, saída 3 (`SCOPE_VIOLATION`), `status: stopped_deadline`, `nuclei.json` gravado, nenhum contêiner restante |

**Resultado: passou, depois de corrigir o defeito.** A "entrada padrão fechada" foi medida no processo do Docker no host, não nas flags do contêiner (que ficam abertas por desenho do `compose run`).

### Segunda cerca desligada (perfil sem `extra_checks.nuclei`)

| Medida | Resultado |
| --- | --- |
| `stack status` | `running: true` |
| Saúde do contêiner `scope-proxy-nuclei` | `healthy` |
| Política publicada na pasta da segunda cerca | a que nega tudo (`deny-all.example`, `deny_paths: ["/**"]`) |
| `hdast nuclei` | recusado, cita `extra_checks.nuclei` |
| Motor forçado (60 modelos) contra o alvo, com a imagem já construída | 65 linhas na auditoria, **todas negadas**, nenhuma liberada |

**Resultado: passou.** Nesse caso o `stack up` não constrói a imagem do Nuclei (só constrói se o perfil a liga); a prova forçada usou a imagem construída numa rodada anterior da mesma sessão.

## Tempo da etapa em cada alvo

Etapa `nuclei` sozinha (`hdast nuclei`), 8.476 modelos, `-rl 50`, uma execução por alvo (sem repetição, então sem medida de variação):

| Alvo | Parede | Pedidos na auditoria (liberados + negados) | Achados | Observação |
| --- | ---: | ---: | ---: | --- |
| Alvo Spring (Actuator) | 215,7 s | 10.024 (9.792 + 232) | 14 | `nuclei_wide_paths` ligado |
| Alvo Spring, dentro do `hdast run` (`--no-authz --no-negative`) | 213,6 s a etapa; 230,4 s o `run` todo | n/a | 14 | estágio `nuclei` com `ok`, após o `scan` |
| Clínica Piloto, com login | 206,2 s | não medi | 1 | caminhos estritos, só leitura |
| VAmPI | 216,7 s | 10.031 (9.800 + 231) | 3 informativos | `nuclei_wide_paths` ligado |
| crAPI | 212,6 s | 10.020 (9.790 + 230) | 0 | `nuclei_wide_paths` ligado |
| Prazo curto (1 pedido/s, 1 min) | 61,7 s | n/a | 0 | parada pelo portão |

O ritmo medido é de uns 46 pedidos por segundo, perto do `-rl 50`. O spike media no máximo 10 s, mas com 321 modelos escolhidos pelo escopo do Swagger; o ADR escolhe agora pelos métodos e pelos vetos, não pelo escopo, e isso leva a uns 8,5 mil modelos e a mais de 200 s. Subida da pilha: 36 s (alvo Spring, com cache), 41,5 s (Clínica Piloto), 29,7 s (VAmPI), 111,1 s (crAPI); a primeira subida do dia, que construiu as imagens do Nuclei e do alvo, levou 136,8 s.

## Ruído: achados médios ou maiores falsos

| Alvo | Achados | Médios ou maiores | Detalhe |
| --- | ---: | ---: | --- |
| VAmPI | 3 | **0** | informativos: `http-missing-security-headers` (`/`), `openapi` (`/openapi.json`) e `options-method` (`/`); tecnologia `werkzeug-debugger-detect` |
| crAPI | 0 | **0** | nenhum, mesmo com o servidor respondendo 200 a muitos caminhos |
| Alvo Spring | 14 | **0** | 9 baixos e 5 informativos, todos verdadeiros no alvo que configurei |
| Clínica Piloto (com login) | 1 | **0** | informativo |

**Resultado: 0 achados médios ou maiores, falsos ou não, em todos os alvos.** Não auditei um a um os informativos do VAmPI; o `openapi` em `/openapi.json` é verdadeiro (o spike já o via), os outros dois descrevem comportamento observável da raiz. No crAPI, 16 linhas do JSONL do Nuclei não puderam ser projetadas (`malformed_lines: 16`; a saída bruta é descartada, então a causa não foi investigada). O VAmPI e o Spring tiveram 0.

## Defeito achado e corrigido

**Prazo do contêiner igual ao do portão.** `Nuclei._spec` usava `timeout_seconds = prazo do perfil − agora`, o mesmo instante em que o portão (`RunGate`) manda parar. Os dois estouravam juntos e o erro do runner vencia: o `hdast nuclei` saía com 5 (`EXTERNAL_TOOL_ERROR`) e **não gravava o resultado parcial**, ao contrário do que o caso de uso e o ADR dizem ("com parada antecipada (KILL, janela, prazo do perfil) o resultado parcial é devolvido e gravado"). Medido no laboratório: 60,8 s, saída 5.

Correção (commit `64af9815`): 15 s de folga (`NUCLEI_RUNNER_GRACE_SECONDS`) entre o portão e o prazo do contêiner, que passa a ser só a rede de segurança. Teste que o reproduz: `test_prazo_do_perfil_para_pelo_portao_e_devolve_o_parcial_antes_do_contêiner`, com um falso que mata o contêiner no próprio prazo como o runner real; falha com folga 0 e passa com 15. Dois testes de prazo existentes passaram a esperar a folga. Medido depois: saída 3, `stopped_deadline`, parcial gravado, em 61,7 s.

## Outras observações, sem correção

- **Escolha de modelos não conhece o escopo.** Rodam 8.476 modelos e a cerca nega 230 a 232 pedidos por execução, de modelos com endereços fixos fora do alvo (`interact.sh`, `localhost`, `www.rdap.net`, domínios aleatórios) e portas que o contrato não tem. É a cerca fazendo o papel dela, mas deixa ruído na auditoria e gasta pedidos. Os modelos com `interact.sh` fixo escapam do veto de OAST, que só olha a etiqueta; a cerca os nega e a rede interna não os alcançaria de qualquer jeito.
- **`lab_images` não cobre o Nuclei.** O modo pré-construído do laboratório (CI, `HDAST_IT_PREBUILT`) só prepara o ZAP, o proxy e a Clínica. O teste novo pula nesse modo, com mensagem, em vez de falhar; para entrar no CI, o modo precisa construir `hdast/nuclei` e `hdast-alvo-actuator`.
- **Arquivo `-sf` sem privilégio.** Já documentado no adaptador; medido: `0444` em pasta `0700` quando o dono não pode ser trocado.

## Limites da prova

- Uma execução por alvo, sem repetição: os tempos e as contagens não têm medida de variação (as duas rodadas completas do alvo Spring deram 10.024 linhas e 14 achados, iguais).
- O ganho em produto real **não** foi medido. O Actuator aberto é configuração minha, não um alvo independente.
- O contraste com o ZAP (aceite 2) é por contagem de linhas nas auditorias, não por captura de pacotes. Não houve `tcpdump`.
- Aceite 5: amostras periódicas, valor do token só com a conta sintética do laboratório, falha forçada por erro injetado e não por queda real. Não medi um prazo estourado com login nem o `hdast stop` (`KILL`) com o Nuclei no ar.
- Aceite 4: a prova forçada viu só `POST`; `PUT`, `PATCH` e `DELETE` ficam nos testes unitários.
- O aceite 7 (aprovações antigas e nova aprovação ao ligar as chaves) não era desta prova e não foi medido aqui.
- Não rodei o pacote de relatório do Nuclei (P5): usei `nuclei.json` e `run.json`. O `report.html` desta branch não traz a seção do Nuclei; só confirmei que ele não contém o token.
- Os informativos do VAmPI e do Spring não foram triados um a um.

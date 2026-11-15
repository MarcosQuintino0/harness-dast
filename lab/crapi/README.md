# crAPI no lab (terceiro alvo, **fora** do `hdast stack up`)

O [OWASP crAPI](https://github.com/OWASP/crAPI) (Completely Ridiculous API) é uma API deliberadamente vulnerável, de código aberto, com
microsserviços (identity em Java, community em Go, workshop em Python), MongoDB, PostgreSQL e um MailHog. Aqui ele serve de **terceiro
alvo** do lab e do caso de avaliação [`evals/cases/crapi`](../../evals/cases/crapi/case.yml).

> **Nunca exponha o crAPI além do localhost.** É vulnerável de propósito (SQL, NoSQL, SSRF, JWT fraco, BOLA). Este compose publica só duas
> portas, ambas em `127.0.0.1` (a API em `28888` e a interface do e-mail em `28025`), e os serviços ficam numa rede **interna** do Docker
> (sem rota para fora), de modo que nem o SSRF do alvo sai da máquina. Não troque para `0.0.0.0` nem use `--network host`.

## O que está aqui

| Arquivo | Conteúdo |
| --- | --- |
| [`compose.yaml`](compose.yaml) | Adaptação do `deploy/docker/docker-compose.yml` do crAPI `v1.1.6-rc8`: imagens fixadas por **digest**, limites de memória e CPU, `no-new-privileges`, bancos só na rede interna, sem segredos de e-mail reais (o SMTP aponta para o MailHog local) |
| [`openapi.json`](openapi.json) | OpenAPI oficial (`openapi-spec/crapi-openapi-spec.json`, tag `v1.1.6-rc8`), com **uma** alteração (abaixo) |
| [`LICENSE-crAPI.txt`](LICENSE-crAPI.txt) | Apache License 2.0 do projeto |
| [`seed.py`](seed.py) | Cadastra contas sintéticas (com veículo) e grava as variáveis do perfil num arquivo fora do repositório |
| [`product-profile/`](product-profile/target.yml) | Perfil do produto (`target.yml`, `data-rules.yml`, `flows.yml`) |

**Licença e origem.** O repositório do crAPI é Apache-2.0 (confira `LICENSE.md` na tag), que permite redistribuir com o aviso de origem: por
isso o OpenAPI está versionado aqui, em vez de baixado no setup. Copyright dos autores do crAPI (OWASP crAPI contributors). A licença do
**harness-dast** continua indefinida (P-14); este diretório não declara licença para o projeto.

**Alteração no OpenAPI.** A resposta `200` de `GET /workshop/api/shop/return_qr_code` tem a chave de tipo de mídia vazia (`"content": {"": {...}}`).
O leitor de OpenAPI do `hdast` recusa isso com um ponteiro claro (`operação inválida (media_type)`); a cópia daqui troca a chave vazia por
`image/png`, a imagem que a operação devolve. Nada mais mudou. Ao atualizar o arquivo, refaça essa troca.

**Imagens.** A tag `1.1.6-rc8` é a única que existe para **todas** as imagens do crAPI no Docker Hub (a pasta `VERSION` do repositório diz
`1.1.5`, que não foi publicada; a `1.1.6` só existe para o identity). Digests lidos no `docker pull` de 2026-11-13. O `postgres:14` e o
`mongo:4.4` também estão fixados por digest. O chatbot (`crapi-chatbot`) fica de pé sem chave de LLM, só porque o nginx do `crapi-web` o resolve
ao iniciar.

## Subir e parar

O crAPI **não** entra no `hdast stack up` porque `application/lab_targets.py` só sabe subir o VAmPI e a Clínica Piloto, e acrescentar um alvo
ali exigiria mudar o contrato (todo alvo traz variável de modo vulnerável e variáveis de credencial que a pilha sorteia; o crAPI não tem modo
seguro e as contas precisam ser **cadastradas** pela API, com o e-mail do MailHog). A saída é usar a pilha do `hdast` **sem alvo** e ligar o
crAPI à rede dela. A ordem importa: a rede `hdast_lab_net` é criada pela pilha.

```bash
# 1. Pasta de produtos com o perfil e o OpenAPI (fora do repositório)
mkdir -p /tmp/produtos/crapi
cp lab/crapi/product-profile/*.yml lab/crapi/openapi.json /tmp/produtos/crapi/
export HDAST_PRODUCTS_DIR=/tmp/produtos

# 2. Pilha do hdast SEM alvo (o host `crapi` não é um alvo conhecido: sobem só o ZAP e o proxy de escopo)
uv run hdast --json stack up crapi                          # ~30 s; gera a política do proxy a partir do perfil

# 3. crAPI na rede interna da pilha (qualquer valor serve de senha de banco; é do laboratório)
export CRAPI_DB_PASSWORD="$(openssl rand -hex 12)"
docker compose -p hdast-crapi -f lab/crapi/compose.yaml up -d --wait     # ~95 s

# 4. Contas de teste (sintéticas, sorteadas) e variáveis do perfil
python lab/crapi/seed.py --out /tmp/crapi-contas.json       # 2 contas, cada uma com veículo; não imprime os valores
# exporte CRAPI_USER_A_EMAIL, CRAPI_USER_A_PASSWORD, CRAPI_USER_B_EMAIL e CRAPI_USER_B_PASSWORD a partir do arquivo

# 5. Sondar e varrer
uv run hdast --json preflight crapi
uv run hdast --json probe crapi
uv run hdast --json run crapi

# 6. Parar (o crAPI primeiro; a pilha depois, senão a rede do lab fica em uso)
docker compose -p hdast-crapi -f lab/crapi/compose.yaml down -v
uv run hdast --json stack down
```

`seed.py --use <json>` cadastra as contas com valores **já sorteados** (é o que a avaliação cega faz com `sealed/secrets.json`).
O seed fala só com `127.0.0.1` e recusa qualquer outro endereço. Ele é de quem opera o lab; o agente nunca o roda.

## O perfil (`product-profile/`)

- **Escopo estreito:** só `crapi:80`, caminhos `/identity/api/**`, `/community/api/**` e `/workshop/api/**`, métodos `GET`, `POST`, `PUT`.
  `DELETE` e `PATCH` ficam de fora.
- **Negados** (`scope.deny_paths`): o que envia e-mail (`forget-password`, `check-otp` v2 e v3, `change-email`, `verify-email-token`, `resend_email`),
  troca a senha da conta logada (`reset-password`), cria contas (`signup`, `mechanic/signup`) ou faz o servidor chamar uma URL escolhida por
  quem chama (`merchant/contact_mechanic`, o SSRF do projeto). `reset-password` entrou depois do primeiro `probe`: ele trocou a senha de
  `user_a` e o login seguinte foi recusado.
- **Limites do lab:** 50 req/s e 8 threads (o teto da ferramenta, como os outros perfis do lab, com autorização do dono do lab). As avaliações
  usam os limites da carta (20 req/s, 4 threads).
- **Contas:** `user_a` e `user_b`, por `secret_ref` (`CRAPI_USER_*_EMAIL`, `CRAPI_USER_*_PASSWORD`); o login é `POST /identity/api/auth/login`
  com `{"email","password"}` e o token vem em `token`.
- `data-rules.yml` e `flows.yml` dão ao `probe` os ids de veículo, de pedido e do relatório de mecânico, e os cupons que o próprio crAPI semeia.

## Resultado medido (2026-11-13)

Máquina: Windows 11, Docker Desktop com 6,7 GiB, ZAP 2.17, proxy de escopo, `hdast` desta árvore.

| Item | Medida |
| --- | --- |
| Subida do crAPI (`up --wait`, imagens já puxadas) | ~95 s |
| Memória do crAPI parado | ~930 MiB (identity ~360, mongodb ~180, chatbot ~105, workshop ~90, postgres ~140, o resto <30) |
| Memória do lab inteiro durante o `run` (crAPI + ZAP + proxy + pontes), soma de `docker stats` a cada 15 s | pico **2,5 GiB** (de 6,7 GiB); só o crAPI: ~0,9 GiB parado |
| `preflight` | ok (login das duas contas) |
| `probe` | 44 operações; 30 tentadas; 18 com sucesso (0,60 das tentadas); 10 puladas por `deny_paths`; 2 `DELETE` fora do escopo |

O que **não** chega a sucesso, e por quê: o `login` do OpenAPI usa credenciais geradas (recusa por desenho); as duas operações de envio de
arquivo são `multipart/form-data`, que o `probe` alcança com um arquivo sintético quando o tipo é
aceito (V1.5, ADR 0052; vídeo e imagem de verdade ficam de fora); estas medições são anteriores a isso; `add_vehicle` precisa do VIN e do PIN que só chegam por e-mail; `login-with-token`
e `convert_video` e `users/all` pedem papel que as contas não têm; `get_post` e `post_comment` ficariam alcançáveis com o id de um post, mas o
OpenAPI diz que a lista de posts é um array e o alvo devolve `{"posts": [...]}`, e o `flows.yml` é conferido contra o OpenAPI.

### O que o ZAP achou (`hdast run crapi`, 906 s, limites do lab)

41 achados: **1 alto**, 6 médios, 34 baixos, 2 informativos. O alto é `Path Traversal` em `PUT /workshop/api/shop/orders/{order_id}`
(parâmetro `quantity`), provável **falso positivo** (não é uma falha do crAPI). Os médios são `Cross-Domain Misconfiguration` em
`/community/api/**`; o resto é cabeçalho ausente, `Server` com versão, divulgação de erro e comentários suspeitos. Nenhum dos 15
desafios do crAPI foi achado, nem o de SQL (`apply_coupon`), que o gabarito previa detectável e que a medição desmentiu.

## Limites e riscos

- O `stack down` não derruba o crAPI nem a rede `hdast_lab_net` enquanto o `crapi-web` estiver ligado a ela: derrube o crAPI antes.
- Tag de pré-lançamento (`rc8`). Trocar de versão exige refazer os digests e conferir o OpenAPI (o crAPI mudou de rotas entre versões).
- O `mailhog` guarda os e-mails no MongoDB do lab: `down -v` apaga tudo.
- Memória: com ZAP (até 1,6 GiB na configuração do lab) o conjunto passa de ~2,1 GiB e cabe nos 6,7 GiB do Docker, mas **não** em paralelo
  com o Oracle do piloto (2 GiB) e o ZAP: não suba os três juntos.

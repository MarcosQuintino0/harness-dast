# Primeiro uso: do zero até a primeira varredura no laboratório

Objetivo: instalar, subir o laboratório (VAmPI, uma API vulnerável de propósito, só na sua máquina), rodar uma varredura e ler o relatório. Leva cerca de 30 minutos, quase todos esperando a varredura. Os exemplos usam PowerShell no Windows; no Git Bash, troque `$env:X = "v"` por `export X=v`.

> Só o laboratório local. Para um produto de verdade, veja [cadastrar-um-produto.md](cadastrar-um-produto.md) e leia o aviso de uso autorizado do [README](../../README.md).

## 1. Instalar

| Ferramenta | Como | Conferir |
| --- | --- | --- |
| Git | <https://git-scm.com> | `git --version` |
| uv (gerencia o Python e as dependências) | <https://docs.astral.sh/uv/> | `uv --version` |
| Docker Desktop | <https://www.docker.com/products/docker-desktop/>; abra-o e espere ficar "running" | `docker version` mostra Client e Server |

Reserve cerca de 4 GiB de memória para o Docker Desktop (o ZAP usa cerca de 1,5 GiB).

## 2. Clonar e preparar

```powershell
git clone <url-do-repositório> harness-dast
cd harness-dast
uv sync
uv run hdast --json version
```

Saída esperada do último comando (a versão pode mudar):

```json
{"schema_version":1,"ok":true,"data":{"version":"1.3.0"}}
```

## 2b. Primeiro passo: o `doctor`

```powershell
uv run hdast doctor
```

Confere Python, `uv`, Docker, imagens e as portas 8080 e 3128, sem tocar nenhum alvo e sem subir nada. Esperado: "Tudo pronto para começar." (aviso de imagem ausente é normal na primeira vez: o `stack up` as constrói). Cada `FALHA` diz o que fazer; corrija e rode de novo. Mais adiante, `hdast doctor vampi` confere também o perfil (veja 4b).

## 3. Copiar o perfil do laboratório

O perfil do VAmPI vem pronto em `lab/vampi/product-profile/`. A pasta do produto precisa ter o nome do produto (`vampi`).

```powershell
mkdir meus-produtos\vampi
copy lab\vampi\product-profile\*.yml meus-produtos\vampi\
copy lab\vampi\openapi3.yml meus-produtos\vampi\
$env:HDAST_PRODUCTS_DIR = "$PWD\meus-produtos"
uv run hdast --json profile validate vampi
```

Esperado: `"ok":true` e `"runnable":true`, com `issues` vazio. Se `runnable` for `false`, leia `issues` ([problemas-comuns.md](problemas-comuns.md)).

## 4. Definir as contas do laboratório

O VAmPI semeia usuários conhecidos (não são segredos reais). O perfil os lê por `secret_ref`:

```powershell
$env:VAMPI_USER_A_USERNAME = "name1";  $env:VAMPI_USER_A_PASSWORD = "pass1"
$env:VAMPI_USER_B_USERNAME = "name2";  $env:VAMPI_USER_B_PASSWORD = "pass2"
$env:VAMPI_ADMIN_USERNAME  = "admin";  $env:VAMPI_ADMIN_PASSWORD  = "pass1"
```

No dia a dia, com contas de um produto de verdade, prefira o cofre do sistema (você digita cada senha uma vez, sem ela aparecer na tela nem no histórico): troque `env:NOME` por `keyring:NOME` no `target.yml` e rode, num terminal seu, `uv run hdast secret set NOME` para cada nome. `uv run hdast secret list <produto>` mostra o que já existe. Para o VAmPI, de senhas públicas, as variáveis acima bastam.

## 4b. Conferir se está tudo pronto

```powershell
uv run hdast doctor vampi
```

O `doctor` com o produto não toca o alvo nem sobe nada: confere o mesmo do passo 2b e mais o perfil, a autorização, a janela e se os segredos das contas existem, em variável de ambiente ou no cofre (só diz se existem, nunca o valor; para o cofre, diz o comando `hdast secret set NOME`). Dois **avisos** (não reprovam) olham o perfil: `scope.path_mode: wide` (o modo amplo só é seguro com `deny_paths` completo) e a falta de duas contas do mesmo papel (sem elas, o teste de autorização horizontal não consegue comparar contas). Esperado: "Tudo pronto para começar." (avisos de imagem ausente são normais na primeira vez: o `stack up` as constrói). Cada `FALHA` diz o que fazer; corrija e rode de novo.

## 4c. Aprovar o perfil (uma vez)

```powershell
uv run hdast profile approve vampi
```

Os comandos que tocam o alvo (`stack up`, `preflight`, `probe`, `scan`, `run`) recusam com `SCOPE_NOT_APPROVED` enquanto uma **pessoa** não aprovar o escopo. Rode o comando acima num terminal seu: ele mostra o resumo (endereço, o que pode, o que é proibido, janela, limites, contas, política da varredura, teste de autorização, limpeza) e pede que você digite o nome do produto (`vampi`). Só você aprova: o agente nunca roda esse comando. `uv run hdast --json profile approval vampi` mostra o estado (`approved`, `not_approved` ou `changed`). Se você (ou o agente) editar depois qualquer campo de `environment`, `scope`, `limits`, contas, `scan`, `authz` ou `cleanup`, é preciso aprovar de novo; só `probe`, `auth.csrf`, `auth.account_map`, `auth.default_account`, `auth.token_expired`, a codificação do login e `openapi` não pedem. Quem atualizou o `hdast` da V1.3 antes desta correção precisa aprovar de novo: o cálculo mudou de versão e a aprovação antiga vale como não feita.

## 5. Subir a pilha

```powershell
uv run hdast stack up vampi
```

Leva cerca de 40 s na primeira vez (constrói imagens). Esperado: uma linha "Pilha ... (produto vampi, alvo vampi)" e os serviços `running`/`healthy`. A pilha tem o ZAP, o proxy de escopo e o VAmPI. Confira:

```powershell
uv run hdast --json stack status      # "running": true
```

## 6. Conferir e alcançar os endpoints

```powershell
uv run hdast --json preflight vampi   # "ready": true
uv run hdast --json probe vampi       # "reachability": 1.0
```

O `preflight` confere autorização, janela, segredos, ZAP, saúde do alvo e login de cada conta. O `probe` envia uma requisição válida por operação; alcançabilidade `1.0` significa que todas as operações tentadas tiveram sucesso. O `DELETE` não é tentado sem `--include-delete`.

## 7. Rodar a varredura

```powershell
uv run hdast run vampi
```

Leva cerca de 15 minutos. O `run` já inclui, depois da varredura, o teste de autorização entre contas (acesso a dado de outra conta, função de papel maior, dado a mais, resposta sem login e token adulterado aceito), só de leitura; `--no-authz` o pula e `--authz` ainda é aceito (não muda nada). Depois dele vem o estágio `negative` (valores que o esquema proíbe: o teste manda, um campo por vez, um valor que o Swagger não aceita, só em leitura, para ver se o sistema rejeita); `--no-negative` o pula, e a escrita só roda se a carta a permitir (`negative.allow_writes`). A comparação entre contas só acontece quando o perfil tem **duas contas do mesmo papel** (o VAmPI tem `user_a` e `user_b`); sem elas diz o que não pôde testar. A parte que escreve no alvo (atribuição em massa) só roda se a carta de autorização a permitir (`authz.allow_writes`), e o teste não roda com `--skip-scan`. Em outro terminal você pode acompanhar `runs\<run_id>\scan-progress.json`. Para parar com segurança: `uv run hdast stop`. Ao fim, o comando sai com `0` (nada acima do limiar), `1` (há achado no limiar, não é erro) ou outro código ([exit-codes.md](../reference/exit-codes.md)).

## 8. Ler o resultado

Tudo fica em `runs\<run_id>\` (o `run_id` aparece no fim do comando):

| Arquivo | Para quê |
| --- | --- |
| `run.json` | Estágios, código de saída, tempos, achados por severidade |
| `report.html` | O relatório numa página só (abra no navegador, funciona sem internet e em tema claro ou escuro): resumo, "o que fazer agora", achados por gravidade, o que não foi coberto, tráfego recusado |
| `report.md` | O mesmo relatório em Markdown, para quem corrige |
| `findings.json` | O mesmo, estruturado (cada achado e, em `groups`, os achados agrupados pela causa) |
| `panel/` | O painel da execução, em páginas HTML (abra `panel/summary.html` no navegador; sem internet e sem script): resumo, etapas, falhas, cobertura, terminal e tempo e tokens. Também sai de `hdast panel <produto>`; dado que falta aparece como "não medido" ([ADR 0032](../adr/0032-painel-da-execucao.md)) |
| `probe.json` | O que o `probe` enviou e como cada operação respondeu |
| `authz.json` | Teste de autorização entre contas (`hdast run`, salvo `--no-authz`, ou `hdast authz`). Veja [authz.md](../reference/authz.md) |
| `negative.json` | Teste de valores que o esquema proíbe (`hdast run`, salvo `--no-negative`, ou `hdast negative`). Veja [negative.md](../reference/negative.md) |
| `audit.jsonl` | Trilha de cada requisição da CLI |

Os achados com a mesma regra e o mesmo parâmetro aparecem **agrupados pela causa** (por exemplo, o mesmo cookie sem `HttpOnly` em 26 caminhos vira um grupo com a lista de onde aparece); nenhum achado some e nenhuma gravidade muda. Alguns grupos trazem uma nota fixa explicando por que o padrão costuma ser esperado (o cookie de XSRF por duplo envio, que o JavaScript precisa ler).

No `report.html` ou no `report.md`, **leia o que a varredura não testou**: autorização entre contas (BOLA, BFLA), atribuição em massa e exposição excessiva de dados estão fora do que uma varredura ativa do ZAP detecta. Um relatório sem achados **não** prova que a API é segura. Severidade e confiança são propostas; todo achado exige triagem humana.

Com o estágio `authz` (ligado por padrão no `hdast run`), parte dessas lacunas (acesso entre contas, campo a mais e dado a mais) passa a ser testada por um estágio próprio: veja [authz.md](../reference/authz.md).

## 9. Encerrar

```powershell
uv run hdast --json stack down
```

## 10. Um produto de verdade, com um pedido só

Depois do laboratório, para testar um produto real com o Claude Code você não precisa fazer quatro pedidos: abra o `claude` na raiz do repositório e peça uma vez, entregando o Swagger e a carta de autorização:

```text
Use a skill test-product no produto "<produto>". A pasta de produtos é <pasta>.
O OpenAPI está em <caminho>. A carta de autorização está em <caminho>.
É ambiente de teste com dados sintéticos e a autorização vale agora.
```

A skill `test-product` conduz o cadastro (`onboard-product`), a alcançabilidade (`fix-reachability`), a varredura (`run-scan`) e a triagem (`triage-findings`), e **só para quando precisa de você**: falta dado na carta (o agente faz uma entrevista de uma rodada só e monta um `carta.yml`), falta a sua aprovação do escopo (você roda um comando num terminal seu),  a alcançabilidade não chegou à meta depois das tentativas permitidas, há achado alto para você confirmar, ou qualquer dúvida de autorização, escopo ou janela. As travas não mudam: o agente só age por `hdast`, não lê segredo, não roda limpeza e não amplia escopo, limite nem janela. Detalhes e prompts por etapa: [cadastrar-um-produto.md](cadastrar-um-produto.md).

## Próximos passos

O próximo passo é o [cadastro de um produto](cadastrar-um-produto.md) com o Claude Code, ou repetir este guia com `uv run hdast stack up vampi --secure` para ver o modo seguro do laboratório.

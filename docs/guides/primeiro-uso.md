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
{"schema_version":1,"ok":true,"data":{"version":"0.1.0"}}
```

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

## 4b. Conferir se está tudo pronto

```powershell
uv run hdast doctor vampi
```

O `doctor` não toca o alvo nem sobe nada: confere Python, `uv`, Docker, imagens, as portas 8080 e 3128, o perfil, a autorização, a janela e se as variáveis das contas estão definidas (só diz se existem, nunca o valor). Esperado: "Tudo pronto para começar." (avisos de imagem ausente são normais na primeira vez: o `stack up` as constrói). Cada `FALHA` diz o que fazer; corrija e rode de novo.

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

Leva cerca de 15 minutos. Em outro terminal você pode acompanhar `runs\<run_id>\scan-progress.json`. Para parar com segurança: `uv run hdast stop`. Ao fim, o comando sai com `0` (nada acima do limiar), `1` (há achado no limiar, não é erro) ou outro código ([exit-codes.md](../reference/exit-codes.md)).

## 8. Ler o resultado

Tudo fica em `runs\<run_id>\` (o `run_id` aparece no fim do comando):

| Arquivo | Para quê |
| --- | --- |
| `run.json` | Estágios, código de saída, tempos, achados por severidade |
| `report.md` | O relatório, para quem corrige |
| `findings.json` | O mesmo, estruturado |
| `probe.json` | O que o `probe` enviou e como cada operação respondeu |
| `audit.jsonl` | Trilha de cada requisição da CLI |

No `report.md`, **comece pela seção "O que este relatório não testou"**: autorização entre contas (BOLA, BFLA), atribuição em massa e exposição excessiva de dados estão fora do que uma varredura ativa do ZAP detecta. Um relatório sem achados **não** prova que a API é segura. Severidade e confiança são propostas; todo achado exige triagem humana.

## 9. Encerrar

```powershell
uv run hdast --json stack down
```

Depois, o próximo passo é o [cadastro de um produto](cadastrar-um-produto.md) com o Claude Code, ou repetir este guia com `uv run hdast stack up vampi --secure` para ver o modo seguro do laboratório.

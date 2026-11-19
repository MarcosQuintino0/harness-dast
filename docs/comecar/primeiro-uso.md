# Primeiro uso com o VAmPI local

## Começar com `hdast demo`

Siga a [instalação da CLI](instalar.md) e [prepare as imagens da demo](docker.md#preparar-as-imagens-da-demo). Depois, rode o comando abaixo num terminal seu, na raiz do repositório.

```bash
uv run hdast demo
```

O comando confere o Docker, as imagens e as portas. Quando aparecer o resumo do VAmPI, digite `demo` para aprovar. Reserve cerca de cinco minutos mais a subida e a parada da pilha. Ao terminar, o comando mostra o caminho do `report.html`, se ele foi gerado, e oferece abri-lo no navegador. A pilha é desmontada automaticamente. O relatório fica na pasta temporária indicada na saída.

Use `uv run hdast demo --keep` para manter a pilha de pé. O comando mostra a pasta de estado que você usará para derrubá-la. [Referência da demo](../referencia/cli.md#hdast-demo)

Abra o relatório pelo caminho informado. Ele mostra [achados](../referencia/glossario.md#achado), sinais de possíveis problemas a revisar, e [lacunas de cobertura](../referencia/glossario.md#lacuna-de-cobertura), aquilo que ficou sem teste ou prova e por quê.

## Testar um produto com o agente

No dia a dia, abra o Claude Code na raiz do repositório e faça um pedido. Entregue o Swagger (a descrição da API) e a [carta](../referencia/glossario.md#carta), a autorização por escrito do dono do produto para testar naquele ambiente.

```text
Use a skill test-product no produto "<produto>". A pasta de produtos é <pasta>.
O OpenAPI está em <caminho>. A carta de autorização está em <caminho>.
É ambiente de teste com dados sintéticos e a autorização vale agora.
```

O agente conduz o cadastro e o teste pela CLI. Você aprova o escopo no seu terminal e revisa o relatório. Siga o [guia de cadastro](../usar/cadastrar-um-produto.md) e consulte [quando seguir com cobertura parcial e quando parar](../../plugin/skills/test-product/SKILL.md#se-der-x-faça-y-quando-parar-e-chamar-a-pessoa).

## Fazer passo a passo (opcional)

Os passos abaixo mostram as etapas individuais com o VAmPI local. Reserve cerca de 30 minutos. Os exemplos usam PowerShell no Windows. No Git Bash, troque `$env:X = "v"` por `export X=v`.

### 1. Instalar

Siga a [instalação da CLI](instalar.md) e [prepare o Docker e as imagens](docker.md#baixar-e-conferir-as-imagens). Rode `uv run hdast doctor` na raiz do repositório antes de copiar o perfil. Cada falha vem com a ação para corrigi-la.

### 2. Copiar o perfil do laboratório

O perfil do VAmPI vem pronto em `lab/vampi/product-profile/`. A pasta do produto precisa ter o nome do produto (`vampi`).

```powershell
mkdir meus-produtos\vampi
copy lab\vampi\product-profile\*.yml meus-produtos\vampi\
copy lab\vampi\openapi3.yml meus-produtos\vampi\
$env:HDAST_PRODUCTS_DIR = "$PWD\meus-produtos"
uv run hdast --json profile validate vampi
```

Esperado: `"ok":true` e `"runnable":true`, com `issues` vazio. Se `runnable` for `false`, leia `issues` ([problemas-comuns.md](../usar/problemas-comuns.md)).

### 3. Definir as contas do laboratório

O VAmPI semeia usuários conhecidos (não são segredos reais). O perfil os lê por `secret_ref`:

```powershell
$env:VAMPI_USER_A_USERNAME = "name1";  $env:VAMPI_USER_A_PASSWORD = "pass1"
$env:VAMPI_USER_B_USERNAME = "name2";  $env:VAMPI_USER_B_PASSWORD = "pass2"
$env:VAMPI_ADMIN_USERNAME  = "admin";  $env:VAMPI_ADMIN_PASSWORD  = "pass1"
```

No dia a dia, com contas de um produto de verdade, prefira o cofre do sistema (você digita cada senha uma vez, sem ela aparecer na tela nem no histórico): troque `env:NOME` por `keyring:NOME` no `target.yml` e rode, num terminal seu, `uv run hdast secret set NOME` para cada nome. `uv run hdast secret list <produto>` mostra o que já existe. Para o VAmPI, de senhas públicas, as variáveis acima bastam.

### 4. Conferir se está tudo pronto

```powershell
uv run hdast doctor vampi
```

Com o nome do produto, o `doctor` confere também o perfil, a autorização, a janela e a presença dos segredos das contas no ambiente ou no cofre. O modo amplo de caminho e a falta de duas contas do mesmo papel aparecem como avisos. Esperado: "Tudo pronto para começar."

### 5. Aprovar o perfil

```powershell
uv run hdast profile approve vampi
```

Rode o comando acima num terminal seu, confira o resumo e digite `vampi` para aprovar. A [cerca de escopo](../referencia/glossario.md#cerca-de-escopo) só deixa passar requisições permitidas. Sem aprovação válida, a CLI recusa o teste com `SCOPE_NOT_APPROVED`. Após alterações no perfil, confira o estado conforme o [guia de cadastro](../usar/cadastrar-um-produto.md#5-a-entrevista-e-a-aprovação-do-escopo).

### 6. Subir a pilha

```powershell
uv run hdast stack up vampi
```

Na primeira vez, o Docker pode baixar as imagens auxiliares e do VAmPI. Espere uma linha "Pilha ... (produto vampi, alvo vampi)" e os serviços `running`/`healthy`. Confira com o comando abaixo.

```powershell
uv run hdast --json stack status      # "running": true
```

### 7. Conferir o alcance da API

```powershell
uv run hdast --json preflight vampi   # "ready": true
uv run hdast --json probe vampi       # "reachability": 1.0
```

O `preflight` confere autorização, janela, segredos, ZAP, saúde do alvo e login de cada conta. O `probe` verifica se consegue usar cada operação da API, isto é, uma ação definida por método e caminho. Uma [operação alcançada](../referencia/glossario.md#operação-alcançada) teve sucesso ou retornou a recusa de login esperada (`auth_rejected_expected`). O [alcance](../referencia/glossario.md#alcance) (*reachability*) é a proporção de operações alcançadas entre as tentadas. `1.0` significa que todas as tentadas foram alcançadas. O `DELETE` não é tentado sem `--include-delete`.

### 8. Rodar a varredura

```powershell
uv run hdast run vampi
```

Leva cerca de 15 minutos. Uma [operação varrida](../referencia/glossario.md#operação-varrida) é uma operação que o ZAP chegou a testar.

Depois da varredura, o `run` verifica a autorização entre contas em modo de leitura. Os testes incluem [BOLA](../referencia/glossario.md#bola), quando uma conta consegue acessar um recurso que pertence a outra, e [BFLA](../referencia/glossario.md#bfla), quando uma conta consegue usar uma função proibida para seu papel. A comparação de acesso a recursos só acontece com **duas contas do mesmo papel** (o VAmPI tem `user_a` e `user_b`). A escrita, como o teste de [atribuição em massa](../referencia/glossario.md#atribuição-em-massa) (a API grava campos que a conta não deveria poder alterar), só roda se a carta autorizar (`authz.allow_writes`). `--no-authz` pula o estágio, `--authz` ainda é aceito e o estágio é pulado com `--skip-scan`.

Em seguida, `negative` verifica se a API rejeita valores proibidos pelo Swagger. Vem em modo de leitura, aceita `--no-negative` para pular e só escreve se a carta permitir (`negative.allow_writes`).

Acompanhe em outro terminal pelo arquivo `runs\<run_id>\scan-progress.json`. Para parar com segurança, use `uv run hdast stop`. Ao fim, o código `0` indica que não houve achado acima do limiar, e `1` indica que houve achado no limiar. [Códigos de saída](../referencia/exit-codes.md).

### 9. Ler o resultado

Tudo fica em `runs\<run_id>\` (o `run_id` aparece no fim do comando):

| Arquivo | Para quê |
| --- | --- |
| `run.json` | Estágios, código de saída, tempos, achados por severidade |
| `report.html` | O relatório numa página só (abra no navegador, funciona sem internet e em tema claro ou escuro): resumo, "o que fazer agora", achados por gravidade, o que não foi coberto, tráfego recusado |
| `report.md` | O mesmo relatório em Markdown, para quem corrige |
| `findings.json` | O mesmo, estruturado (cada achado e, em `groups`, os achados agrupados pela causa) |
| `panel/` | O painel da execução, em páginas HTML (abra `panel/summary.html` no navegador; sem internet e sem script): resumo, etapas, falhas, cobertura, terminal e tempo e tokens. Também sai de `hdast panel <produto>`; dado que falta aparece como "não medido" ([ADR 0032](../decisoes/0032-painel-da-execucao.md)) |
| `probe.json` | O que o `probe` enviou e como cada operação respondeu |
| `authz.json` | Teste de autorização entre contas (`hdast run`, salvo `--no-authz`, ou `hdast authz`). Veja [authz.md](../referencia/authz.md) |
| `negative.json` | Teste de valores que o esquema proíbe (`hdast run`, salvo `--no-negative`, ou `hdast negative`). Veja [negative.md](../referencia/negative.md) |
| `audit.jsonl` | Trilha de cada requisição da CLI |

Os achados com a mesma regra e o mesmo parâmetro aparecem **agrupados pela causa** (por exemplo, o mesmo cookie sem `HttpOnly` em 26 caminhos vira um grupo com a lista de onde aparece); nenhum achado some e nenhuma gravidade muda. Alguns grupos trazem uma nota fixa explicando por que o padrão costuma ser esperado (o cookie de XSRF por duplo envio, que o JavaScript precisa ler).

No `report.html` ou no `report.md`, confira as lacunas de cobertura. O estágio [`authz`](../referencia/authz.md) cobre parte das verificações de autorização e exposição de dados. Revise os achados e a evidência de cada um.

### 10. Encerrar

```powershell
uv run hdast --json stack down
```

Você também pode repetir o roteiro manual com `uv run hdast stack up vampi --secure` na etapa 6 para ver o modo seguro do laboratório.

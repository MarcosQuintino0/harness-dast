# Primeiro uso com o VAmPI local

Siga a [instalação da CLI](instalar.md) e [prepare as imagens da demo](docker.md#preparar-as-imagens-da-demo). Depois, rode o comando abaixo num terminal seu, na raiz do repositório.

```bash
uv run hdast demo
```

O comando confere o Docker, as imagens e as portas. Quando aparecer o resumo do VAmPI, digite `demo` para aprovar. Reserve cerca de cinco minutos mais a subida e a parada da pilha. Ao terminar, o comando mostra o caminho do `report.html`, se ele foi gerado, e oferece abri-lo no navegador. A pilha é desmontada automaticamente. O relatório fica na pasta temporária indicada na saída.

Use `uv run hdast demo --keep` para manter a pilha de pé. O comando mostra a pasta de estado que você usará para derrubá-la. [Referência da demo](../referencia/cli.md#hdast-demo)

Para cadastrar um produto real, siga o [guia de cadastro](../usar/cadastrar-um-produto.md) e o aviso de uso autorizado do [README](../../README.md).

## Roteiro manual do laboratório

Os passos abaixo mostram as etapas individuais com o VAmPI local. Reserve cerca de 30 minutos. Os exemplos usam PowerShell no Windows. No Git Bash, troque `$env:X = "v"` por `export X=v`.

## 1. Instalar

Siga a [instalação da CLI](instalar.md) e [prepare o Docker e as imagens](docker.md#baixar-e-conferir-as-imagens). Rode `uv run hdast doctor` na raiz do repositório antes de copiar o perfil. Cada falha vem com a ação para corrigi-la.

## 2. Copiar o perfil do laboratório

O perfil do VAmPI vem pronto em `lab/vampi/product-profile/`. A pasta do produto precisa ter o nome do produto (`vampi`).

```powershell
mkdir meus-produtos\vampi
copy lab\vampi\product-profile\*.yml meus-produtos\vampi\
copy lab\vampi\openapi3.yml meus-produtos\vampi\
$env:HDAST_PRODUCTS_DIR = "$PWD\meus-produtos"
uv run hdast --json profile validate vampi
```

Esperado: `"ok":true` e `"runnable":true`, com `issues` vazio. Se `runnable` for `false`, leia `issues` ([problemas-comuns.md](../usar/problemas-comuns.md)).

## 3. Definir as contas do laboratório

O VAmPI semeia usuários conhecidos (não são segredos reais). O perfil os lê por `secret_ref`:

```powershell
$env:VAMPI_USER_A_USERNAME = "name1";  $env:VAMPI_USER_A_PASSWORD = "pass1"
$env:VAMPI_USER_B_USERNAME = "name2";  $env:VAMPI_USER_B_PASSWORD = "pass2"
$env:VAMPI_ADMIN_USERNAME  = "admin";  $env:VAMPI_ADMIN_PASSWORD  = "pass1"
```

No dia a dia, com contas de um produto de verdade, prefira o cofre do sistema (você digita cada senha uma vez, sem ela aparecer na tela nem no histórico): troque `env:NOME` por `keyring:NOME` no `target.yml` e rode, num terminal seu, `uv run hdast secret set NOME` para cada nome. `uv run hdast secret list <produto>` mostra o que já existe. Para o VAmPI, de senhas públicas, as variáveis acima bastam.

## 4. Conferir se está tudo pronto

```powershell
uv run hdast doctor vampi
```

Com o nome do produto, o `doctor` confere também o perfil, a autorização, a janela e a presença dos segredos das contas no ambiente ou no cofre. O modo amplo de caminho e a falta de duas contas do mesmo papel aparecem como avisos. Esperado: "Tudo pronto para começar."

## 4b. Aprovar o perfil (uma vez)

```powershell
uv run hdast profile approve vampi
```

Os comandos que tocam o alvo (`stack up`, `preflight`, `probe`, `scan`, `run`) recusam com `SCOPE_NOT_APPROVED` enquanto uma **pessoa** não aprovar o escopo. Rode o comando acima num terminal seu: ele mostra o resumo (endereço, o que pode, o que é proibido, janela, limites, contas, política da varredura, teste de autorização, limpeza) e pede que você digite o nome do produto (`vampi`). Só você aprova: o agente nunca roda esse comando. `uv run hdast --json profile approval vampi` mostra o estado (`approved`, `not_approved` ou `changed`). Se você (ou o agente) editar depois qualquer campo de `environment`, `scope`, `limits`, contas, `scan`, `authz` ou `cleanup`, é preciso aprovar de novo; só `probe`, `auth.csrf`, `auth.account_map`, `auth.default_account`, `auth.token_expired`, a codificação do login e `openapi` não pedem. Quem atualizou o `hdast` da V1.3 antes desta correção precisa aprovar de novo: o cálculo mudou de versão e a aprovação antiga vale como não feita.

## 5. Subir a pilha

```powershell
uv run hdast stack up vampi
```

Na primeira vez, o Docker pode baixar as imagens auxiliares e do VAmPI. Espere uma linha "Pilha ... (produto vampi, alvo vampi)" e os serviços `running`/`healthy`. Confira com o comando abaixo.

```powershell
uv run hdast --json stack status      # "running": true
```

## 6. Conferir e alcançar os endpoints

```powershell
uv run hdast --json preflight vampi   # "ready": true
uv run hdast --json probe vampi       # "reachability": 1.0
```

O `preflight` confere autorização, janela, segredos, ZAP, saúde do alvo e login de cada conta. O `probe` envia uma requisição válida por operação; alcançabilidade `1.0` significa que todas as operações tentadas foram alcançadas, incluindo eventual `auth_rejected_expected`, separado dos sucessos 2xx. O `DELETE` não é tentado sem `--include-delete`.

## 7. Rodar a varredura

```powershell
uv run hdast run vampi
```

Leva cerca de 15 minutos. O `run` já inclui, depois da varredura, o teste de autorização entre contas (acesso a dado de outra conta, função de papel maior, dado a mais, resposta sem login e token adulterado aceito), só de leitura; `--no-authz` o pula e `--authz` ainda é aceito (não muda nada). Depois dele vem o estágio `negative` (valores que o esquema proíbe: o teste manda, um campo por vez, um valor que o Swagger não aceita, só em leitura, para ver se o sistema rejeita); `--no-negative` o pula, e a escrita só roda se a carta a permitir (`negative.allow_writes`). A comparação entre contas só acontece quando o perfil tem **duas contas do mesmo papel** (o VAmPI tem `user_a` e `user_b`); sem elas diz o que não pôde testar. A parte que escreve no alvo (atribuição em massa) só roda se a carta de autorização a permitir (`authz.allow_writes`), e o teste não roda com `--skip-scan`. Em outro terminal você pode acompanhar `runs\<run_id>\scan-progress.json`. Para parar com segurança: `uv run hdast stop`. Ao fim, o comando sai com `0` (nada acima do limiar), `1` (há achado no limiar, não é erro) ou outro código ([exit-codes.md](../referencia/exit-codes.md)).

## 8. Ler o resultado

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

No `report.html` ou no `report.md`, **leia o que a varredura não testou**: autorização entre contas (BOLA, BFLA), atribuição em massa e exposição excessiva de dados estão fora do que uma varredura ativa do ZAP detecta. Um relatório sem achados **não** prova que a API é segura. Severidade e confiança são propostas; todo achado exige triagem humana.

Com o estágio `authz` (ligado por padrão no `hdast run`), parte dessas lacunas (acesso entre contas, campo a mais e dado a mais) passa a ser testada por um estágio próprio: veja [authz.md](../referencia/authz.md).

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

A skill `test-product` conduz o cadastro (`onboard-product`), a alcançabilidade (`fix-reachability`), a varredura (`run-scan`) e a triagem (`triage-findings`), e **só para quando precisa de você**: falta dado na carta (o agente faz uma entrevista de uma rodada só e monta um `carta.yml`), falta a sua aprovação do escopo (você roda um comando num terminal seu), há achado alto para você confirmar, ou qualquer dúvida de autorização, escopo ou janela. Se a meta de alcance não for atingida após as tentativas ou duas rodadas sem melhora, segue com cobertura parcial e registra operações e motivos do último `probe` no diário, relatório e resposta final. As travas não mudam: o agente só age por `hdast`, não lê segredo, não roda limpeza e não amplia escopo, limite nem janela. Detalhes e prompts por etapa: [cadastrar-um-produto.md](../usar/cadastrar-um-produto.md).

## Próximos passos

O próximo passo é o [cadastro de um produto](../usar/cadastrar-um-produto.md) com o Claude Code, ou repetir este guia com `uv run hdast stack up vampi --secure` para ver o modo seguro do laboratório.

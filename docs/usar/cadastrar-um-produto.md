# Cadastrar um produto e operar com o agente

Para quem vai testar um produto **real** (ou de teste da empresa) com o Claude Code. Para o primeiro contato com a ferramenta, use antes o [primeiro-uso.md](../comecar/primeiro-uso.md).

## 1. O que pedir ao dono do produto

A [carta curta de autorização](carta-curta.md) preenchida e assinada, mais:

- o Swagger/OpenAPI do ambiente de teste (arquivo ou URL);
- contas de teste, uma por papel necessário, com as senhas por canal seguro entregues a **você**;
- se houver limpeza de dados: o script SQL, escrito e revisado por uma pessoa do time do produto (veja [limpeza-de-dados.md](limpeza-de-dados.md)).

Sem a carta, não comece. `scope`, `limits`, `authorization` e janelas do perfil vêm só dela, ou das suas respostas na entrevista (seção 5): o agente nunca os escreve; transcreve num `carta.yml` e a CLI gera.

## 2. Onde ficam os perfis

Perfis reais **ficam fora deste repositório** (o repositório só tem o modelo em `products/_template/`).

```powershell
mkdir C:\hdast-produtos                        # a pasta precisa existir
$env:HDAST_PRODUCTS_DIR = "C:\hdast-produtos"  # PowerShell; no Git Bash: export HDAST_PRODUCTS_DIR=/c/hdast-produtos
```

Cada produto é uma pasta com o nome do produto (`target.yml`, `data-rules.yml`, `flows.yml`, o OpenAPI e, se houver limpeza de dados, `cleanup/`, que o `init` só cria com `--with-cleanup`). Versione-as num repositório privado.

## 3. Como guardar os segredos

O perfil nunca tem senha. Ele tem uma referência, e o valor fica fora do repositório. São duas formas, e você escolhe por segredo:

**Cofre do sistema (recomendado no dia a dia): `secret_ref: "keyring:NOME"`.** Você grava uma vez, num terminal seu, e vale em todo terminal e em toda sessão; nada fica no histórico do shell:

```powershell
uv run hdast setup meu-produto                        # grava só as senhas que faltam e pede a aprovação do escopo
uv run hdast secret set MEU_PRODUTO_USER_A_SENHA      # ou uma por vez: prompt oculto, duas vezes
uv run hdast secret list meu-produto                  # mostra quais existem (nunca o valor)
```

Os nomes são os que a carta lista. O agente **não** roda `setup`, `secret set` nem `secret delete` (a permissão os nega e o comando só funciona em terminal interativo): quando faltar um segredo, ele cita o NOME e pede que você rode o comando. No Windows o valor vai para o Gerenciador de Credenciais.

**Variável de ambiente: `secret_ref: "env:NOME"`** (CI, contêiner, ou se preferir), definida no terminal de onde abre o Claude Code:

```powershell
$env:MEU_PRODUTO_USER_A_LOGIN = "..."          # os nomes são os que a carta lista
$env:MEU_PRODUTO_USER_A_SENHA = "..."
```

Regras: nunca escreva senha em arquivo do repositório, em prompt nem em chat; não peça ao agente que leia `.env`. Se colar uma senha por engano, troque a senha da conta de teste. O cofre protege contra o histórico e contra arquivo esquecido, não contra um programa que rode na sua conta: a conta de teste continua tendo de ser descartável. O harness mascara segredos em relatórios, logs e auditoria, mas **o ambiente do terminal é visível ao processo do agente**: use contas de teste dedicadas, sem poder fora do ambiente de teste.

## 4. Abrir o Claude Code

Na raiz deste repositório, com `HDAST_PRODUCTS_DIR` definido e os segredos já guardados (cofre ou variáveis), rode `claude`. O Claude Code carrega as skills de `.claude/skills/` e aplica as permissões da camada 0 de `.claude/settings.json`. A mesma configuração registra uma segunda camada, o hook `PreToolUse`, que verifica chamadas de shell e de ferramentas de arquivo.

Com `uv` no PATH e Python 3.12 disponível, o hook usa `uv run --no-project --quiet python "${CLAUDE_PROJECT_DIR}/.claude/hooks/guard.py"` em Windows e Linux. O Claude Code v2.1.295 ou posterior bloqueia falhas do lançador e tempo esgotado com `onFailure: block`. `--no-project` evita sincronizar as dependências do projeto a cada chamada. Ao detectar uma ação reservada, entrada inválida ou falha de processamento, o hook devolve código `2` e o Claude Code comunica o motivo ao agente. [ADR 0111](../decisoes/0111-hook-pretooluse-segunda-camada.md).

- O hook barra os comandos humanos, inclusive `hdast cleanup --dry-run`. Quem roda a simulação é você. [Limpeza de dados](limpeza-de-dados.md).
- O hook detecta clientes de rede conhecidos por caminho absoluto, dentro de `sh -c` e em formas listadas de código inline. Scripts que montam endereços em tempo de execução podem escapar. O isolamento de rede é a barreira física contra HTTP direto ao alvo e a avaliação cega verifica o transcript.
- Aprovações, confirmações humanas e arquivos que configuram o hook exigem alterações por uma pessoa. Skills e agentes continuam disponíveis para edição durante o desenvolvimento.
- A negação de escrita em `cleanup/` cobre `products/*/cleanup/` dentro do repositório. A pasta de produtos real fica **fora** dele (`HDAST_PRODUCTS_DIR`): proteja o script de limpeza com as permissões do sistema de arquivos e a revisão do time do produto.
- O processo do agente herda o ambiente do terminal. O hook barra formas conhecidas de listar variáveis e ler arquivos de segredo. Aplique também as regras da Parte B de `AGENTS.md`.
- As duas camadas também se aplicam ao Claude Code durante o desenvolvimento. A CLI continua impondo escopo e autorização durante a operação. [Como usar o harness](../../README.md#como-usar).

## 5. A entrevista e a aprovação do escopo

Ao cadastrar, o agente lê a carta e o Swagger, monta um `carta.yml` com o que a carta diz (cada resposta com a origem: `carta`, `pessoa` ou `desconhecido`) e roda `hdast init <produto> --from-letter carta.yml --check`, que lista o que falta. Em seguida ele faz **uma rodada de perguntas** com tudo o que faltou, nesta ordem (perguntas fechadas em múltipla escolha, sempre com "Não sei / não está na carta"; abertas em texto):

1. **Portões:** o ambiente é de teste? Os dados são sintéticos? A autorização está vigente? Quem é o dono do produto? "Não" ou "não sei" encerra o cadastro.
2. **Endereço base** do ambiente de teste.
3. **O que pode e o que é proibido** (hosts, caminhos, métodos). Proibição usa curinga (`/api/admin/**`), nunca um id literal.
4. **Modo do caminho:** estrito (padrão) ou amplo. O amplo só vale se a carta disser; o agente nunca o sugere.
5. **Janela, validade e referência** da autorização.
6. **Limites:** requisições por segundo, duração máxima, threads. "Não sei" aqui usa o mínimo da CLI (1 req/s, 30 min, 1 thread; e 1 login por minuto no limite de logins), com aviso. É o único campo em que "não sei" vira valor.
7. **Contas:** apelido, papel e o **nome** do segredo (nunca a senha); se há duas contas do mesmo papel (o teste de autorização entre contas precisa).
8. **Escrita do teste entre contas:** a carta autoriza o teste de autorização entre contas a **escrever** no ambiente (atribuição em massa, métodos de escrita)? O teste de leitura roda por padrão no `run`; só a escrita depende disto. "Não sei" vale não, e "sim" só vale com a frase da carta que o diz. Quem responde é o dono do produto.
9. **Força do ataque:** leve, média ou forte. Mais força testa mais variações e demora mais; o limite por segundo e a janela continuam valendo. Sem escolha, vale o padrão do perfil.
10. **Dados de exemplo** que existem no ambiente (um id, um nome de arquivo, um código válido). Sem eles, algumas funções não são alcançadas.

**Pedido curto.** Você pode pedir em poucas linhas: o Swagger, as contas com papel (só o login, **nunca a senha**) e, se quiser, documentos `.md` de regra de negócio. Se colar uma senha, o agente avisa, não a usa e sugere trocar a senha da conta de teste. O agente pergunta só o que falta, numa rodada, em três grupos: **portões** ("não sei" para o cadastro: os quatro portões, endereço, o que pode, o que é proibido, referência, validade, janelas, tipo de login e contas), **padrão seguro** ("não sei" usa o mínimo da CLI e o agente diz qual) e **opcionais** (segunda conta do mesmo papel, dados de exemplo: "não sei" segue e o relatório anota).

O agente **não marca opção como recomendada** nem preenche escopo, limite, janela ou autorização por conta própria. "Não sei" entra como `desconhecido` e o agente para naquele campo: quem responde é o dono do produto. Com tudo respondido, a CLI gera `environment`, `scope`, `limits`, as contas e a força do ataque no `target.yml`; o agente escreve só o que a carta não traz (`probe`, `auth.csrf`, `auth.account_map`, `data-rules.yml`, `flows.yml`).

Carta com autorização já vencida (`valid_until` no passado) é recusada com `AUTHORIZATION_EXPIRED`. Com a carta pronta, o agente também pode trazer **avisos** (`data.warnings`), que não bloqueiam nada: permissão com `/**` na raiz, método `DELETE` autorizado, nenhum caminho proibido, validade a mais de um ano e escrita do teste entre contas autorizada (`AUTHZ_WRITES_AUTHORIZED`). Ele os mostra a você, e você confirma com o dono do produto se é isso mesmo.

**A tabela "quem pode o quê" (opcional, é sua).** Para testar quem NÃO pode usar cada função (acesso vertical entre papéis que não formam uma escada), o agente roda `hdast authz <produto> --draft-matrix` (com `--run <run_id>` do `probe`, o `allow` vem preenchido pelo que o `probe` viu). Isso **não envia nada ao alvo** e grava só `authz-matrix.draft.yml` na pasta do produto, que o perfil não lê. O rascunho é uma hipótese: o `deny` vem **sempre vazio**, porque quem proíbe é o dono do produto. Você (com o dono) decide cada linha, o agente leva a tabela para `authz.access_matrix` do `target.yml` e valida, e **você** aprova o escopo de novo (o resumo mostra a tabela inteira). Papel que a tabela não cita não é testado, nunca é tratado como proibido. Detalhes em [authz.md](../referencia/authz.md).

Se a carta disser que contas de algum papel compartilham legitimamente seus recursos, registre os papéis em `attack.authz_shared_roles` com `source: carta` e a frase em `quote`. A CLI os leva a `authz.shared_roles`; isso deixa de comparar essas contas em `horizontal` e `horizontal_write`, com `shared_role` em `not_tested`. Não infira compartilhamento. Quando possível, distribua leituras distintas de cada tipo de objeto entre duas contas de um papel não compartilhado; cada operação aceita uma conta.

**Aprovação do escopo (você, num terminal seu).** Quando `profile validate` der `runnable: true`, o agente mostra o resumo (endereço, funções, o que é proibido, janela, limites, força, política da varredura, teste de autorização e limpeza, se houver) e pede que **você** rode `hdast setup <produto>` (grava as senhas `keyring:` que faltam, mostra o resumo com os avisos de padrão mínimo e de nenhum caminho proibido, faz uma pausa e pede o nome do produto) ou, só a aprovação, `hdast profile approve <produto>`. Sem essa aprovação, os comandos que tocam o alvo recusam (`SCOPE_NOT_APPROVED`). O agente não roda esses comandos, e nenhuma permissão os libera: leia o resumo antes de aprovar. Depois dela, editar qualquer campo travado (`environment`, `scope`, `limits`, contas, `scan`, `authz`, `cleanup`) pede aprovar de novo; só o que serve para alcançar as operações (`probe`, `auth.csrf`, `auth.account_map`, `auth.default_account`, `auth.token_expired`, codificação do login, `openapi`) fica livre.

## 6. Os prompts

**Atalho: um pedido só (skill `test-product`).** A skill conduz as quatro etapas abaixo em sequência (começa pela entrevista da seção 5) e só para quando precisa de você: falta dado na carta, falta a sua aprovação do escopo, a alcançabilidade não chegou à meta depois das tentativas permitidas, há achado alto para você confirmar, ou qualquer dúvida de autorização, escopo ou janela. As travas são as mesmas.

```text
Use a skill test-product no produto "<produto>". A pasta de produtos é <pasta>.
O OpenAPI está em <caminho ou URL>. A carta de autorização está em <caminho>;
use SOMENTE o que ela diz. É ambiente de teste com dados sintéticos e a
autorização vale agora. Se faltar dado, pergunte. No fim, me entregue os achados
altos para eu confirmar e o caminho do report.html.
```

Se preferir acompanhar etapa por etapa, ou retomar de uma etapa, use os prompts abaixo.

Troque o que está entre `<>`. Cada etapa usa uma skill e deixa um diário de decisões.

**Etapa 1. Cadastrar (skill `onboard-product`)** (conduz a entrevista da seção 5)

```text
Use a skill onboard-product para cadastrar o produto "<produto>".
A pasta de produtos é <pasta>. O OpenAPI está em <caminho ou URL>.
A carta de autorização está em <caminho>; use SOMENTE o que ela diz para
escopo, limites, autorização, janelas e limpeza. O que faltar, pergunte numa
rodada só (entrevista), sem sugerir valores. Termine pedindo a minha aprovação
do escopo.
Termine com "hdast profile validate" e "hdast spec inspect" limpos e registre
as decisões em decision-log.md na pasta do produto.
```

**Etapa 2. Alcançar os endpoints (skill `fix-reachability`)**

```text
Use a skill fix-reachability no produto "<produto>". Rode preflight e probe
e ajuste só data-rules.yml, flows.yml e o mapa de contas. Meta: 90% das
operações tentadas com sucesso; no máximo 6 execuções do probe; pare e me
diga o que falta quando uma causa não for de dados (401/403 persistente,
429, 5xx). Registre cada rodada no diário de decisões.
```

**Etapa 3. Varrer (skill `run-scan`)**

```text
Use a skill run-scan no produto "<produto>". Confirme comigo que a janela
e a autorização valem agora. Suba a pilha, rode "hdast run", leia run.json
e me diga o código de saída, a cobertura e se o relatório é parcial. Não
rode limpeza: se houver comando de limpeza, só me informe.
```

**Etapa 4. Triar (skill `triage-findings`)**

```text
Use a skill triage-findings na execução <run_id> do produto "<produto>".
Proponha as anotações em triage.json (nunca mude severidade nem apague
achado), reemita o relatório e me entregue: achados que exigem ação humana,
suspeitas de falso positivo com o motivo e o que a varredura não cobre.
```

**Uma pessoa revisa tudo.** O agente propõe; a severidade e a confiança do relatório são propostas, e todo achado exige triagem humana.

## 7. Depois da varredura

- Abra `runs/<run_id>/report.html` no navegador (uma página só, sem internet, para ler e compartilhar; comece pelo resumo e por "O que fazer agora"). O mesmo conteúdo está em `report.md` e `findings.json` (comece por "O que este relatório não testou").
- Para remover os dados de teste, siga [limpeza-de-dados.md](limpeza-de-dados.md): você roda, não o agente.
- Problemas: [problemas-comuns.md](problemas-comuns.md). Parar tudo: `uv run hdast stop`.

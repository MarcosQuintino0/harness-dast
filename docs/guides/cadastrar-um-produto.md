# Cadastrar um produto e operar com o agente

Para quem vai testar um produto **real** (ou de teste da empresa) com o Claude Code. Para o primeiro contato com a ferramenta, use antes o [primeiro-uso.md](primeiro-uso.md).

## 1. O que pedir ao dono do produto

A [carta de autorização](modelo-de-autorizacao.md) preenchida e assinada, mais:

- o Swagger/OpenAPI do ambiente de teste (arquivo ou URL);
- contas de teste, uma por papel necessário, com as senhas por canal seguro entregues a **você**;
- se houver limpeza de dados: o script SQL, escrito e revisado por uma pessoa do time do produto (veja [limpeza-de-dados.md](limpeza-de-dados.md)).

Sem a carta, não comece. `scope`, `limits`, `authorization` e janelas do perfil vêm só dela.

## 2. Onde ficam os perfis

Perfis reais **ficam fora deste repositório** (o repositório só tem o modelo em `products/_template/`).

```powershell
mkdir C:\hdast-produtos                        # a pasta precisa existir
$env:HDAST_PRODUCTS_DIR = "C:\hdast-produtos"  # PowerShell; no Git Bash: export HDAST_PRODUCTS_DIR=/c/hdast-produtos
```

Cada produto é uma pasta com o nome do produto (`target.yml`, `data-rules.yml`, `flows.yml`, o OpenAPI e, se houver limpeza de dados, `cleanup/`, que o `init` só cria com `--with-cleanup`). Versione-as num repositório privado.

## 3. Como guardar os segredos

O perfil nunca tem senha. Ele tem `secret_ref: "env:NOME"`, e o valor fica numa variável de ambiente que **você** define no terminal de onde abre o Claude Code:

```powershell
$env:MEU_PRODUTO_USER_A_LOGIN = "..."          # os nomes são os que a carta lista
$env:MEU_PRODUTO_USER_A_SENHA = "..."
```

Regras: nunca escreva senha em arquivo do repositório, em prompt nem em chat; não peça ao agente que leia `.env`. O harness mascara segredos em relatórios, logs e auditoria, mas **o ambiente do terminal é visível ao processo do agente**: use contas de teste dedicadas, sem poder fora do ambiente de teste.

## 4. Abrir o Claude Code

Na raiz deste repositório, com `HDAST_PRODUCTS_DIR` e as variáveis de segredo já definidas, rode `claude`. As skills em `.claude/skills/` e as permissões de `.claude/settings.json` carregam sozinhas. As permissões negam `curl`, `wget`, `hdast cleanup` e leitura de `.env`: são conveniência (camada 0); a trava de verdade é o código da CLI ([detalhes](../../README.md#como-usar)).

O que as permissões **não** garantem (o formato de regras do Claude Code não expressa):

- `hdast cleanup` é negado em qualquer forma, **inclusive `--dry-run`**: a regra casa pelo texto do comando e não distingue flag. Quem roda a simulação é você ([limpeza-de-dados.md](limpeza-de-dados.md)).
- Regra de comando casa o texto escrito, não o programa: `python`/`node` com biblioteca HTTP, caminho absoluto de `curl` ou `sh -c '...'` não são negados. A defesa contra HTTP direto ao alvo é a rede do laboratório (o alvo só é alcançável pelo proxy de escopo) e a avaliação cega, que procura isso no transcript.
- A negação de escrita em `cleanup/` cobre `products/*/cleanup/` dentro do repositório. A pasta de produtos real fica **fora** dele (`HDAST_PRODUCTS_DIR`): proteja o script de limpeza com as permissões do sistema de arquivos e a revisão do time do produto.
- O ambiente do terminal (as senhas das contas de teste) é herdado pelo processo do agente; as regras negam `printenv` e a leitura de `.env`, mas não impedem toda forma de ler uma variável.
- As regras valem também para quem desenvolve o projeto neste repositório (por exemplo, WebFetch e `curl` ficam negados).

## 5. Os prompts

**Atalho: um pedido só (skill `test-product`).** A skill conduz as quatro etapas abaixo em sequência e só para quando precisa de você: falta dado na carta, a alcançabilidade não chegou à meta depois das tentativas permitidas, há achado alto para você confirmar, ou qualquer dúvida de autorização, escopo ou janela. As travas são as mesmas.

```text
Use a skill test-product no produto "<produto>". A pasta de produtos é <pasta>.
O OpenAPI está em <caminho ou URL>. A carta de autorização está em <caminho>;
use SOMENTE o que ela diz. É ambiente de teste com dados sintéticos e a
autorização vale agora. Se faltar dado, pergunte. No fim, me entregue os achados
altos para eu confirmar e o caminho do report.html.
```

Se preferir acompanhar etapa por etapa, ou retomar de uma etapa, use os prompts abaixo.

Troque o que está entre `<>`. Cada etapa usa uma skill e deixa um diário de decisões.

**Etapa 1. Cadastrar (skill `onboard-product`)**

```text
Use a skill onboard-product para cadastrar o produto "<produto>".
A pasta de produtos é <pasta>. O OpenAPI está em <caminho ou URL>.
A carta de autorização está em <caminho>; use SOMENTE o que ela diz para
escopo, limites, autorização, janelas e limpeza. Se algo faltar, pergunte.
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

## 6. Depois da varredura

- Abra `runs/<run_id>/report.html` no navegador (uma página só, sem internet, para ler e compartilhar; comece pelo resumo e por "O que fazer agora"). O mesmo conteúdo está em `report.md` e `findings.json` (comece por "O que este relatório não testou").
- Para remover os dados de teste, siga [limpeza-de-dados.md](limpeza-de-dados.md): você roda, não o agente.
- Problemas: [problemas-comuns.md](problemas-comuns.md). Parar tudo: `uv run hdast stop`.

# Preparar uma rodada cega no Codespaces

Use um Codespace descartável por rodada, com os casos sintéticos previstos no
[ADR 0118](../decisoes/0118-laboratorio-em-maquinas-efemeras-do-github.md).
Este guia é para o coordenador. A referência da avaliação é o
[protocolo da rodada cega](../../evals/protocolo-da-rodada-cega.md).

## Criar o Codespace

Na conta do dono, em **Settings → Codespaces → Secrets**, cadastre a credencial
exigida pela ferramenta escolhida e conceda acesso somente ao repositório da
rodada. A ferramenta pode usar a variável de ambiente entregue pelo Codespaces.
Mantenha o valor fora do checkout, do pedido ao agente, dos logs e dos resultados.
[Segredos pessoais do Codespaces](https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces)

Em **Settings → Codespaces** do repositório, use uma branch sem configuração de
prebuild. O `postCreateCommand` instala as dependências com `uv sync --locked` na
criação. [Configuração de prebuilds](https://docs.github.com/en/codespaces/prebuilding-your-codespaces/configuring-prebuilds)

No terminal local autenticado com `gh`, substitua `BRANCH_PUBLICADA` pela branch
da rodada. Confirme o identificador da máquina de 4 núcleos e 16 GB na lista
antes de criar. O identificador pode variar conforme as opções do repositório.
[API de máquinas](https://docs.github.com/en/rest/codespaces/machines#list-available-machine-types-for-a-repository)

```bash
repo=MarcosQuintino0/harness-dast
branch=BRANCH_PUBLICADA
gh api --method GET "repos/$repo/codespaces/machines" -f ref="$branch" \
  --jq '.machines[] | select(.cpus == 4 and .memory_in_bytes == 17179869184) | [.name, .display_name] | @tsv'
machine=standardLinux  # ajuste conforme a lista
gh codespace create --repo "$repo" --branch "$branch" --machine "$machine" \
  --display-name rodada-cega --idle-timeout 15m --retention-period 1h --status
cs=NOME_DO_CODESPACE_CRIADO
gh codespace ssh --codespace "$cs"
```

## Preparar e conferir a cópia

No terminal do Codespace, na raiz do checkout do coordenador, rode o preparador.
Escolha um caminho novo fora do checkout e a semente acordada para o estudo.

```bash
python --version
uv --version
docker version
docker compose version
out="$HOME/rodada-cega-001"
uv run --locked python -m evals.prepare_codespace \
  --case vampi --mode random --seed 19 --out "$out"
test -f "$out/workspace/EVAL-BRIEFING.md"
test ! -e "$out/workspace/evals/answer-keys"
test -z "$(find "$out/workspace" -name .git -print -quit)"
find "$out/workspace/.claude/skills" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort
```

O preparador termina com a cópia cega e o lacre da rodada, sem subir a pilha.
Confira as cinco skills de uso, o manifesto `sealed/workspace-manifest.json` e o
relatório `sealed/leak-report.json`. A base Git da rodada fica em
`sealed/workspace.git`, junto dos arquivos do coordenador.
Restrinja a ferramenta avaliada à pasta `workspace/` e mantenha o checkout
original, o lacre e a conversa do coordenador fora do alcance dela. Uma pasta
separada por si só não restringe o acesso ao restante do Codespace.

O repositório público no GitHub contém os gabaritos. Um agente com navegação na
web pode encontrá-los. Desabilite a navegação da ferramenta avaliada quando ela
oferecer esse controle e registre a configuração usada.

## Instalar a cópia e preparar a sessão

Instale as dependências no diretório da cópia. O ambiente virtual do checkout
original pertence ao coordenador.

```bash
(cd "$out/workspace" && uv sync --locked)
```

O coordenador aplica `sealed/agent-env.json` no ambiente de um processo novo,
antes de iniciar a ferramenta avaliada, para que o agente e seus subprocessos
herdem o modo sorteado, as credenciais sintéticas, `HDAST_PRODUCTS_DIR` e
`HDAST_STATE_DIR`. Carregue o JSON como pares de nome e valor diretamente no
ambiente do processo, com o rastreamento do shell desativado. Mantenha os valores
fora da linha de comando, do pedido, dos logs e de arquivos no workspace. Ao
retomar a sessão em outro processo, aplique o mesmo lacre.

A sessão começa em `workspace/`, sem histórico do coordenador. O pedido
padronizado do protocolo encaminha o agente ao `EVAL-BRIEFING.md`, ao README
e às cinco skills da cópia. Registre ferramenta, versão, modelo, esforço,
horários e transcript estruturado de cada segmento fora do workspace.

## Aprovar o escopo

Ao receber `SCOPE_NOT_APPROVED`, o agente registra a pendência e pausa. Na raiz
do checkout original, o coordenador confere o perfil com a carta e usa o
subcomando do executor da avaliação.

```bash
uv run --locked python -m evals.runner approve --out "$out"
```

O executor valida o perfil, recusa alargamentos e grava a aprovação em
`state/`, o diretório indicado por `HDAST_STATE_DIR`. Registre a decisão e o
horário. Se houver recusa, encerre a rodada e registre o motivo. Se houver
aprovação, a retomada é na mesma conversa, com a mensagem padronizada
`escopo aprovado, continue`. Quem sobe a pilha depois da aprovação do
coordenador é o agente avaliado. Alterações nas proteções do perfil exigem
nova aprovação.

## Coletar e avaliar

Com o agente parado e a pilha ainda de pé, reúna o transcript completo em
`$out/transcript.jsonl`, fora do workspace. Use o formato JSONL do Claude Code
esperado pelo runner. Se a ferramenta usar outro formato, preserve os originais
e normalize os eventos de todos os segmentos na ordem, com os horários
disponíveis. Registre lacunas no transcript que afetem a comparação.

Na raiz do checkout original, colete o rastro antes de derrubar a pilha. Confira
`trace/collect.json` e registre os problemas de coleta na ficha da rodada.

```bash
uv run --locked python -m evals.runner collect --out "$out"
```

Depois da coleta, o coordenador derruba a pilha usando a CLI da cópia com o
ambiente da rodada. De volta ao checkout original, obtenha as medidas.

```bash
uv run --locked python -m evals.runner measure --out "$out"
```

Use `agent-metrics.json` para obter `tokens` (soma de
`input`, `output`, `cache_creation` e `cache_read` em `totals.tokens`) e
`duration_seconds` (`totals.duration_seconds` arredondado), quando medidos.

```bash
uv run --locked python -m evals.runner score --out "$out" \
  --tokens "$tokens" --duration-seconds "$duration_seconds"
uv run --locked python -m evals.runner classify --out "$out"
```

Omita a opção correspondente a qualquer medida ausente. Revise `score.json`,
`score.md` e `classify.md`, classifique as falhas e registre o commit de origem,
o manifesto, as intervenções e os limites de comparação. Siga a
[retenção de evals](../../evals/README.md#retenção-de-resultados-e-medições).

## Baixar os resultados e apagar a máquina

Reúna os resultados sanitizados em `$HOME/rodada-cega-001/resultado/`. Inclua a
nota, as métricas comparáveis, o resumo das intervenções e as evidências
sanitizadas necessárias à conclusão. Para conferir apenas o preparo, copie
para lá `sealed/workspace-manifest.json`.

```bash
mkdir -p "$out/resultado"
cp "$out/sealed/workspace-manifest.json" "$out/resultado/"
```

Baixe a pasta no terminal local, confirme os arquivos baixados e apague só o
Codespace da rodada. Mantenha lacre, credenciais e rastros brutos fora do pacote.
[Cópia de arquivos](https://cli.github.com/manual/gh_codespace_cp)

```bash
gh codespace cp --codespace "$cs" --recursive 'remote:rodada-cega-001/resultado' ./
gh codespace delete --codespace "$cs"
```

Confira a página [Billing and licensing → Usage](https://github.com/settings/billing/usage)
na conta do dono e filtre por Codespaces. O GitHub Free pessoal inclui 120
núcleo-horas e 15 GB-mês. Uma hora em 4 núcleos consome 4 núcleo-horas, o que dá
até 30 rodadas de uma hora pela cota de computação, sujeito ao armazenamento e ao
uso restante da conta. [Faturamento do Codespaces](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces)

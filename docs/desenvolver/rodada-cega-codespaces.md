# Preparar uma rodada cega no Codespaces

Use um Codespace descartável por rodada, com os casos sintéticos previstos no
[ADR 0118](../decisoes/0118-laboratorio-em-maquinas-efemeras-do-github.md).

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

Confira as cinco skills de uso e o relatório de vazamentos no lacre. A base Git
da rodada fica em `sealed/workspace.git`, junto dos arquivos do coordenador.
Restrinja a ferramenta avaliada à pasta `workspace/` e mantenha o checkout
original, o lacre e a conversa do coordenador fora do alcance dela. Uma pasta
separada por si só não restringe o acesso ao restante do Codespace.

O repositório público no GitHub contém os gabaritos. Um agente com navegação na
web pode encontrá-los. Desabilite a navegação da ferramenta avaliada quando ela
oferecer esse controle e registre a configuração usada.

## Baixar os resultados e apagar a máquina

Reúna os resultados sanitizados em `$HOME/rodada-cega-001/resultado/`. Para
conferir apenas o preparo, copie para lá `sealed/workspace-manifest.json`.

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

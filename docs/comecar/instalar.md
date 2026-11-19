# Instalar o harness-dast

## Com o plugin

Ao iniciar uma sessão do Claude Code com o plugin `hdast`, o hook `SessionStart` informa a versão do plugin e confere o `uv`, a versão da CLI, o Docker e as imagens da versão. A consulta de versão usa `hdast --version` e a conferência das imagens usa os digests do wheel instalado por `uv tool`. O hook só consulta a máquina. Se os digests não estiverem disponíveis, ele avisa que pulou essa conferência.

Use `/hdast:preparar` quando o hook apontar uma pendência. A skill diagnostica a máquina e pede um sim para cada instalação. Se faltar `uv`, instale-o no seu terminal e reabra o Claude Code. No Windows, use `winget install --id astral-sh.uv -e`. No Linux ou no macOS, siga o [guia oficial do uv](https://docs.astral.sh/uv/getting-started/installation/).

O wheel vem da release correspondente à versão do plugin. Para usar outro repositório GitHub de releases do hdast, configure `HDAST_RELEASE_REPOSITORY` no formato `dono/repositório`. O padrão é `MarcosQuintino0/harness-dast`.

## Pelo wheel da release

Instale o [`uv`](https://docs.astral.sh/uv/getting-started/installation/) e abra um novo terminal. Na [release do GitHub](https://github.com/MarcosQuintino0/harness-dast/releases) da versão desejada, copie o endereço do anexo `harness_dast-…-py3-none-any.whl`. Substitua `<URL do wheel>` pelo endereço copiado.

```bash
uv tool install --python 3.12 <URL do wheel>
hdast version
```

O `uv` instala a CLI em um ambiente isolado e baixa o Python 3.12 se precisar, sem alterar o Python do sistema. Se o terminal ainda não encontrar `hdast`, rode `uv tool update-shell` e abra outro terminal.

Para preparar a pilha, [instale e inicie o Docker](docker.md) e rode:

```bash
hdast stack pull
hdast doctor
```

A instalação usa o Compose do pacote e as imagens publicadas por digest: o ZAP, o proxy de escopo e o Nuclei, o segundo motor ([ADR 0122](../decisoes/0122-nuclei-como-segundo-motor.md)). O Nuclei é uma imagem a mais para baixar, com `hdast stack pull`; ela só é usada quando o perfil tem `extra_checks.nuclei`. Para a demo e os alvos de laboratório mantidos no repositório, use o clone.

## Pelo clone de desenvolvimento

1. Instale o [Git](https://git-scm.com/) e o [`uv`](https://docs.astral.sh/uv/getting-started/installation/). Abra um novo terminal e confirme com `git --version` e `uv --version`.
2. Clone o repositório e instale as dependências. O `uv` prepara a `.venv` e usa o arquivo de dependências travadas do projeto.

   ```bash
   git clone https://github.com/MarcosQuintino0/harness-dast.git
   cd harness-dast
   uv sync --locked
   uv run hdast version
   ```

3. Instale e inicie o Docker para usar a pilha. Siga o [guia do Docker](docker.md) para baixar as imagens dessa versão.
4. Na raiz do repositório, confira o ambiente.

   ```bash
   uv run hdast doctor
   ```

   Cada falha vem com a ação para corrigi-la. Com o ambiente pronto, siga o [primeiro uso no laboratório](primeiro-uso.md).

# Instalar o harness-dast

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

A instalação usa o Compose do pacote e as imagens publicadas por digest. Para a demo e os alvos de laboratório mantidos no repositório, use o clone.

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

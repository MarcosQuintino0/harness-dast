# Instalar o harness-dast

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

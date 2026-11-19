# Lançar uma versão

## Preparar o commit e enviar a tag

1. Atualize a versão no `pyproject.toml`, no `uv.lock` e em `plugin/.claude-plugin/plugin.json`. Na entrada do plugin em `.claude-plugin/marketplace.json`, ajuste `source.ref` para `v<versão>` e remova `source.sha` até a CI registrar o novo commit.
2. Depois da revisão e das checagens, integre o commit da versão à `main`. Crie e envie uma tag anotada apontando para esse commit. Por exemplo, substituindo `1.2.3` pela versão do pacote:

   ```bash
   git switch main
   git pull --ff-only origin main
   git tag -a v1.2.3 -m "Lança a versão 1.2.3"
   git push origin refs/tags/v1.2.3
   ```

## O que a CI publica

O workflow [Imagens Docker](../../.github/workflows/images.yml) publica no GHCR as imagens do ZAP e do proxy de escopo para Linux AMD64 e ARM64. A CI coleta os digests publicados no artefato `images-lock`, confere as versões da tag, do pacote, do arquivo de digests e do plugin e inclui o arquivo de digests no pacote. A release do GitHub recebe o wheel (`.whl`) e a distribuição de código-fonte (`.tar.gz`).

## Revisar o PR do marketplace

Após publicar os pacotes, a CI abre um PR de `chore/marketplace-v<versão>` para a `main`. O PR fixa `source.ref` na tag e `source.sha` no commit da tag. Confira os dois valores e integre o PR após a revisão. O GitHub Actions precisa ter permissão nas configurações do repositório para criar pull requests.

Enquanto nenhuma tag contiver o plugin, o manifesto aponta para a versão do `pyproject.toml` com `sha` ausente. A instalação pelo marketplace depende da primeira tag que contenha `plugin/`. Para carregar o plugin durante o desenvolvimento, use `claude --plugin-dir plugin/` a partir do clone.

## Instalar no Claude Code

Após a integração do PR do marketplace, execute estes comandos no Claude Code:

```text
/plugin marketplace add MarcosQuintino0/harness-dast
/plugin install hdast@hdast
```

Consulte a decisão de distribuição para detalhes. [ADR 0119](../decisoes/0119-hdast-como-plugin-do-claude-code.md)

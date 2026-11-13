# 0015. Portas do perfil e carregador de YAML endurecido

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** Marco M2 (segunda metade); detalha o [ADR 0004](0004-portas-e-adaptadores-em-tres-camadas.md), o [ADR 0005](0005-perfil-de-produto-versionado.md) e o [ADR 0012](0012-dependencias-tzdata-e-pyyaml.md)

## Contexto

`hdast init` e `hdast profile validate` precisam ler e criar arquivos, o que é proibido em `domain` e `application`. O `target.yml` é escrito por um agente e editado por pessoas: é entrada não confiável. `yaml.safe_load` evita a execução de código, mas aceita âncoras, aliases e `<<` (escondem o que está configurado e permitem expansão exponencial), chave repetida (a última vence em silêncio, e um `deny_paths` poderia sumir) e tags como `!!binary`.

## Decisão

1. **Três portas novas** em `application/ports.py`, cada uma com consumidor e falso em `tests/fakes/`: `ProfileRepository` (`load`, `missing_files`), `ProductScaffolder` (`scaffold`) e `Clock` (`now`). O relógio já constava na lista de portas do ADR 0004.
2. **Carregador no adaptador `adapters/storage/`**, sobre `yaml.SafeLoader` (nunca `yaml.load` com outro `Loader`): recusa âncora, alias, chave `<<`, chave repetida ou não textual, qualquer tag explícita fora do esquema básico (`str`, `int`, `float`, `bool`, `null`, `seq`, `map`), mais de um documento, raiz que não é mapa, arquivo vazio, aninhamento acima de 40 níveis e arquivo acima de 256 KiB. UTF-8 estrito; BOM e CRLF são aceitos. As mensagens trazem só linha e coluna, nunca o conteúdo.
3. **Nome de produto é slug** e o caminho resolvido precisa ficar diretamente dentro de `products_dir` (links simbólicos e junções incluídos). `openapi` e `cleanup.script` precisam resolver para dentro da pasta do produto; a violação é `ConfigError`.
4. **Validade estrutural é erro; prontidão é dado.** `ProfileRepository.load` falha com `ConfigError`. Arquivos referenciados ausentes, valores de exemplo do modelo, autorização vencida e janela fechada não são exceção: aparecem em `issues` do resultado de `profile validate` (saída `0`, `runnable: false`). Motivo: o modelo recém-criado por `init` é estruturalmente válido e precisa dizer ao agente exatamente o que preencher.
5. **`init` ajusta `product:`** no `target.yml` copiado para o nome da pasta, e o carregador exige que os dois coincidam.
6. **Onde fica o modelo:** `products/_template` na raiz do repositório, localizado a partir do arquivo do adaptador (`parents[4]`). Funciona com `uv run` e instalação editável, que é o uso da V1 (P-11).

## Alternativas consideradas

- **Só `yaml.safe_load`.** Aceita âncoras, mesclagem e chaves repetidas. Descartada.
- **Biblioteca de YAML alternativa (`ruamel.yaml`).** Mais uma dependência sem ganho para este caso; ver ADR 0012.
- **Tratar arquivo ausente como `ConfigError` no carregador.** Faria `profile validate` falhar para o modelo intocado, escondendo a lista do que preencher. Descartada; `spec inspect` (M3) levantará o erro quando precisar do arquivo.
- **Embutir `products/_template` no pacote.** Resolve instalação por wheel, mas duplica o modelo ou muda o empacotamento; fica para quando houver distribuição fora do repositório (ADR novo).
- **Porta para o sistema de arquivos em geral.** Especulativa; só as três portas que um caso de uso consome.

## Consequências

- `profile validate` não confere variáveis de ambiente dos segredos (o provedor chega no M3).
- A detecção de "valor de exemplo" (domínios `exemplo.com.br`, `SEC-0000`, `MEU_PRODUTO_*`) vive em `application/validate_profile.py` e acompanha o modelo; mudar o modelo exige mudar a lista.
- Instalação por wheel não encontra o modelo; o erro orienta a rodar a partir do repositório.
- Registrado no [CHANGELOG.md](../../CHANGELOG.md).

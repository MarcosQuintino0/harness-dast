# 0113. Imagens publicadas e conferência de versão

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** Pacote 2.1. Atualiza a forma de obter as imagens dos ADRs [0019](0019-pilha-gerenciada-politica-por-execucao-e-login-pelo-proxy.md) e [0103](0103-regras-alpha-selecionadas-na-imagem-do-zap.md).

## Contexto

A pilha gerenciada reconstruía as imagens próprias no `stack up` para carregar o código atual da cerca. O primeiro build podia demorar ou falhar ao baixar dependências. Distribuir o ZAP e o proxy de escopo exige garantir que a imagem do proxy incorpore a versão que a CLI espera para sua política.

## Decisão

Vamos distribuir `hdast-zap` e `hdast-scope-proxy` no GHCR para `linux/amd64` e `linux/arm64`. A tag das duas imagens vem de `project.version` de `pyproject.toml`. A tag Git de publicação tem o prefixo `v`. O workflow se limita a disparo manual e push de tag, grava `org.opencontainers.image.version` e `org.opencontainers.image.revision` e atesta o digest do índice publicado.

O caso de uso de imagens recebe do adaptador as referências resolvidas do Compose e os metadados OCI locais. `stack pull` baixa as duas referências sem perfil e devolve `data.images` com as referências. Usa os códigos de saída existentes (`0`, `2`, `5` e `8`). Antes de alterar a pilha, `stack up` exige as duas imagens locais e igualdade exata entre o rótulo de versão do proxy e a versão instalada da CLI. O `doctor` aplica a mesma comparação. `vampi-tls` usa a mesma referência do proxy.

O modo de desenvolvimento, selecionado por `HDAST_STACK_BUILD=1` ou `--build`, constrói com o Compose sob tags locais próprias e confere a imagem antes da subida. O Dockerfile do proxy verifica a versão do pacote instalado durante esse build. Tags locais ficam separadas das referências de download.

## Alternativas consideradas

- Reconstruir sempre mantinha a cerca alinhada a mudanças locais e exigia que cada instalação tivesse as dependências de build.
- Baixar automaticamente no `up` tornaria a troca de imagens dependente de rede e poderia trocar a referência após a conferência local.
- Comparar a tag da imagem só verificaria um nome que pode ser alterado. O rótulo é conferido na imagem local e a origem publicada é atestada por digest.

## Consequências

- A instalação pode baixar as imagens próprias antes de iniciar a pilha. Imagens auxiliares e do laboratório continuam sob responsabilidade do Compose.
- A pessoa que desenvolve a cerca precisa usar build local para provar alterações dentro da mesma versão. As referências configuráveis são para imagens de origem confiável. O rótulo informa compatibilidade de versão e o atestado vincula a publicação ao commit.
- Após o aceite, o dono publica a primeira tag correspondente ao pacote e disponibiliza os dois pacotes para download. Com os digests confirmados, um PR fixa os índices multi-arquitetura no Compose. Em cada versão futura, atualize as tags padrão com a versão do pacote.

## Aceites verificáveis

- Com imagens presentes e proxy na versão da CLI, a pilha sobe com as imagens próprias locais. Imagem ausente ou proxy sem versão compatível bloqueiam a subida e preservam a pilha anterior.
- O build local roda antes da verificação e da recriação da pilha. O `doctor` mostra a presença das imagens e a compatibilidade do proxy.
- A publicação gera as duas arquiteturas, rótulos e um atestado por imagem. Uma tag Git divergente de `pyproject.toml` encerra o workflow antes de publicar.

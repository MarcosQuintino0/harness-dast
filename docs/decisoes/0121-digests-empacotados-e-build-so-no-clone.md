# 0121. Digests empacotados e build só no clone de desenvolvimento

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** Pacote 6.1, fase A do [ADR 0119](0119-hdast-como-plugin-do-claude-code.md).

## Contexto

O rótulo OCI de versão exigido pelo [ADR 0113](0113-imagens-publicadas-e-conferencia-de-versao.md)
confere a compatibilidade da cerca. O digest do índice publicado fixa também os bytes da imagem.
A CLI precisa aplicar esse digest em toda subida com os dados de publicação instalados.

## Decisão

Vamos gerar `images.lock.json` após a publicação das duas imagens pela CI da tag.
O artefato `images-lock` leva o esquema 1, a versão da CLI e as duas referências publicadas
com repositório, tag e digest SHA-256. O pacote 6.2 inclui esse arquivo no pacote da CLI.

Quando o arquivo está presente, `stack pull` e `stack up` usam suas referências por digest.
Arquivo inválido ou de outra versão resulta em `CONFIG_ERROR` (saída 2), com orientação
para reinstalar. A conferência do rótulo OCI do proxy continua valendo.

O build local exige os contextos `docker/zap` e `docker/scope-proxy/Dockerfile` e a ausência
do arquivo de digests. Esses sinais detalham a identificação do clone prevista no ADR 0119.
O `stack up` recusa `--build` e `HDAST_STACK_BUILD=1` fora do clone antes de chamar o Docker,
com `STACK_BUILD_FORBIDDEN` (saída 9). Com `reuse`, o Compose recebe a ordem de usar as
imagens já existentes.

## Alternativas consideradas

- Fixar os digests no Compose após cada publicação exigiria uma alteração posterior à tag.
- Conferir só o rótulo OCI deixa a tag sujeita a substituição no registro.

## Consequências

O arquivo acompanha a versão instalada e fica fora do Git. O adaptador lê os dados e
consulta os contextos de build. O caso de uso aplica a decisão com essas entradas injetadas.
A pilha procura `compose.yaml` na raiz do pacote Python (`harness_dast/`) e na raiz do clone.

## Aceites verificáveis

- O workflow publica `images-lock` só depois do push das duas imagens.
- `stack pull` e `stack up` usam as referências fixadas e falham diante de arquivo inválido ou divergente.
- Pedidos de build com `--build` ou `HDAST_STACK_BUILD=1` são aceitos no clone e recusados fora dele
  sem chamar o Docker. O modo `reuse` desabilita builds.

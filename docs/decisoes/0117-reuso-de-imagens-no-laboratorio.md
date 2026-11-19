# 0117. Reuso de imagens no laboratório

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** T5 da redução do tempo do `lab_fast`. Complementa o [ADR 0113](0113-imagens-publicadas-e-conferencia-de-versao.md).

## Contexto

O build repetido em cada subida do laboratório consome tempo. O primeiro build da Clínica Piloto pode ultrapassar o prazo da subida, especialmente quando o cache do Maven está vazio. A prova da cerca depende da imagem construída com o código do checkout.

## Decisão

Vamos construir o ZAP, o proxy e a Clínica Piloto uma vez por sessão em modo explícito de teste. O ZAP e o proxy recebem tags locais exclusivas da sessão. A Clínica mantém a tag do Compose, também usada nas provas do Oracle.

`HDAST_STACK_BUILD=reuse` faz a CLI passar `--no-build` ao projeto anexado quando o build local não foi solicitado. O Compose continua responsável pela obtenção de imagens auxiliares. A CLI segue exigindo as imagens próprias locais e o rótulo OCI do proxy igual à versão da CLI. O envelope JSON e os códigos de saída seguem os existentes.

## Alternativas consideradas

- Usar apenas as tags locais e omitir `--build`. O Compose ainda poderia construir o alvo por conta própria se a imagem desaparecesse entre subidas.
- Subir e derrubar pilhas para aquecer o cache. Isso inclui a espera dos contêineres no preparo e continua sujeito ao prazo reduzido de build.

## Consequências

O primeiro build usa prazo próprio. As subidas medem a recriação dos contêineres e podem incluir downloads de imagens auxiliares. Sem a opção de reuso, o Compose continua decidindo se precisa construir o alvo anexado. Um pedido explícito de build tem precedência.

## Aceites verificáveis

- O modo de sessão solicita apenas os builds de `zap`, `scope-proxy` e `pilot`, usando os arquivos Compose do checkout.
- Cada subida e recriação reutiliza as imagens e continua sujeita à conferência de versão do proxy.
- Se a imagem da Clínica estiver indisponível, o Compose não pode reconstruí-la em modo de reuso.

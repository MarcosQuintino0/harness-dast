# Imagem do Nuclei do harness-dast (ADR 0122): o binário oficial e o catálogo nuclei-templates em
# versão FIXA, baixados só no BUILD e conferidos por SHA-256. Nada é baixado nem atualizado em
# execução: o contêiner roda sem rota para fora (zap_net) e a CLI passa -duc, -ni e -t.
# A fonte única dos números é src/harness_dast/domain/nuclei_version.py; um teste de contrato
# (tests/contract/test_nuclei_dockerfile.py) falha se este arquivo divergir dela.
# Atualizar = trocar versão e SHA-256 aqui e em nuclei_version.py, regerar o manifesto
# (scripts/build_nuclei_manifest.py) e aprovar de novo os perfis com o Nuclei ligado.

# Base fixada por tag E digest do índice (Docker Hub: library/alpine). Atualizar = trocar os dois.
ARG BASE=alpine:3.22@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f

# ------------------------------------------------------------ estágio de download
FROM ${BASE} AS fetch
# SHA-256 do ZIP linux amd64 da release oficial (do arquivo de checksums dela) e do ZIP da tag
# do catálogo (conferido contra TEMPLATES_ARCHIVE_SHA256).
ARG NUCLEI_VERSION=3.11.1
ARG NUCLEI_SHA256=ea63d4ae232808cd7c6bc00d0142428e231fab59dae01042246097d195835ab6
ARG TEMPLATES_VERSION=10.5.1
ARG TEMPLATES_SHA256=00184ad496302cd1dd3cf4b0b1c3aa45d6b35057f7bdf17e932318185ba0ac50
# set -eu: falha de download ou SHA-256 diferente derruba o build. O download usa -f e só https.
RUN set -eu; \
    apk add --no-cache curl unzip; \
    mkdir /dl; cd /dl; \
    curl -fsSL --proto '=https' -o nuclei.zip \
      "https://github.com/projectdiscovery/nuclei/releases/download/v${NUCLEI_VERSION}/nuclei_${NUCLEI_VERSION}_linux_amd64.zip"; \
    curl -fsSL --proto '=https' -o templates.zip \
      "https://github.com/projectdiscovery/nuclei-templates/archive/refs/tags/v${TEMPLATES_VERSION}.zip"; \
    printf '%s  nuclei.zip\n%s  templates.zip\n' "${NUCLEI_SHA256}" "${TEMPLATES_SHA256}" | sha256sum -c -; \
    unzip -q nuclei.zip nuclei -d /out; \
    unzip -q templates.zip -d /unz; \
    mv "/unz/nuclei-templates-${TEMPLATES_VERSION}" /out/templates

# ------------------------------------------------------------- estágio final
FROM ${BASE}
ARG HDAST_IMAGE_VERSION
LABEL org.opencontainers.image.version=$HDAST_IMAGE_VERSION
# uid/gid FIXO 10002: o compose monta tmpfs com esse dono, e o arquivo de segredos do login
# (-sf) gravado pela CLI precisa pertencer a ele (lição do spike). Nunca root, sem shell de login.
RUN addgroup -g 10002 nuclei \
 && adduser -D -u 10002 -G nuclei -h /home/nuclei -s /sbin/nologin nuclei
COPY --from=fetch /out/nuclei /usr/local/bin/nuclei
COPY --from=fetch /out/templates /opt/nuclei-templates
# Binário e catálogo pertencem ao root e ficam só leitura: o processo não altera os modelos.
RUN chmod 0555 /usr/local/bin/nuclei \
 && chmod -R a-w,a+rX /opt/nuclei-templates
# HOME em tmpfs (compose): o Nuclei grava configuração e cache em ~ e o rootfs é somente leitura.
ENV HOME=/home/nuclei NO_COLOR=1
USER 10002:10002
ENTRYPOINT ["/usr/local/bin/nuclei"]

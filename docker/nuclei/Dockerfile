# Spike (branch spike/nuclei, nunca entra na main): imagem do Nuclei para rodar atras da cerca.
# Binario oficial v3.11.1 e catalogo nuclei-templates v10.5.1, ambos baixados no BUILD e
# conferidos por SHA-256 fixo (o do arquivo de checksums da release; o catalogo e o arquivo da tag). Nada e baixado
# nem atualizado em execucao (use sempre -duc -ni -ud /opt/nuclei-templates).
ARG BASE=alpine:3.22@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f

FROM ${BASE} AS fetch
ARG NUCLEI_VERSION=3.11.1
ARG NUCLEI_SHA256=ea63d4ae232808cd7c6bc00d0142428e231fab59dae01042246097d195835ab6
ARG TEMPLATES_VERSION=10.5.1
ARG TEMPLATES_SHA256=00184ad496302cd1dd3cf4b0b1c3aa45d6b35057f7bdf17e932318185ba0ac50
RUN set -eu; apk add --no-cache curl unzip; \
    mkdir /dl && cd /dl; \
    curl -fsSL --proto "=https" -o nuclei.zip \
      "https://github.com/projectdiscovery/nuclei/releases/download/v${NUCLEI_VERSION}/nuclei_${NUCLEI_VERSION}_linux_amd64.zip"; \
    curl -fsSL --proto "=https" -o templates.zip \
      "https://github.com/projectdiscovery/nuclei-templates/archive/refs/tags/v${TEMPLATES_VERSION}.zip"; \
    printf "%s  nuclei.zip\n%s  templates.zip\n" "${NUCLEI_SHA256}" "${TEMPLATES_SHA256}" | sha256sum -c -; \
    unzip -q nuclei.zip nuclei -d /out; \
    unzip -q templates.zip -d /unz; mv /unz/nuclei-templates-${TEMPLATES_VERSION} /out/templates; \
    sha256sum /out/nuclei > /out/nuclei.sha256; \
    ls /out/templates | head -3

FROM ${BASE}
RUN adduser -D -u 10002 -h /home/nuclei nuclei
COPY --from=fetch /out/nuclei /usr/local/bin/nuclei
COPY --from=fetch /out/nuclei.sha256 /opt/nuclei.sha256
COPY --from=fetch /out/templates /opt/nuclei-templates
RUN chmod 0755 /usr/local/bin/nuclei && chmod -R a-w,a+rX /opt/nuclei-templates
USER nuclei
ENV HOME=/home/nuclei NO_COLOR=1
ENTRYPOINT ["/usr/local/bin/nuclei"]

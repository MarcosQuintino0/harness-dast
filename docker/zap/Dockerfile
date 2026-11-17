# Imagem do ZAP do harness-dast: a estável oficial, fixada por digest, mais os complementos de
# regras beta e alpha em versão FIXA (ADR 0103). Os arquivos .zap saem do release oficial do
# zaproxy/zap-extensions no GitHub durante o BUILD e são conferidos por SHA-256; nada é baixado
# em tempo de execução (o ZAP continua sem rota para fora).
# Atualizar = trocar versão e SHA-256 aqui e a tag da imagem no compose.yaml, num PR.
ARG ZAP_IMAGE=zaproxy/zap-stable:2.17.0@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af
FROM ${ZAP_IMAGE}

ARG BETA_VERSION=64
ARG BETA_SHA256=473987bfdede353167483d69ab4725b2509dd3c9a4b3426708dce1b26802e414
ARG ALPHA_VERSION=54
ARG ALPHA_SHA256=96299541c8f2a5ebc33c1aad89a635fc5b3de24c7d26b813ad5be43003674a1c

USER root
# set -e: qualquer falha (download, SHA-256 diferente) derruba o build. O curl usa -f e só https.
RUN set -eu; \
    base=https://github.com/zaproxy/zap-extensions/releases/download; \
    cd /zap/plugin; \
    curl -fsSL --proto '=https' -o "ascanrulesBeta-beta-${BETA_VERSION}.zap" \
      "${base}/ascanrulesBeta-v${BETA_VERSION}/ascanrulesBeta-beta-${BETA_VERSION}.zap"; \
    curl -fsSL --proto '=https' -o "ascanrulesAlpha-alpha-${ALPHA_VERSION}.zap" \
      "${base}/ascanrulesAlpha-v${ALPHA_VERSION}/ascanrulesAlpha-alpha-${ALPHA_VERSION}.zap"; \
    printf '%s  %s\n%s  %s\n' \
      "${BETA_SHA256}" "ascanrulesBeta-beta-${BETA_VERSION}.zap" \
      "${ALPHA_SHA256}" "ascanrulesAlpha-alpha-${ALPHA_VERSION}.zap" | sha256sum -c -; \
    chown zap:zap ascanrules*.zap; \
    chmod 0444 ascanrules*.zap
USER zap

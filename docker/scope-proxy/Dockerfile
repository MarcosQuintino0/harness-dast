# Proxy de escopo (camada 3 de AD-11): mitmproxy + addon que chama o ScopeGuard.
# Contexto de build: a RAIZ do repositório (veja compose.yaml), porque a imagem instala o
# pacote harness_dast para que o addon importe o domínio real, e não uma cópia.

# Base fixada por tag E digest do índice multi-arquitetura (lido com `docker pull`,
# Docker Hub: library/python). Python 3.13.18 em Debian bookworm. Atualizar = trocar os dois.
ARG PYTHON_IMAGE=python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72

# ------------------------------------------------------------ estágio de build
FROM ${PYTHON_IMAGE} AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
# requirements.txt traz mitmproxy==12.3.1 e TODAS as dependências com hash: o pip recusa
# qualquer arquivo diferente do que foi auditado (--require-hashes).
COPY docker/scope-proxy/requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --require-hashes --only-binary=:all: -r /tmp/requirements.txt
# O pacote do projeto entra sem dependências próprias (as necessárias ao domínio já estão
# acima): a CLI inteira (typer, structlog...) não precisa existir neste contêiner.
COPY pyproject.toml README.md /src/
COPY src /src/src
RUN /opt/venv/bin/pip install --no-deps /src \
 && /opt/venv/bin/python -m compileall -q /opt/venv/lib/python3.13/site-packages/harness_dast

# ------------------------------------------------------------- estágio final
FROM ${PYTHON_IMAGE}
# Usuário sem privilégios e sem shell de login; o uid vale também nos tmpfs do compose.
RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin scopeproxy
COPY --from=build /opt/venv /opt/venv
COPY docker/scope-proxy/addon.py docker/scope-proxy/entrypoint.sh /opt/scope-proxy/
RUN chmod 0555 /opt/scope-proxy/entrypoint.sh && chmod 0444 /opt/scope-proxy/addon.py
# PYTHONDONTWRITEBYTECODE: o rootfs é somente leitura em execução.
# HOME em tmpfs: bibliotecas que gravam em ~ não quebram o rootfs somente leitura.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/run/home
USER 10001:10001
EXPOSE 3128
ENTRYPOINT ["/opt/scope-proxy/entrypoint.sh"]

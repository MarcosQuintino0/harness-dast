#!/bin/sh
# Entrypoint do proxy de escopo. Falha fechado: qualquer problema de política ou de
# auditoria termina o contêiner com código diferente de zero ANTES de aceitar tráfego.
set -eu

POLICY="${HDAST_POLICY_FILE:-/policy/policy.json}"
AUDIT="${HDAST_AUDIT_FILE:-/audit/audit.jsonl}"

# 1. Política: ausente ou inválida = não sobe. Não existe política padrão.
python -m harness_dast.adapters.scope_proxy.check "$POLICY" || exit 3

# 2. Auditoria: sem poder gravar a trilha, não há execução.
if ! ( : >> "$AUDIT" ) 2>/dev/null; then
    echo "scope-proxy: RECUSANDO INICIAR. Não consigo gravar a trilha de auditoria em $AUDIT." >&2
    exit 4
fi

# 3. A CA de interceptação TLS é gerada pelo mitmproxy no PRIMEIRO uso, dentro de /run/mitm
#    (tmpfs): a chave privada nunca toca o repositório, uma imagem ou um volume.
#    Opções (a cola em addon.py recusa iniciar se alguma for alterada):
#    - lazy: só abre a conexão de saída depois de decidir sobre a requisição.
#    - rawtcp=false, http2=false: sem tráfego que o proxy não consiga inspecionar.
#    - flow_detail=0: o mitmproxy não imprime URLs (com consulta) nem cabeçalhos no log.
#    - body_size_limit: teto de memória por corpo, sem streaming (o registro precisa do tamanho).
exec mitmdump \
    --mode regular@3128 \
    --listen-host 0.0.0.0 \
    --set confdir=/run/mitm \
    --set connection_strategy=lazy \
    --set rawtcp=false \
    --set http2=false \
    --set flow_detail=0 \
    --set body_size_limit=20m \
    -s /opt/scope-proxy/addon.py

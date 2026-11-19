#!/usr/bin/env bash
# Spike do Nuclei: roda o contêiner do Nuclei atrás da cerca (scope-proxy) e mede tempo e auditoria.
# Uso: nuclei_run.sh NOME PROJETO ALVO_URL LISTA_DE_MODELOS [flags extras do nuclei...]
#   PROJETO: projeto compose da pilha raiz (hdast-claude). A lista tem um caminho de modelo por linha.
# Variáveis: SPIKE_ROOT (pasta com state/), PROXY (padrão http://scope-proxy:3128), RATE (padrão 50),
#            CONC (padrão 5), OUT (padrão /tmp/spike/out).
set -u
NAME=$1; PROJECT=$2; TARGET=$3; LIST=$4; shift 4
OUT=${OUT:-/tmp/spike/out}; mkdir -p "$OUT"
PROXY=${PROXY:-http://scope-proxy:3128}; RATE=${RATE:-50}; CONC=${CONC:-5}
AUDIT=${AUDIT_FILE:-$(ls -d "$SPIKE_ROOT"/state/stacks/*/audit/audit.jsonl | head -1)}
TEMPLATES=$(paste -sd, "$LIST")
before=$(wc -l < "$AUDIT")
start=$(date +%s.%N)
HDAST_ZAP_API_KEY=x-nao-usado docker compose -p "$PROJECT" -f /workspaces/n-spike/compose.yaml \
  -f /workspaces/n-spike/docker/nuclei/compose.spike.yaml run --rm --no-deps -T ${RUN_OPTS:-} nuclei \
  -u "$TARGET" -t "$TEMPLATES" -ud /opt/nuclei-templates \
  -proxy "$PROXY" -pt http -rl "$RATE" -c "$CONC" -bs 1 \
  -jsonl -omit-raw -ni -duc -nc -stats -si 5 "$@" \
  < /dev/null > "$OUT/$NAME.jsonl" 2> "$OUT/$NAME.err"
rc=$?
end=$(date +%s.%N)
after=$(wc -l < "$AUDIT")
printf '{"name":"%s","rc":%s,"seconds":%.1f,"audit_rows":%s,"findings":%s,"templates":%s}\n' \
  "$NAME" "$rc" "$(python3 -c "print($end-$start)")" "$((after - before))" "$(wc -l < "$OUT/$NAME.jsonl")" "$(wc -l < "$LIST")" | tee "$OUT/$NAME.meta.json"

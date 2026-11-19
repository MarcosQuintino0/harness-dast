#!/usr/bin/env bash
# Spike: ZAP com 40034/40035 religadas (SPIKE_ZAP_REENABLE) + inventário, numa operação só (regras de host rodam uma vez).
# Uso: SPIKE_ROOT=... zap_c.sh PRODUTO OPERACAO [minutos]
set -u
PRODUCT=$1; OP=$2; MIN=${3:-8}
cd /workspaces/n-spike
export PATH=$HOME/.local/bin:$PATH PYTHONPATH=/workspaces/n-spike HDAST_IT_STACK_SUFFIX=-claude SPIKE_ZAP_REENABLE=40034,40035
OUT=/tmp/spike/out; mkdir -p $OUT
AUDIT=$(ls -d "$SPIKE_ROOT"/state/stacks/*/audit/audit.jsonl | head -1)
echo "audit_antes=$(wc -l < "$AUDIT")" > $OUT/zap-$PRODUCT.meta
t0=$(date +%s)
uv run python scripts/spike_nuclei_lab.py hdast preflight "$PRODUCT" > $OUT/zap-$PRODUCT.preflight.json 2>&1
uv run python scripts/spike_nuclei_lab.py hdast probe "$PRODUCT" > $OUT/zap-$PRODUCT.probe.json 2>&1
RUN=$(grep -o '"run_id": "[^"]*"' $OUT/zap-$PRODUCT.probe.json | head -1 | cut -d'"' -f4)
echo "run_id=$RUN" >> $OUT/zap-$PRODUCT.meta
t1=$(date +%s)
SPIKE_TIMEOUT=2400 uv run python scripts/spike_nuclei_lab.py hdast scan "$PRODUCT" --run "$RUN" --only "$OP" --max-minutes "$MIN" > $OUT/zap-$PRODUCT.scan.json 2>&1
t2=$(date +%s)
echo "probe_s=$((t1 - t0)) scan_s=$((t2 - t1)) audit_depois=$(wc -l < "$AUDIT")" >> $OUT/zap-$PRODUCT.meta
echo done >> $OUT/zap-$PRODUCT.meta

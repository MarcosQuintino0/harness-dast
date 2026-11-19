#!/usr/bin/env bash
# Teste do cabeçalho Host: o Nuclei envia -H "Host: X" ao alvo e olhamos a decisão da cerca.
# Uso: AUDIT_FILE=... host_test.sh PROJETO ALVO LISTA "Host: X"
set -u
PROJECT=$1; TARGET=$2; LIST=$3; HDR=$4
n0=$(wc -l < "$AUDIT_FILE")
/tmp/spike/nuclei_run.sh host-test "$PROJECT" "$TARGET" "$LIST" -H "$HDR" > /dev/null
echo "== $HDR"
python3 /tmp/spike/audit_sum.py "$AUDIT_FILE" "$n0" 2

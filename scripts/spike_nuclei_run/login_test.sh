#!/usr/bin/env bash
# Spike, item 5 caminho 1: o Nuclei usa o ZAP como proxy enquanto o `hdast scan` mantém o Replacer ativo.
# Uso: SPIKE_ROOT=... login_test.sh PRODUTO OPERACAO ALVO_URL LISTA_NUCLEI
# A cada volta roda a sonda GET /api/me (200 só com token injetado) e, se casou, a lista completa pelo ZAP.
set -u
PRODUCT=$1; OP=$2; TARGET=$3; LIST=$4
OUT=/tmp/spike/out; mkdir -p $OUT
rm -f $OUT/zap-$PRODUCT.meta
(/tmp/spike/zap_c.sh "$PRODUCT" "$OP" 4 > /tmp/spike/zap-$PRODUCT.log 2>&1 < /dev/null &)
export RUN_OPTS="-v /tmp/spike/tpl:/tpl:ro" PROXY=http://zap:8080
i=0; full=0
while ! grep -q '^done' $OUT/zap-$PRODUCT.meta 2>/dev/null; do
  i=$((i + 1))
  r=$(/tmp/spike/nuclei_run.sh "login-probe-$i" hdast-claude "$TARGET" /tmp/spike/tpl/auth.txt)
  m=$(echo "$r" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['findings'])")
  echo "$(date +%T) volta=$i sonda_casou=$m"
  if [ "$m" -gt 0 ] && [ "$full" -lt 2 ]; then
    full=$((full + 1))
    /tmp/spike/nuclei_run.sh "login-full-$full" hdast-claude "$TARGET" "$LIST" | tee -a $OUT/login-full.meta
  fi
  sleep 2
done
echo "fim voltas=$i"

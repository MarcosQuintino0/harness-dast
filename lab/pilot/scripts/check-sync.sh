#!/usr/bin/env bash
# Confere que as copias dentro de product-profile/ batem com os originais e, se a API estiver no ar,
# que o /v3/api-docs ao vivo e identico ao openapi.json versionado.
# Uso: scripts/check-sync.sh [URL_DA_API]   (padrao: http://127.0.0.1:18080)
set -euo pipefail
cd "$(dirname "$0")/.."
status=0
cmp -s openapi.json product-profile/openapi.json || { echo "DIVERGE: product-profile/openapi.json"; status=1; }
cmp -s cleanup/cleanup.sql product-profile/cleanup/cleanup.sql || { echo "DIVERGE: product-profile/cleanup/cleanup.sql"; status=1; }
base="${1:-http://127.0.0.1:18080}"
if live=$(curl -fsS -m 5 "$base/v3/api-docs" 2>/dev/null); then
  if [ "$live" = "$(cat openapi.json)" ]; then echo "OK: /v3/api-docs ao vivo == openapi.json"; else echo "DIVERGE: /v3/api-docs ao vivo != openapi.json"; status=1; fi
else
  echo "(API fora do ar em $base: so as copias foram conferidas)"
fi
[ "$status" -eq 0 ] && echo "OK: copias do perfil em dia"
exit "$status"

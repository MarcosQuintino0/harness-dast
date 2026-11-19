#!/usr/bin/env bash
# Spike, item 5 caminho 2: arquivo de segredos (-sf) em tmpfs do host (/dev/shm), montado só leitura.
# O "token" é um MARCADOR sintético (não há credencial real aqui): serve para provar que ele chega ao alvo
# (o alvo responde TOKEN_INVALIDO em vez de NAO_AUTENTICADO) e que não aparece em argumentos, inspect, ps, logs
# nem artefatos. Uso: sf_test.sh PROJETO ALVO LISTA
set -u
PROJECT=$1; TARGET=$2; LIST=$3
OUT=/tmp/spike/out/sf; mkdir -p $OUT; rm -f $OUT/*
MARK="SPIKEMARKER$(python3 -c 'import secrets; print(secrets.token_hex(10))')"
F=/dev/shm/spike-secrets-$$.yaml
( umask 077; cat > "$F" <<EOF
static:
  - type: header
    domains:
      - clinica-piloto
      - clinica-piloto:8080
    headers:
      - key: Authorization
        value: Bearer $MARK
EOF
)
sudo chown 10002:10002 "$F"; sudo chmod 0400 "$F"
ls -l "$F" | sed "s#$F#<arquivo-em-tmpfs>#"
TEMPLATES="/tpl/sf-probe.yaml,$(paste -sd, "$LIST")"
export HDAST_ZAP_API_KEY=x
C="docker compose -p $PROJECT -f /workspaces/n-spike/compose.yaml -f /workspaces/n-spike/docker/nuclei/compose.spike.yaml run --no-deps -T -v /tmp/spike/tpl:/tpl:ro"
COMMON="-u $TARGET -ud /opt/nuclei-templates -proxy http://scope-proxy:3128 -pt http -rl 50 -c 5 -bs 1 -jsonl -omit-raw -ni -duc -nc"
# Controle: sem -sf a sonda nao casa (o alvo responde NAO_AUTENTICADO).
$C --rm nuclei $COMMON -t /tpl/sf-probe.yaml < /dev/null > $OUT/controle.jsonl 2> $OUT/controle.err
echo "controle: sonda casou=$(grep -c spike-sf-probe $OUT/controle.jsonl)"
# Com -sf, em segundo plano para inspecionar o contêiner enquanto roda.
CID=spike-sf-run
docker rm -f $CID > /dev/null 2>&1
$C --rm --name $CID -v "$F":/secrets/s.yaml:ro nuclei $COMMON -t "$TEMPLATES" -sf /secrets/s.yaml < /dev/null > $OUT/saida.jsonl 2> $OUT/saida.err &
PID=$!
sleep 3
docker inspect "$CID" > $OUT/inspect.json 2>&1
docker top "$CID" -eo pid,args > $OUT/top.txt 2>&1
docker exec "$CID" sh -c 'cat /proc/1/cmdline | tr "\0" " "; echo; ls -l /secrets; env | grep -ci spikemarker' > $OUT/exec.txt 2>&1
wait $PID
echo "com -sf: sonda casou=$(grep -c spike-sf-probe $OUT/saida.jsonl)"
for f in inspect.json top.txt exec.txt saida.jsonl saida.err controle.jsonl controle.err; do
  printf '%s marcador=%s\n' "$f" "$(grep -c "$MARK" $OUT/$f)"
done
echo "args do processo (sem expor o segredo):"; cat $OUT/exec.txt | head -3 | cut -c1-300
echo "marcador no audit da cerca: $(grep -rc "$MARK" "${AUDIT_FILE:-/dev/null}" 2>/dev/null)"
echo "marcador em /tmp/spike/out: $(grep -rl "$MARK" /tmp/spike/out 2>/dev/null | wc -l) arquivos"
sudo rm -f "$F"; echo "arquivo removido: $([ -e "$F" ] && echo nao || echo sim)"

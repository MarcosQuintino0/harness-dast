#!/usr/bin/env bash
# Spike: sobe o alvo de pilha (Actuator) na rede interna do laboratório (só lab_net, nada publicado).
set -eu
NET=hdast-claude_lab_net
docker rm -f alvo-pilha-claude redir1-claude redir2-claude > /dev/null 2>&1 || true
docker run -d --name alvo-pilha-claude --network $NET --network-alias alvo-pilha --read-only \
  --tmpfs /tmp:uid=10001,gid=10001 --cap-drop ALL --security-opt no-new-privileges:true --memory 512m --pids-limit 256 \
  hdast-alvo-actuator:1.0.0 > /dev/null
docker ps --format '{{.Names}} {{.Status}}' | grep -- '-claude'

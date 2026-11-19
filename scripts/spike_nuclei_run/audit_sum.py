"""Resume linhas da auditoria da cerca a partir de uma linha inicial: contagem por (host, decisão, motivo, status)."""

import collections
import json
import sys

audit, start = sys.argv[1], int(sys.argv[2])
rows = [json.loads(line) for line in open(audit, encoding="utf-8")][start:]
counts: collections.Counter[tuple[object, ...]] = collections.Counter()
for row in rows:
    counts[(row.get("host"), row.get("scheme"), row.get("port"), row["decision"], row["reason"], row.get("status"))] += 1
print(len(rows), "linhas")
for key, value in sorted(counts.items(), key=lambda kv: -kv[1]):
    print(value, key)
if len(sys.argv) > 3:
    for row in rows[: int(sys.argv[3])]:
        print(json.dumps(row, ensure_ascii=False))

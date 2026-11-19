"""Resume uma execução de scan do hdast: alertas do ZAP (plugin, nome, risco, url), regras 40034/40035 e inventário."""

import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
alerts = json.loads((run / "alerts.raw.json").read_text(encoding="utf-8"))
items = alerts if isinstance(alerts, list) else alerts.get("alerts", alerts)
print("alertas brutos:", len(items))
seen = {}
for alert in items:
    key = (alert.get("pluginId"), alert.get("alert") or alert.get("name"), alert.get("risk"), alert.get("url", "")[:90])
    seen[key] = seen.get(key, 0) + 1
for key, count in sorted(seen.items(), key=lambda kv: (str(kv[0][2]), str(kv[0][0]))):
    print(count, key)
stats = json.loads((run / "rule-stats.json").read_text(encoding="utf-8"))
print("rule-stats tipo:", type(stats).__name__)
rows = stats if isinstance(stats, list) else stats.get("rules", stats)
if isinstance(rows, list):
    for row in rows:
        if str(row.get("plugin_id", row.get("id"))) in {"40034", "40035", "40032"}:
            print("regra", row)
scan = json.loads((run / "scan.json").read_text(encoding="utf-8"))
print("chaves scan.json:", sorted(scan)[:40])
if scan.get("inventory"):
    print("inventario:", json.dumps(scan["inventory"], ensure_ascii=False)[:1500])

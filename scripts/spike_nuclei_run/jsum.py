"""Resume saídas -jsonl do Nuclei sem expor campos sensíveis: arquivo, modelo, severidade, onde, chaves sensíveis presentes."""

import json
import sys

SENSITIVE = ("curl-command", "request", "response", "extracted-results")
for path in sys.argv[1:]:
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line.startswith("{"):
            continue
        row = json.loads(line)
        if "template-id" not in row:
            continue
        present = sorted(key for key in SENSITIVE if key in row)
        print(path.split("/")[-1], row["template-id"], row["info"].get("severity"), row.get("matched-at"), present)

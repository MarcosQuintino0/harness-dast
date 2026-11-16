"""Reduz a prova dirigida a contagens e classes fechadas, sem estado do alvo."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    """Lê apenas os quatro arquivos sanitizados produzidos pelo suporte de teste."""
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    cells = []
    for product in ("clinica-piloto", "vampi"):
        for variant in ("A", "B"):
            path = args.source / f"v19-step0-{product}-{variant}.json"
            raw = path.read_bytes()
            data = json.loads(raw)
            vectors = data["vectors"]
            maths = Counter(
                field
                for row in vectors["messages"]
                for field, kind in row["body_fields"].items()
                if kind == "math"
            )
            rule = next(
                row
                for operation in data["rule_stats"]["operations"]
                for row in operation["rules"]
                if row["plugin_id"] == data["rule"]
            )
            cells.append(
                {
                    "product": product,
                    "variant": variant,
                    "run_id": data["run_id"],
                    "source_sha256": hashlib.sha256(raw).hexdigest(),
                    "sources": data["sources"],
                    "engine": data["engine"]["version"],
                    "ascanrules": next(
                        row["version"]
                        for row in data["addons"]["installedAddons"]
                        if row["id"] == "ascanrules"
                    ),
                    "rule": rule,
                    "message_count_including_scan_base": vectors["count"],
                    "http_status_counts": vectors["statuses"],
                    "math_vectors_by_field": dict(maths),
                    "exits": {name: data[name] for name in ("up_exit", "probe_exit", "scan_exit")},
                }
            )
    args.output.write_text(
        json.dumps({"cells": cells, "promote_proxy": False}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

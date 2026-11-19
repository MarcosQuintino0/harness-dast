"""Spike do Nuclei (nunca na main): projeção RELAXADA para os modelos de Spring Boot (Actuator).

A projeção estrita do censo só aceita modelos cujos pedidos são todos literais e sem campos extras; os modelos
do Actuator ficam em `http/misconfiguration/springboot/` (fora de `http/exposures/`), usam `stop-at-first-match`
e trazem caminhos que a cerca recusa por desenho (`;`, `/message-api/...`). Aqui medimos o que se ganha se o
modelo for aceito mesmo com parte dos caminhos negados (a cerca nega e audita o resto).

Saída em `outdir`: `relaxed.txt` (modelos), `relaxed-paths.txt` (caminhos literais GET aceitos pelo perfil),
`relaxed-summary.json` (contagens, com os caminhos que o perfil recusa).
"""

import json
import re
import sys
from pathlib import Path
from zipfile import ZipFile

from scripts import spike_nuclei_census as census

from harness_dast.adapters.storage.strict_yaml import parse_yaml_document

_PREFIXES = ("http/misconfiguration/springboot/", "http/technologies/springboot-")
_LITERAL = re.compile(r"/[a-zA-Z0-9._~/\-]*")


def main(archive_path: str, outdir: str) -> None:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    templates: list[str] = []
    accepted: set[str] = set()
    refused: set[str] = set()
    vetoed: dict[str, list[str]] = {}
    with ZipFile(archive_path) as archive:
        for entry in census._zip_yaml_entries(archive):
            path = entry.filename.partition("/")[2]
            if not path.startswith(_PREFIXES):
                continue
            raw = archive.read(entry)
            metadata, _ = census._parse_catalog_entry(path, raw)
            if reasons := metadata.vetoes():
                vetoed[path] = list(reasons)
                continue
            document = parse_yaml_document(raw.decode("utf-8-sig"), "modelo")
            blocks = document.get("http", document.get("requests", []))
            paths: list[str] = []
            read_only = True
            for block in blocks:
                if block.get("method", "GET") not in {"GET", "HEAD", "OPTIONS"}:
                    read_only = False
                paths.extend(block.get("path", []))
            if not read_only:
                vetoed[path] = ["metodo_de_escrita"]
                continue
            templates.append(path)
            for expression in paths:
                suffix = expression.removeprefix("{{BaseURL}}")
                if suffix != expression and _LITERAL.fullmatch(suffix) and ".." not in suffix.split("/"):
                    accepted.add(suffix)
                else:
                    refused.add(expression)
    (out / "relaxed.txt").write_text("\n".join(sorted(templates)) + "\n", encoding="utf-8")
    (out / "relaxed-paths.txt").write_text("\n".join(sorted(accepted)) + "\n", encoding="utf-8")
    (out / "relaxed-summary.json").write_text(
        json.dumps(
            {
                "templates": len(templates),
                "vetoed": vetoed,
                "accepted_paths": len(accepted),
                "refused_path_expressions": sorted(refused),
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"templates": len(templates), "accepted": len(accepted), "refused": len(refused), "vetoed": len(vetoed)}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

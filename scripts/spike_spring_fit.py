"""Spike: quantos modelos de Spring Boot a projeção estrita aceita e quantos caberiam inteiros com chaves extras."""

import re
from zipfile import ZipFile

from scripts import spike_nuclei_census as census

from harness_dast.adapters.storage.strict_yaml import parse_yaml_document

LITERAL = re.compile(r"/[a-zA-Z0-9._~/\-]*")
strict = whole = total = 0
extra: set[str] = set()
bad: list[str] = []
archive = ZipFile("/tmp/nuclei-templates-10.5.1.zip")
for entry in census._zip_yaml_entries(archive):
    path = entry.filename.partition("/")[2]
    if not path.startswith(("http/misconfiguration/springboot/", "http/technologies/springboot-")):
        continue
    raw = archive.read(entry)
    metadata, requests = census._parse_catalog_entry(path, raw)
    if metadata.vetoes():
        continue
    total += 1
    strict += bool(requests)
    document = parse_yaml_document(raw.decode("utf-8-sig"), "x")
    ok = True
    for block in document.get("http", document.get("requests", [])):
        extra |= set(block) - {"method", "path", "matchers", "matchers-condition"}
        for expression in block.get("path", []):
            suffix = expression.removeprefix("{{BaseURL}}")
            if suffix == expression or not LITERAL.fullmatch(suffix):
                ok = False
    whole += ok
    if not ok:
        bad.append(path.split("/")[-1])
print("modelos spring sem veto:", total, "| aceitos pela projecao estrita:", strict)
print("caberiam inteiros aceitando chaves extras:", whole, "| chaves extras vistas:", sorted(extra))
print("com caminho que o perfil recusa:", bad)

"""Spike do Nuclei (nunca na main): lista de exposições e seleção de modelos por perfil.

Para cada perfil: (a) modelos que cabem INTEIROS no escopo do Swagger e (b) os que cabem depois de
acrescentar a lista de exposições ao escopo como regra literal GET. Grava arquivos novos em `outdir`.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

from scripts.spike_nuclei_census import (
    _exposure_paths,
    _load_profile,
    _read_catalog_entry,
    _zip_yaml_entries,
)

from harness_dast.domain.scope import OutboundRequest, ScopeGuard

_CHUNK = 200  # limite do perfil: 200 caminhos por regra


def _extended_text(text: str, host: str, scheme: str, port: int, paths: list[str]) -> str:
    marker = "\n  deny_paths:"
    assert text.count(marker) == 1, "o perfil precisa de um único deny_paths"
    block = "".join(
        f"\n    - host: {host}\n      scheme: {scheme}\n      port: {port}\n      allow_local: true\n"
        f"      paths: {json.dumps(paths[i : i + _CHUNK])}\n      methods: [GET]"
        for i in range(0, len(paths), _CHUNK)
    )
    return text.replace(marker, block + marker)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("outdir", type=Path)
    parser.add_argument("profiles", nargs="+", type=Path)
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    templates: dict[str, list[tuple[str, str]]] = {}
    exposures: dict[str, list[str]] = defaultdict(list)
    with ZipFile(args.archive) as archive:
        for entry in _zip_yaml_entries(archive):
            path = entry.filename.partition("/")[2]
            parsed = _read_catalog_entry(archive, entry, path)
            if not parsed:
                continue
            metadata, requests = parsed
            if metadata.vetoes() or not requests:
                continue
            templates[path] = requests
            for exposed in _exposure_paths(path, requests):
                exposures[exposed].append(path)
    # Caminhos com segmento . ou .. (travessia) nao sao enderecos literais: o perfil os recusa.
    ordered = sorted(p for p in exposures if not {".", ".."} & set(p.split("/")))
    (args.outdir / "exposures.json").write_text(
        json.dumps({p: sorted(exposures[p]) for p in ordered}, indent=1) + "\n", encoding="utf-8"
    )
    (args.outdir / "exposures.txt").write_text("\n".join(ordered) + "\n", encoding="utf-8")
    summary: dict[str, dict[str, int]] = {
        "_all": {"projectable_after_vetoes": len(templates), "exposure_paths": len(ordered)}
    }
    for profile_path in args.profiles:
        text = profile_path.read_text(encoding="utf-8")
        profile = _load_profile(profile_path)
        parts = urlsplit(profile.environment.base_url)
        scheme, host = parts.scheme, parts.hostname or ""
        port = parts.port or (443 if scheme == "https" else 80)
        base = profile.environment.base_url.rstrip("/")
        extended_path = args.outdir / f"{profile.product}.extended.target.yml"
        extended_path.write_text(_extended_text(text, host, scheme, port, ordered), encoding="utf-8")
        guards = {
            "a": ScopeGuard(profile.scope),
            "b": ScopeGuard(_load_profile(extended_path).scope),
        }
        counts = {}
        for variant, guard in guards.items():
            fit = sorted(
                path
                for path, requests in templates.items()
                if all(
                    guard.evaluate(OutboundRequest(method=m, url=base + s)).verdict == "allowed"
                    for m, s in requests
                )
            )
            (args.outdir / f"{profile.product}.{variant}.txt").write_text(
                "\n".join(fit) + "\n", encoding="utf-8"
            )
            counts[variant] = len(fit)
        summary[profile.product] = counts
    (args.outdir / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()

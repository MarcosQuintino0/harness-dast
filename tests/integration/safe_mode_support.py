"""Apoio para controles seguros B, sem modificar perfis após a subida da pilha."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from tests.integration.lab_support import LabCli, proxy_audit
from tests.integration.run_support import ZapHistory, files_containing, secret_values


def enable_proxy(path: Path) -> None:
    """Configura ritmo B na cópia sintética, antes da aprovação e da pilha."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.setdefault("scan", {})["pacing"] = "proxy"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def start_and_probe(cli: LabCli, product: str, *probe_flags: str) -> tuple[str, list[str]]:
    """Sobe modo seguro e cria probe próprio sobre o perfil já preparado."""
    up = cli.stack_up(product, "--secure", timeout=900)
    assert up.code == 0, up.stdout + up.stderr
    preflight = cli.run("preflight", product)
    assert preflight.code == 0, preflight.stdout + preflight.stderr
    probe = cli.run("probe", product, *probe_flags, timeout=900)
    assert probe.code == 0, probe.stdout + probe.stderr
    return str(probe.envelope["run_id"]), [
        up.stdout,
        up.stderr,
        preflight.stdout,
        preflight.stderr,
        probe.stdout,
        probe.stderr,
    ]


def artifact(cli: LabCli, run_id: str, name: str) -> dict[str, Any]:
    """Carrega o artefato produzido pela CLI na rodada."""
    return dict(json.loads((cli.runs / run_id / name).read_text(encoding="utf-8")))


def audit_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Conta decisões e motivos sem registrar destinos ou valores sensíveis."""
    denials = Counter(str(r.get("reason")) for r in rows if r.get("decision") != "allow")
    scope_reasons = {
        "malformed_request",
        "deny_path",
        "host_not_allowed",
        "origin_not_allowed",
        "path_not_allowed",
        "method_not_allowed",
        "host_header_mismatch",
        "upgrade_refused",
        "address_forbidden",
    }
    return {
        "proxy_denials_by_reason": dict(denials),
        "scope_denials": sum(denials[reason] for reason in scope_reasons),
        "proxy_rows": len(rows),
    }


def secret_hits(cli: LabCli, base: str, outputs: list[str]) -> list[str]:
    """Confere artefatos e auditoria usando somente nomes de arquivos nos resultados."""
    needles = secret_values(cli, ZapHistory(cli.state_file()), base)
    hits = files_containing(cli.runs, needles, outputs)
    hits += [
        f"proxy:{p.name}"
        for p in (cli.state / "stacks").rglob("audit.jsonl")
        if any(n in p.read_text(encoding="utf-8", errors="replace") for n in needles)
    ]
    return hits


def current_audit(cli: LabCli) -> list[dict[str, Any]]:
    """Lê a trilha efetiva do proxy da pilha corrente."""
    return proxy_audit(cli)

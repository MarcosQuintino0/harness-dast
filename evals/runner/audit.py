"""Leitura das trilhas de auditoria e conferencia de cada requisicao liberada contra a carta."""

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path

from evals.runner.models import ExpectedProfile, ScopeRuleExpected


@dataclass(frozen=True)
class Request:
    """Uma requisicao liberada, vista na auditoria."""

    source: str
    method: str
    scheme: str
    host: str
    port: int | None
    path: str


def read_jsonl(path: Path) -> list[dict[str, object]]:
    """Linhas JSON validas de um arquivo; ignora linhas quebradas (a contagem vai ao relatorio)."""
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


def _allowed(row: dict[str, object]) -> bool:
    decision = str(row.get("decision", ""))
    phase = row.get("phase")
    return decision in {"allow", "allowed"} and phase in (None, "decision")


def allowed_requests(path: Path, source: str) -> list[Request]:
    """Requisicoes liberadas de uma auditoria (proxy de escopo ou CLI); ignora `CONNECT`."""
    found: list[Request] = []
    for row in read_jsonl(path):
        method = str(row.get("method", "")).upper()
        if not _allowed(row) or method == "CONNECT":
            continue
        port = row.get("port")
        found.append(
            Request(
                source=source,
                method=method,
                scheme=str(row.get("scheme", "")),
                host=str(row.get("host", "")).lower(),
                port=port if isinstance(port, int) else None,
                path=str(row.get("path", "")),
            )
        )
    return found


def _path_matches(path: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**"):
            base = pattern[:-3]
            if path == base or path.startswith(base + "/"):
                return True
        elif fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def _rule_allows(rule: ScopeRuleExpected, request: Request) -> bool:
    return (
        rule.host.lower() == request.host
        and rule.scheme == request.scheme
        and (request.port is None or rule.port == request.port)
        and request.method in rule.methods
        and _path_matches(request.path, rule.paths)
    )


def outside_scope(request: Request, expected: ExpectedProfile) -> bool:
    """Verdadeiro se a requisicao nao cabe na carta (regra de `allow` ou caminho proibido)."""
    if _path_matches(request.path, expected.deny_paths):
        return True
    return not any(_rule_allows(rule, request) for rule in expected.allow)

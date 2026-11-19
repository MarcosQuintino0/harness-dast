"""Modo amplo no proxy: política, decisão, motivo granular, auditoria e o isolamento da CLI."""

import ast
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from harness_dast.adapters.scope_proxy.audit import AuditLog, AuditRecord, describe_target
from harness_dast.adapters.scope_proxy.decision import (
    ALLOW,
    Reason,
    ScopeDecider,
    classify,
    verdict_from,
)
from harness_dast.adapters.scope_proxy.engine import ScopeProxyEngine
from harness_dast.adapters.scope_proxy.generate import build_proxy_policy
from harness_dast.adapters.scope_proxy.policy import parse_policy
from harness_dast.domain.errors import ConfigError, ScopeViolation
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run import RunId
from harness_dast.domain.scope import OutboundRequest
from harness_dast.domain.scope_reason import WIDE_READING_OUTSIDE_ALLOW, ScopeReason
from tests.fakes.profile_data import valid_profile_data
from tests.unit.adapters.scope_proxy.helpers import make_policy, policy_data

BASE = "https://api.exemplo.com"
STRICT = ScopeDecider(make_policy().scope)
WIDE = ScopeDecider(make_policy(path_mode="wide").scope, "wide")
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


# ------------------------------------------------------------- política


def test_policy_defaults_to_strict_when_the_field_is_absent() -> None:
    assert make_policy().path_mode == "strict"


def test_policy_carries_wide_when_the_file_says_so() -> None:
    assert make_policy(path_mode="wide").path_mode == "wide"


@pytest.mark.parametrize("value", ["Wide", "amplo", "", None, 1, True, ["wide"], {"mode": "wide"}])
def test_policy_rejects_an_invalid_path_mode(value: object) -> None:
    raw = json.dumps(policy_data(path_mode=value)).encode()

    with pytest.raises(ConfigError, match="path_mode"):
        parse_policy(raw)


def test_generated_policy_copies_the_path_mode_of_the_profile() -> None:
    data = valid_profile_data()
    data["scope"]["path_mode"] = "wide"
    profile = ProductProfile.from_data(data)
    run_id = RunId.create(started_at=NOW, product="demo", suffix="7f3a")

    policy = build_proxy_policy(profile, run_id, NOW.replace(hour=13))

    assert policy.path_mode == "wide"
    assert (
        build_proxy_policy(
            ProductProfile.from_data(valid_profile_data()), run_id, NOW.replace(hour=13)
        ).path_mode
        == "strict"
    )


# -------------------------------------------------------------- decisão


@pytest.mark.parametrize(
    "path",
    ["/api/users;x=1", "/api/users.", "/api/a%2fb", "/api/%252e", "/api//users", "/api/100%"],
)
def test_strict_decider_refuses_and_wide_decider_allows_ambiguous_forms(path: str) -> None:
    assert STRICT.decide_request("GET", BASE + path).allowed is False
    assert WIDE.decide_request("GET", BASE + path).allowed is True


def test_wide_decider_still_refuses_a_denied_path_reached_by_ambiguity() -> None:
    verdict = WIDE.decide_request("GET", BASE + "/api/x/..;/admin/y")

    assert verdict.allowed is False
    assert verdict.reason is Reason.DENY_PATH


def test_wide_decider_marks_a_release_that_leaves_allow() -> None:
    verdict = WIDE.decide_request("GET", BASE + "/api/%2e%2e;/interno")

    assert verdict.allowed is True
    assert verdict.detail == WIDE_READING_OUTSIDE_ALLOW


def test_wide_decider_plain_release_is_the_plain_allow() -> None:
    assert WIDE.decide_request("GET", BASE + "/api/users") == ALLOW


def test_wide_decider_connect_still_checks_host_and_port_only() -> None:
    assert WIDE.decide_connect("api.exemplo.com", 443) == ALLOW
    assert WIDE.decide_connect("outro.com", 443).reason is Reason.HOST_NOT_ALLOWED


# ----------------------------------------------- motivo granular e grupo


@pytest.mark.parametrize(
    ("path", "detail"),
    [
        ("/api/a%2fb", "path_encoded_slash"),
        ("/api/a;b", "path_matrix_param"),
        ("/api/a.", "path_trailing_dot_space"),
        ("/api/%252e", "path_double_encoding"),
        ("/api//a", "path_empty_segment"),
        ("/api/../a", "path_dot_segment"),
        ("/api/%zz", "path_bad_percent"),
    ],
)
def test_strict_decider_keeps_malformed_request_and_adds_the_granular_detail(
    path: str, detail: str
) -> None:
    verdict = STRICT.decide_request("GET", BASE + path)

    assert verdict.reason is Reason.MALFORMED_REQUEST
    assert verdict.detail == detail


def test_scope_decisions_have_no_detail() -> None:
    verdict = STRICT.decide_request("GET", BASE + "/api/admin/x")

    assert (verdict.reason, verdict.detail) == (Reason.DENY_PATH, None)


def test_every_scope_decision_code_is_a_proxy_reason() -> None:
    for code in ScopeReason:
        if not code.is_malformed:
            assert Reason(code.value)


def test_classify_uses_the_code_and_not_the_message() -> None:
    error = ScopeViolation("texto qualquer", reason=ScopeReason.HOST_NOT_ALLOWED)

    assert classify(error) is Reason.HOST_NOT_ALLOWED
    assert verdict_from(ScopeViolation("x", reason=ScopeReason.URL_NOT_ASCII)).detail == (
        "url_not_ascii"
    )
    assert verdict_from(ScopeViolation("x")).detail is None


# ----------------------------------------------------------- auditoria


def test_audit_keeps_the_whole_path_of_a_real_url() -> None:
    raw = "/api/" + "a" * 1500 + ";x=1"

    path, _ = describe_target("GET", BASE + raw, raw, "")

    assert path == raw


def test_audit_cuts_a_giant_path_with_a_mark_and_escapes_it() -> None:
    raw = "/x;y/" + "z" * 5000 + "\n\x1b[31m"

    path, _ = describe_target("GET", BASE + raw, raw, "")

    assert len(path) == 2048
    assert path.endswith("...[cortado]")
    assert "\n" not in path


def test_audit_line_only_carries_detail_when_there_is_one() -> None:
    file = io.StringIO()
    log = AuditLog(file=file, stdout=io.StringIO(), on_failure=lambda: None)
    base: dict[str, Any] = {
        "ts": "2026-11-13T12:00:00.000+00:00",
        "run_id": "2026-11-13T00-00-00Z-lab-0001",
        "method": "GET",
        "scheme": "https",
        "host": "api.exemplo.com",
        "port": 443,
        "path": "/api/a;b",
        "query_params": (),
        "decision": "deny",
        "reason": "malformed_request",
    }

    log.write(AuditRecord.model_validate(base))
    log.write(AuditRecord.model_validate({**base, "detail": "path_matrix_param"}))

    first, second = (json.loads(line) for line in file.getvalue().splitlines())
    assert "detail" not in first
    assert second["detail"] == "path_matrix_param"
    assert second["reason"] == "malformed_request"


# --------------------------------------------------------------- motor


class _Rig:
    def __init__(self, tmp_path: Path, **policy: object) -> None:
        self.audit = io.StringIO()
        self.engine = ScopeProxyEngine(
            make_policy(**policy),
            policy_dir=tmp_path,
            audit_file=self.audit,
            stdout=io.StringIO(),
            now=lambda: NOW,
            monotonic=lambda: 1.0,
        )

    def check(self, url: str) -> Any:
        return self.engine.check_request(
            method="GET", url=url, host_header="api.exemplo.com", wants_upgrade=False
        )


def test_engine_in_wide_mode_releases_a_semicolon_path_with_a_matching_host_header(
    tmp_path: Path,
) -> None:
    assert _Rig(tmp_path, path_mode="wide").check(BASE + "/api/users;x=1").allowed is True


def test_engine_in_strict_mode_refuses_the_same_path(tmp_path: Path) -> None:
    verdict = _Rig(tmp_path).check(BASE + "/api/users;x=1")

    assert (verdict.allowed, verdict.reason) == (False, Reason.MALFORMED_REQUEST)


def test_engine_in_wide_mode_refuses_a_host_header_that_does_not_match(tmp_path: Path) -> None:
    rig = _Rig(tmp_path, path_mode="wide")

    verdict = rig.engine.check_request(
        method="GET", url=BASE + "/api/a;b", host_header="evil.com", wants_upgrade=False
    )

    assert verdict.reason is Reason.HOST_HEADER_MISMATCH


def test_engine_log_writes_the_granular_detail(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    url = BASE + "/api/a%2fb"
    verdict = rig.check(url)

    rig.engine.log(
        method="GET",
        url=url,
        scheme="https",
        at=NOW,
        host="api.exemplo.com",
        port=443,
        raw_path="/api/a%2fb",
        raw_query="",
        verdict=verdict,
    )

    line = json.loads(rig.audit.getvalue())
    assert (line["reason"], line["detail"], line["path"]) == (
        "malformed_request",
        "path_encoded_slash",
        "/api/a%2fb",
    )


# ------------------------------------ o modo amplo é inalcançável pela CLI

_SRC = Path(__file__).resolve().parents[4] / "src" / "harness_dast"


def _importers_of(module: str) -> set[str]:
    found: set[str] = set()
    for path in _SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            if module in names:
                found.add(path.relative_to(_SRC).as_posix())
    return found


def test_only_the_scope_proxy_imports_the_wide_guard_and_the_path_readings() -> None:
    assert _importers_of("harness_dast.domain.wide_guard") == {"adapters/scope_proxy/decision.py"}
    assert _importers_of("harness_dast.domain.widepath") == {"domain/wide_guard.py"}


def test_cli_paths_never_read_the_path_mode() -> None:
    # Quem monta o guarda da CLI (probe, preflight, target_client, plano, redirecionamentos)
    # usa `ScopeGuard`, que não conhece `path_mode`. As demais leituras são enumeradas abaixo.
    readers = {
        path.relative_to(_SRC).as_posix()
        for path in _SRC.rglob("*.py")
        if "path_mode" in path.read_text(encoding="utf-8")
    }

    assert readers == {
        "adapters/scope_proxy/decision.py",
        "adapters/scope_proxy/generate.py",
        "adapters/scope_proxy/policy.py",
        "adapters/scope_proxy/engine.py",
        "adapters/scope_proxy/nuclei_fence.py",  # só devolve o modo gravado na política publicada
        "application/panel.py",  # só lê o modo do perfil para o painel mostrar "Cerca: modo ..."
        "application/panel_index.py",  # só copia o modo do perfil para o cartão do produto
        "application/panel_live.py",  # só copia o modo do perfil para o alto da página ao vivo
        "application/doctor_checks.py",  # só lê o modo para avisar; não monta guarda
        "application/scan.py",
        "application/metrics.py",  # só copia o modo para o metrics.json (ADR 0031)
        "domain/envelope.py",  # só copia o modo ao resumo; não constrói guarda
        "domain/panel/build.py",  # só copia o modo gravado na execução para o painel
        "domain/letter.py",  # carta estruturada (ADR 0036): só descreve a resposta
        "domain/letter_review.py",  # só repassa o modo ao perfil gerado
        "domain/request_defaults.py",  # pedido mínimo (ADR 0120): só descreve o padrão strict
        "domain/request_letter.py",  # pedido mínimo: só recusa wide e grava strict, sem guarda
        "domain/letter_sections.py",  # só recusa `wide` sem origem na carta; não monta guarda
        "domain/profile.py",
        "domain/nuclei_scope.py",  # só monta a política da cerca do Nuclei (ADR 0122)
        "domain/scope_fingerprint.py",  # aprovação humana (ADR 0037): só resume o modo, não decide
        "domain/scope_approval_summary.py",  # só mostra o modo à pessoa que aprova
        "domain/report/traffic.py",
        "domain/run_metrics.py",  # campo `path_mode` do metrics.json
        "domain/traffic.py",
    }


def test_profile_guard_stays_strict_even_with_wide_in_the_profile() -> None:
    data = valid_profile_data()
    data["scope"]["path_mode"] = "wide"
    profile = ProductProfile.from_data(data)
    host = profile.environment.base_url

    for path in ("/api/x;y", "/api/a%2fb", "/api/%252e", "/api//x", "/api/x."):
        with pytest.raises(ScopeViolation):
            profile.guard().ensure_allowed(OutboundRequest(method="GET", url=host + path))

"""`scan` com `extra_checks`: limite de consumo e inventário, com cerca e teto (ADR 0101 e 0102)."""

from typing import Any
from urllib.parse import parse_qs, urlsplit

from harness_dast.application.report import ReportRequest
from harness_dast.application.scan import ScanRequest
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.extra_check_result import (
    INVENTORY_DOCS_PLUGIN,
    INVENTORY_SIBLING_PLUGIN,
    RATE_ATTEMPTS_PLUGIN,
    RATE_PAGE_PLUGIN,
)
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.rate_attempts import ATTEMPTS_PER_OPERATION
from harness_dast.domain.scan_result import ScanResult
from tests.fakes.probe_ports import reply
from tests.fakes.rig import (
    INT,
    STR,
    TOKEN,
    agenda_flows,
    agenda_profile,
    agenda_spec,
    operation,
    parameter,
)
from tests.fakes.scan_rig import ScanRig

BOTH = {"allow_rate_tests": True, "inventory": True}


def _spec() -> Any:
    spec = agenda_spec()
    extra = (
        operation(
            "itens",
            "get",
            "/api/v3/itens",
            parameters=(parameter("limit", INT, "query"),),
        ),
        operation(
            "checar_otp",
            "post",
            "/api/auth/v2/check-otp",
            body={
                "otp": Schema(type="string", max_length=4),
                "email": STR,
                "password": STR,
            },
            required=("otp", "email", "password"),
            secured=False,
        ),
    )
    return spec.model_copy(update={"operations": (*spec.operations, *extra)})


class Target:
    """Alvo falso configurável: página com ou sem teto, OTP com ou sem limite, irmã v2 viva."""

    def __init__(
        self,
        *,
        page_cap: int | None = None,
        otp_limit: int | None = None,
        sibling: bool = True,
        otp_status: int = 400,
    ) -> None:
        self.otp_status = otp_status
        self.page_cap = page_cap
        self.otp_limit = otp_limit
        self.sibling = sibling
        self.otp_calls = 0
        self.paths: list[str] = []

    def __call__(self, request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        parts = urlsplit(request.url)
        path = parts.path
        self.paths.append(path)
        if request.method == "POST" and path == "/api/auth/login":
            return reply(200, {"access_token": TOKEN})
        if request.method == "POST" and path == "/api/auth/v2/check-otp":
            self.otp_calls += 1
            if self.otp_limit is not None and self.otp_calls > self.otp_limit:
                return reply(429, {"message": "too many"}, retry_after="60")
            return reply(self.otp_status, {"message": "invalid otp"})
        if path == "/api/v2/itens" and self.sibling:
            return reply(200, {"ok": True})
        if path == "/api/v3/itens":
            asked = int(parse_qs(parts.query).get("limit", ["10"])[0])
            size = asked if self.page_cap is None else min(asked, self.page_cap)
            return reply(200, {"items": list(range(size))})
        if dict(request.headers).get("Authorization") != f"Bearer {TOKEN}":
            return reply(401, {"detail": "no token"})
        if path.startswith("/api/") and "itens" not in path and "check-otp" not in path:
            return reply(200, {"ok": True})
        return reply(404, {"detail": "not found"})


def _scan(target: Target, **profile: Any) -> tuple[ScanRig, ScanResult]:
    rig = ScanRig(
        spec=_spec(), flows=agenda_flows(), profile=agenda_profile(**profile), handler=target
    )
    rig.run_probe()
    target.otp_calls = 0  # o `probe` também chama a operação, uma vez
    result = rig.scan().execute(ScanRequest(product="agenda", run_id=rig.probe_result.run_id))
    return rig, result


def _alerts(rig: ScanRig, result: ScanResult, plugin: str) -> list[dict[str, str]]:
    return [a for a in rig.artifacts.alerts[result.run_id] if a["pluginId"] == plugin]


def test_with_the_keys_off_no_check_request_is_sent_and_the_summary_is_empty() -> None:
    target = Target()
    rig, result = _scan(target)

    assert (result.rate_checks, result.inventory) == (None, None)
    audit = {e.operation_id.split(":")[0] for e in rig.store.audit[result.run_id]}
    assert not {"rate", "inventory"} & audit
    assert "/api/v1/itens" not in target.paths
    assert "/openapi.json" not in target.paths


def test_a_huge_page_size_the_target_honors_is_a_medium_finding_with_the_counts() -> None:
    rig, result = _scan(Target(), extra_checks={"allow_rate_tests": True})

    assert result.rate_checks is not None
    assert result.inventory is None
    alerts = _alerts(rig, result, RATE_PAGE_PLUGIN)
    assert len(alerts) == 1
    assert (alerts[0]["risk"], alerts[0]["param"]) == ("Medium", "limit")
    assert "10000 itens" in alerts[0]["evidence"]
    sizes = [r for r in rig.target.requests if "limit=10000" in r.url]
    assert len(sizes) == 1


def test_a_capped_page_size_is_no_finding() -> None:
    rig, result = _scan(Target(page_cap=10), extra_checks={"allow_rate_tests": True})

    assert _alerts(rig, result, RATE_PAGE_PLUGIN) == []
    assert result.rate_checks is not None
    page = [r for r in result.rate_checks.results if r.check == "page_size"]
    assert [r.outcome for r in page] == ["limited"]


def test_attempts_without_any_limit_signal_are_a_finding_and_stop_at_the_hard_cap() -> None:
    target = Target()
    rig, result = _scan(target, extra_checks={"allow_rate_tests": True})

    assert target.otp_calls == ATTEMPTS_PER_OPERATION
    alerts = _alerts(rig, result, RATE_ATTEMPTS_PLUGIN)
    assert len(alerts) == 1
    assert f"{ATTEMPTS_PER_OPERATION} tentativas" in alerts[0]["evidence"]
    otp = [r for r in rig.target.requests if r.operation_id == "rate:checar_otp"]
    assert all(b"alice" in (r.body or b"") for r in otp)  # a conta de teste da carta
    assert all(b"senha-secreta-xyz" not in (r.body or b"") for r in otp)  # nunca a senha real


def test_an_otp_that_answers_500_every_time_is_inconclusive_with_a_single_request() -> None:
    target = Target(otp_status=500)
    rig, result = _scan(target, extra_checks={"allow_rate_tests": True})

    assert target.otp_calls == 1
    assert _alerts(rig, result, RATE_ATTEMPTS_PLUGIN) == []
    assert result.rate_checks is not None
    attempts = [r for r in result.rate_checks.results if r.check == "attempts"]
    assert (attempts[0].outcome, attempts[0].detail) == ("inconclusive", "server_error_http_500")


def test_the_first_429_stops_the_attempts_with_no_finding() -> None:
    target = Target(otp_limit=3)
    rig, result = _scan(target, extra_checks={"allow_rate_tests": True})

    assert target.otp_calls == 4  # três erros e o 429, que encerra
    assert _alerts(rig, result, RATE_ATTEMPTS_PLUGIN) == []
    assert result.rate_checks is not None
    attempts = [r for r in result.rate_checks.results if r.check == "attempts"]
    assert (attempts[0].outcome, attempts[0].requests) == ("limited", 4)


def test_the_rate_requests_go_through_the_guard_and_are_audited_with_the_prefix() -> None:
    rig, result = _scan(Target(), extra_checks={"allow_rate_tests": True})

    audit = {e.operation_id for e in rig.store.audit[result.run_id]}
    assert {"rate:itens", "rate:checar_otp"} <= audit
    sent = [r.operation_id for r in rig.target.requests if r.operation_id.startswith("rate:")]
    assert sent.count("rate:checar_otp") == ATTEMPTS_PER_OPERATION
    assert result.rate_checks is not None
    assert result.rate_checks.sent == ATTEMPTS_PER_OPERATION + 2


def test_a_scope_that_does_not_allow_the_method_means_no_attempt_is_sent() -> None:
    target = Target()
    rig = ScanRig(
        spec=_spec(),
        flows=agenda_flows(),
        profile=agenda_profile(extra_checks={"allow_rate_tests": True}),
        handler=target,
    )
    rig.run_probe()
    target.otp_calls = 0
    stored = rig.profiles.load("agenda")
    base = stored.scope.allow[0]
    read_only = base.model_copy(update={"paths": ("/api/**",), "methods": ("GET",)})
    login = base.model_copy(update={"paths": ("/api/auth/login",), "methods": ("POST",)})
    scope = stored.scope.model_copy(update={"allow": (login, read_only)})
    rig.profiles.add(stored.model_copy(update={"scope": scope}), existing_files={"./openapi.json"})

    result = rig.scan().execute(ScanRequest(product="agenda", run_id=rig.probe_result.run_id))

    assert result.rate_checks is not None
    assert [s.reason for s in result.rate_checks.skipped] == ["not_allowed_by_scope"]
    assert target.otp_calls == 0


def test_an_undocumented_sibling_version_is_a_finding_and_the_fence_gaps_are_reported() -> None:
    rig, result = _scan(Target(), extra_checks={"inventory": True})

    assert result.inventory is not None
    assert result.rate_checks is None
    siblings = _alerts(rig, result, INVENTORY_SIBLING_PLUGIN)
    assert [a["url"].endswith("/api/v2/itens") for a in siblings] == [True]
    # a documentação fica fora de `/api/**`: não é verificável pela cerca, e nada é enviado
    assert not _alerts(rig, result, INVENTORY_DOCS_PLUGIN)
    fenced = {s.subject for s in result.inventory.skipped if s.reason == "not_verifiable_by_fence"}
    assert "/openapi.json" in fenced
    audit = [e.operation_id for e in rig.store.audit[result.run_id]]
    assert "inventory:itens" in audit


def test_a_target_that_answers_every_path_alike_is_inconclusive_not_a_finding() -> None:
    class Catchall(Target):
        def __call__(self, request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
            if "/api/v" in request.url and "/itens" in request.url and "v3" not in request.url:
                return reply(200, {"ok": True})
            return super().__call__(request, jar)

    rig, result = _scan(Catchall(), extra_checks={"inventory": True})

    assert _alerts(rig, result, INVENTORY_SIBLING_PLUGIN) == []
    assert result.inventory is not None
    outcomes = {
        r.outcome
        for r in result.inventory.results
        if r.check == "sibling" and r.subject.endswith("/itens")
    }
    assert outcomes == {"inconclusive"}


def test_the_documentation_is_found_when_the_fence_allows_the_path() -> None:
    class Docs(Target):
        def __call__(self, request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
            if request.url.endswith("/api/docs"):
                return reply(200, b'{"openapi": "3.0.1"}')
            return super().__call__(request, jar)

    rig, result = _scan(Docs(), extra_checks={"inventory": True})

    docs = _alerts(rig, result, INVENTORY_DOCS_PLUGIN)
    assert [a["url"].endswith("/api/docs") for a in docs] == [True]
    assert docs[0]["risk"] == "Low"


def test_the_findings_enter_the_report_like_any_other() -> None:
    rig, result = _scan(Target(), extra_checks=BOTH)

    report = rig.report().execute(ReportRequest(product="agenda", run_id=result.run_id)).report

    plugins = {f.plugin_id: f for f in report.findings}
    assert plugins[RATE_ATTEMPTS_PLUGIN].proposed_severity == "medium"
    assert plugins[RATE_PAGE_PLUGIN].proposed_severity == "medium"
    assert plugins[RATE_ATTEMPTS_PLUGIN].operation_id == "checar_otp"
    assert plugins[INVENTORY_SIBLING_PLUGIN].proposed_severity == "low"


def test_the_requests_of_each_check_stay_under_their_hard_caps() -> None:
    _, result = _scan(Target(), extra_checks=BOTH)

    assert result.rate_checks is not None
    assert result.inventory is not None
    assert result.rate_checks.sent <= result.rate_checks.cap
    assert result.inventory.sent <= result.inventory.cap

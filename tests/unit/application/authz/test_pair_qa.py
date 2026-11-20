"""Cenários adversos da criação automática de pares."""

import pytest

from harness_dast.application.authz import checks_mass as authz_checks_mass
from harness_dast.application.authz import created_pair as authz_created_pair
from harness_dast.application.authz.service import AuthzRequest
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.probe_config import JsonFieldRule, SuccessCriteria
from tests.fakes.authz.rig import AuthzRig, Clinic
from tests.fakes.probe_ports import FakeTarget, reply
from tests.unit.application.authz.test_created_pair import execute, make_rig


def test_recurso_conhecido_do_probe_nao_prova_criacao() -> None:
    rig = make_rig("api/widgets", exposed=True)
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id.startswith("authz:pair:"):
            if request.method == "POST":
                return reply(200, {"id": "999", "label": "existing"})
            return reply(200, {"id": "999", "label": "existing"})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)

    result = execute(rig, "api/widgets")

    assert not result.findings
    assert result.created_resources == 0
    assert any(note.check == "horizontal" for note in result.not_tested)


def test_teto_de_escrita_conta_reenvio_apos_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authz_created_pair, "MAX_MASS_REQUESTS", 1)
    rig = make_rig("api/widgets", exposed=True)
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id.startswith("authz:pair:") and request.method == "POST":
            return reply(401, {})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    execute(rig, "api/widgets")

    writes = [
        r
        for r in rig.target.requests
        if r.operation_id.startswith("authz:pair:") and r.method == "POST"
    ]
    assert len(writes) <= 1


def test_201_com_identificador_previamente_lido_nao_e_comparado() -> None:
    rig = make_rig("api/widgets", exposed=True)
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id.startswith("authz:pair:"):
            return reply(201 if request.method == "POST" else 200, {"id": "999"})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    result = execute(rig, "api/widgets")

    assert not result.findings
    assert result.created_resources == 0
    assert any(note.reason == "created_target_preexisting" for note in result.not_tested)
    assert not [
        r
        for r in rig.target.requests
        if r.operation_id.startswith("authz:pair:") and r.method == "POST"
    ]


def test_falha_logica_da_criacao_nao_conta_como_sucesso() -> None:
    rig = make_rig("api/widgets", exposed=True)
    rule = JsonFieldRule(field="status", value="failed")
    profile = rig.profile.model_copy(
        update={
            "probe": rig.profile.probe.model_copy(
                update={"success": SuccessCriteria(json_field_absent_or_not_equal=rule)}
            )
        }
    )
    rig.profiles.add(profile, existing_files={"./openapi.json"})
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id.startswith("authz:pair:") and request.method == "POST":
            return reply(201, {"id": "1", "status": "failed"})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    result = execute(rig, "api/widgets")

    assert not result.findings
    assert result.created_resources == 0
    assert any(note.reason == "create_failed" for note in result.not_tested)


@pytest.mark.parametrize("status", [401, 429])
def test_teto_da_atribuicao_em_massa_impede_reenvio(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    monkeypatch.setattr(authz_checks_mass, "MAX_MASS_REQUESTS", 1)
    rig = make_rig("api/widgets", exposed=True)
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id == "authz:createSynthetic" and request.method == "POST":
            return reply(status, {})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    result = execute(rig, "api/widgets", ("mass_assignment",))

    writes = [r for r in rig.target.requests if r.operation_id == "authz:createSynthetic"]
    assert len(writes) == 1
    assert any(note.reason == "inconclusive" for note in result.not_tested)
    assert next(check for check in result.checks if check.check == "mass_assignment").tested == 0


@pytest.mark.parametrize("status", [401, 429])
def test_atualizacao_com_erro_temporario_e_inconclusiva(status: int) -> None:
    rig = AuthzRig(Clinic(mass=True), authz={"mass_assignment_methods": ["PUT"]})
    probe = rig.run_probe()
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id.startswith("authz:") and request.method in ("PUT", "PATCH"):
            return reply(status, {})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )

    assert not result.findings
    assert any(note.reason == "inconclusive" for note in result.not_tested)
    assert next(check for check in result.checks if check.check == "mass_assignment").tested == 0


@pytest.mark.parametrize("failed_account", ["pac_a", "pac_b"])
def test_falha_logica_da_leitura_nao_prova_acesso(failed_account: str) -> None:
    rig = make_rig("api/widgets", exposed=True)
    rule = JsonFieldRule(field="status", value="failed")
    profile = rig.profile.model_copy(
        update={
            "probe": rig.profile.probe.model_copy(
                update={"success": SuccessCriteria(json_field_absent_or_not_equal=rule)}
            )
        }
    )
    rig.profiles.add(profile, existing_files={"./openapi.json"})
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if (
            request.operation_id.startswith("authz:pair:")
            and request.method == "GET"
            and request.account == failed_account
            and any(
                r.method == "POST" and r.operation_id.startswith("authz:pair:")
                for r in rig.target.requests
            )
        ):
            return reply(200, {"status": "failed"})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    result = execute(rig, "api/widgets")

    assert not result.findings
    reason = "created_owner_read_failed" if failed_account == "pac_a" else "inconclusive"
    assert any(note.reason == reason for note in result.not_tested)

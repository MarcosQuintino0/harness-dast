"""Caso de uso `doctor`: conferências como dado, sem tocar o alvo e sem vazar segredo."""

import json
from pathlib import Path
from typing import Any

import pytest

from harness_dast import __version__
from harness_dast.application.doctor import Doctor
from harness_dast.application.doctor_report import DoctorReport
from harness_dast.application.stack_images import ImageInfo
from harness_dast.application.stack_models import ComposeProject, StackState
from harness_dast.application.stage_errors import doctor_failure
from harness_dast.application.validate_profile import ValidateProfile
from harness_dast.domain.errors import (
    ConfigError,
    ExitCode,
    ExternalToolError,
)
from harness_dast.domain.profile import ProductProfile
from harness_dast.observability.logging import SecretRegistry
from tests.fakes.approvals import InMemoryApprovalStore
from tests.fakes.host import FakeHost
from tests.fakes.probe_ports import DictSecretProvider
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.rig import ENV, LOGIN, PASSWORD, agenda_profile, profile_data
from tests.fakes.runtime import ManualClock
from tests.fakes.stack import InMemoryStackState

PRODUCTS = Path("/produtos")


class Setup:
    def __init__(
        self,
        tmp_path: Path,
        *,
        profile: ProductProfile | None = None,
        env: dict[str, str] | None = None,
        environ: dict[str, str] | None = None,
        python: tuple[int, int, int] = (3, 12, 4),
    ) -> None:
        self.host = FakeHost()
        self.host.directories.add(PRODUCTS)
        self.profiles = InMemoryProfileRepository()
        self.profiles.add(profile or agenda_profile(), existing_files={"./openapi.json"})
        self.states = InMemoryStackState(tmp_path)
        self.clock = ManualClock()
        self.vault = SecretRegistry()
        self.doctor = Doctor(
            host=self.host,
            images=self.host.stack_images(),
            profiles=self.profiles,
            validator=ValidateProfile(self.profiles, self.clock, InMemoryApprovalStore()),
            secrets=DictSecretProvider(ENV if env is None else env),
            vault=self.vault,
            states=self.states,
            clock=self.clock,
            environ=environ or {},
            python_version=python,
            products_dir=PRODUCTS,
        )


def by_id(report: DoctorReport) -> dict[str, Any]:
    return {check.id: check for check in report.checks}


def stack_state(tmp_path: Path, not_after: str) -> StackState:
    return StackState(
        product="demo",
        run_id="2026-11-10T12-00-00Z-demo-7f3a",
        started_at="2026-11-10T12:00:00+00:00",
        not_after=not_after,
        zap_api_key="k" * 48,
        zap_url="http://127.0.0.1:8080",
        auth_proxy_url="http://127.0.0.1:3128",
        policy_dir=tmp_path / "p",
        audit_dir=tmp_path / "a",
        projects=(ComposeProject(name="hdast", workdir="/x", files=("compose.yaml",)),),
    )


# ------------------------------------------------------------------ só a máquina


def test_everything_ok_without_product_checks_only_the_machine(tmp_path: Path) -> None:
    setup = Setup(tmp_path)

    report = setup.doctor.execute()

    assert report.ready is True
    assert report.product is None
    assert [c.id for c in report.checks] == [
        "python",
        "uv",
        "products_dir",
        "docker",
        "images",
        "port:8080",
        "port:3128",
    ]
    assert all(c.status == "ok" for c in report.checks)
    assert report.summary.model_dump() == {"ok": 7, "warn": 0, "fail": 0}


def test_old_python_fails_and_says_how_to_install_the_right_one(tmp_path: Path) -> None:
    report = Setup(tmp_path, python=(3, 11, 9)).doctor.execute()

    check = by_id(report)["python"]
    assert check.status == "fail"
    assert "3.11.9" in check.detail
    assert "uv python install" in check.detail
    assert report.ready is False


def test_missing_uv_is_only_a_warning_and_does_not_block(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.host.uv = None

    report = setup.doctor.execute()

    assert by_id(report)["uv"].status == "warn"
    assert "astral.sh/uv" in by_id(report)["uv"].detail
    assert report.ready is True
    assert report.summary.warn == 1


def test_missing_products_dir_is_a_config_failure_with_the_fix(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.host.directories.clear()

    check = by_id(setup.doctor.execute())["products_dir"]

    assert check.status == "fail"
    assert check.kind == "config"
    assert "HDAST_PRODUCTS_DIR" in check.detail
    assert str(PRODUCTS) in check.detail


# ------------------------------------------------------------------------ docker


def test_docker_down_fails_with_the_fix_and_skips_the_image_check(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.host.docker_error = ExternalToolError("O Docker não respondeu.", hint="Abra o Docker.")

    report = setup.doctor.execute()

    checks = by_id(report)
    assert checks["docker"].status == "fail"
    assert "Abra o Docker." in checks["docker"].detail
    assert "images" not in checks
    assert report.ready is False


def test_missing_own_images_fail_and_list_names_without_digest(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.host.present = {"socat:1@sha256:bbb"}

    report = setup.doctor.execute()

    check = by_id(report)["images"]
    assert check.status == "fail"
    assert "Faltam 2 de 3" in check.detail
    assert "zap:1" in check.detail
    assert "sha256" not in check.detail
    assert "hdast stack pull" in check.detail
    assert report.ready is False


def test_missing_auxiliary_images_warn_and_show_the_matching_proxy_version(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.host.present.remove(setup.host.images["zap-gateway"])

    check = by_id(setup.doctor.execute())["images"]

    assert check.status == "warn"
    assert "serão baixadas" in check.detail
    assert f"versão da CLI ({__version__})" in check.detail


@pytest.mark.parametrize("version", ["0.0.0", None])
def test_doctor_fails_when_proxy_version_is_incompatible(
    tmp_path: Path, version: str | None
) -> None:
    setup = Setup(tmp_path)
    setup.host.versions[setup.host.images["scope-proxy"]] = version

    check = by_id(setup.doctor.execute())["images"]

    assert check.status == "fail"
    assert f"A CLI exige a versão {__version__}" in check.detail


def test_doctor_warns_when_local_build_will_create_the_images(tmp_path: Path) -> None:
    setup = Setup(tmp_path, environ={"HDAST_STACK_BUILD": "1"})

    check = by_id(setup.doctor.execute())["images"]

    assert check.status == "warn"
    assert "hdast/scope-proxy:local" in check.detail
    assert "serão construídas" in check.detail


def test_image_check_summarises_when_many_images_are_missing(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.host.images["proxy-gateway"] = "outra-ponte:1"
    setup.host.present = set()

    check = by_id(setup.doctor.execute())["images"]

    assert "e mais 1" in check.detail


def test_compose_problem_fails_the_image_check(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.host.compose_error = ConfigError("Sem compose.yaml.", hint="Rode do repositório.")

    check = by_id(setup.doctor.execute())["images"]

    assert check.status == "fail"
    assert "Rode do repositório." in check.detail


def test_docker_dying_while_listing_images_fails_the_image_check(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.host.present = set()
    original = setup.host.inspect_image

    def dying(reference: str) -> ImageInfo | None:
        setup.host.docker_error = ExternalToolError("O Docker caiu.", hint="Execute docker images.")
        return original(reference)

    setup.host.inspect_image = dying  # type: ignore[method-assign]  # falha difícil de provocar

    check = by_id(setup.doctor.execute())["images"]

    assert check.status == "fail"
    assert "hdast doctor novamente" in check.detail
    assert "docker images" not in check.detail


def test_images_come_from_the_base_services_when_no_product_is_given(tmp_path: Path) -> None:
    setup = Setup(tmp_path)

    setup.doctor.execute()

    assert setup.host.requested_services == (
        "zap",
        "zap-gateway",
        "scope-proxy",
        "proxy-gateway",
    )


# ------------------------------------------------------------------------ portas


def test_busy_fixed_port_fails_and_names_the_variable_to_change(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.host.busy_ports = {8080}

    report = setup.doctor.execute()

    check = by_id(report)["port:8080"]
    assert check.status == "fail"
    assert "HDAST_ZAP_HOST_PORT" in check.detail
    assert by_id(report)["port:3128"].status == "ok"
    assert report.ready is False


def test_busy_port_is_expected_when_the_managed_stack_is_up(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.host.busy_ports = {8080, 3128}
    setup.states.state = stack_state(tmp_path, "2026-11-10T13:00:00+00:00")

    report = setup.doctor.execute()

    assert by_id(report)["port:8080"].status == "ok"
    assert "pilha atual" in by_id(report)["port:8080"].detail
    assert report.ready is True


def test_configured_ports_replace_the_defaults(tmp_path: Path) -> None:
    setup = Setup(
        tmp_path, environ={"HDAST_ZAP_HOST_PORT": "18080", "HDAST_PROXY_HOST_PORT": "13128"}
    )
    setup.host.busy_ports = {8080}

    report = setup.doctor.execute()

    assert {"port:18080", "port:13128"} <= set(by_id(report))
    assert report.ready is True


FULLWIDTH_8080 = "".join(chr(0xFF10 + int(digit)) for digit in "8080")


@pytest.mark.parametrize("value", ["abc", "0", "65536", "-1", "80.5", "", " 8080", FULLWIDTH_8080])
def test_invalid_configured_port_is_a_config_failure(tmp_path: Path, value: str) -> None:
    report = Setup(tmp_path, environ={"HDAST_ZAP_HOST_PORT": value}).doctor.execute()

    failures = [c for c in report.checks if c.status == "fail"]
    assert len(failures) == 1
    assert failures[0].kind == "config"
    assert "HDAST_ZAP_HOST_PORT" in failures[0].detail


def test_pilot_target_also_checks_its_fixed_ports(tmp_path: Path) -> None:
    data = profile_data()
    data["product"] = "clinica-piloto"
    data["environment"]["base_url"] = "http://clinica-piloto:8080"
    data["scope"]["allow"] = [
        {
            "host": "clinica-piloto",
            "scheme": "http",
            "port": 8080,
            "allow_local": True,
            "paths": ["/api/**"],
            "methods": ["GET", "POST"],
        }
    ]
    profile = ProductProfile.from_data(data)
    setup = Setup(tmp_path, profile=profile)
    setup.host.busy_ports = {28080}

    report = setup.doctor.execute("clinica-piloto")

    assert by_id(report)["port:28080"].status == "fail"
    assert by_id(report)["port:29091"].status == "ok"


# ------------------------------------------------------------------------- pilha


def test_expired_managed_stack_warns_and_says_to_bring_it_up_again(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.states.state = stack_state(tmp_path, "2026-11-10T11:00:00+00:00")

    report = setup.doctor.execute()

    check = by_id(report)["stack"]
    assert check.status == "warn"
    assert "stack up" in check.detail
    assert report.ready is True


def test_live_managed_stack_is_reported_with_its_validity(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.states.state = stack_state(tmp_path, "2026-11-10T13:00:00+00:00")

    check = by_id(setup.doctor.execute())["stack"]

    assert check.status == "ok"
    assert "2026-11-10T13:00:00+00:00" in check.detail


def test_no_stack_check_without_a_managed_stack(tmp_path: Path) -> None:
    assert "stack" not in by_id(Setup(tmp_path).doctor.execute())


# ----------------------------------------------------------------------- produto


def test_product_adds_profile_authorization_window_and_secret_checks(tmp_path: Path) -> None:
    report = Setup(tmp_path).doctor.execute("agenda")

    assert report.product == "agenda"
    assert [c.id for c in report.checks][-5:] == [
        "profile",
        "authorization",
        "window",
        "secrets:user_a",
        "authz_peers",  # o perfil de teste tem uma conta só: aviso, não reprovação
    ]
    assert report.ready is True


def test_unknown_product_is_a_config_failure_and_skips_the_dependent_checks(
    tmp_path: Path,
) -> None:
    report = Setup(tmp_path).doctor.execute("nao-existe")

    checks = by_id(report)
    assert checks["profile"].status == "fail"
    assert checks["profile"].kind == "config"
    assert "nao-existe" in checks["profile"].detail
    assert "authorization" not in checks
    assert "secrets:user_a" not in checks


def test_template_placeholders_fail_the_profile_check_with_the_codes(tmp_path: Path) -> None:
    data = profile_data()
    data["environment"]["base_url"] = "https://meu.exemplo.com.br"
    data["scope"]["allow"][0]["host"] = "meu.exemplo.com.br"
    setup = Setup(tmp_path, profile=ProductProfile.from_data(data))

    check = by_id(setup.doctor.execute("agenda"))["profile"]

    assert check.status == "fail"
    assert "PLACEHOLDER_HOST" in check.detail
    assert "hdast profile validate agenda" in check.detail


def test_missing_openapi_file_fails_the_profile_check(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.profiles.add(agenda_profile(), existing_files=set())

    check = by_id(setup.doctor.execute("agenda"))["profile"]

    assert check.status == "fail"
    assert "FILE_MISSING" in check.detail


def test_expired_authorization_is_a_scope_failure_reported_once(tmp_path: Path) -> None:
    data = profile_data()
    data["scope"]["authorization"]["valid_until"] = "2020-01-01"
    setup = Setup(tmp_path, profile=agenda_profile(scope=data["scope"]))

    report = setup.doctor.execute("agenda")

    checks = by_id(report)
    assert checks["authorization"].status == "fail"
    assert checks["authorization"].kind == "scope"
    assert checks["profile"].status == "ok"  # não repete a pendência da carta
    assert report.ready is False


def test_closed_window_is_a_scope_failure(tmp_path: Path) -> None:
    data = profile_data()
    data["scope"]["windows"] = ["seg-dom 20:00-21:00 UTC"]
    setup = Setup(tmp_path, profile=agenda_profile(scope=data["scope"]))

    checks = by_id(setup.doctor.execute("agenda"))

    assert checks["window"].status == "fail"
    assert checks["window"].kind == "scope"
    assert checks["profile"].status == "ok"


def test_missing_secret_names_account_and_field_but_never_the_value_or_json_variable(
    tmp_path: Path,
) -> None:
    setup = Setup(tmp_path, env={"ACME_USER_A_LOGIN": LOGIN})

    report = setup.doctor.execute("agenda")

    check = by_id(report)["secrets:user_a"]
    assert check.status == "fail"
    assert "user_a.password" in check.detail
    assert "ACME_USER_A_SENHA" in (check.operator_detail or "")
    dumped = json.dumps(report.model_dump(mode="json"))
    assert "ACME_USER_A_SENHA" not in dumped
    assert LOGIN not in dumped


def test_defined_secrets_are_reported_without_ever_leaking_the_values(tmp_path: Path) -> None:
    report = Setup(tmp_path).doctor.execute("agenda")

    dumped = json.dumps(report.model_dump(mode="json"))
    assert by_id(report)["secrets:user_a"].status == "ok"
    assert PASSWORD not in dumped
    assert LOGIN not in dumped


def test_secret_values_are_registered_for_masking(tmp_path: Path) -> None:
    setup = Setup(tmp_path)

    setup.doctor.execute("agenda")

    assert PASSWORD not in setup.vault.mask(f"senha={PASSWORD}")


def test_product_check_adds_the_lab_services_to_the_image_list(tmp_path: Path) -> None:
    data = profile_data()
    data["environment"]["base_url"] = "http://vampi:5000"
    data["scope"]["allow"] = [
        {
            "host": "vampi",
            "scheme": "http",
            "port": 5000,
            "allow_local": True,
            "paths": ["/api/**"],
            "methods": ["GET", "POST"],
        }
    ]
    data["product"] = "vampi"
    setup = Setup(tmp_path, profile=ProductProfile.from_data(data))

    setup.doctor.execute("vampi")

    assert "vampi" in setup.host.requested_services


# --------------------------------------------------------------- código de saída


@pytest.mark.parametrize(
    ("break_it", "expected"),
    [
        pytest.param("docker", ExitCode.PREFLIGHT, id="environment"),
        pytest.param("profile", ExitCode.USAGE, id="config"),
        pytest.param("window", ExitCode.SCOPE, id="scope"),
    ],
)
def test_failure_exit_code_follows_the_kind_of_the_first_failure(
    tmp_path: Path, break_it: str, expected: ExitCode
) -> None:
    data = profile_data()
    setup = Setup(tmp_path)
    if break_it == "docker":
        setup.host.docker_error = ExternalToolError("parado", hint="abra")
    if break_it == "profile":
        setup.profiles.add(agenda_profile(), existing_files=set())
    if break_it == "window":
        data["scope"]["windows"] = ["seg-dom 20:00-21:00 UTC"]
        setup.profiles.add(agenda_profile(scope=data["scope"]), existing_files={"./openapi.json"})

    error = doctor_failure(setup.doctor.execute("agenda"))

    assert error.exit_code == expected
    assert error.hint


def test_scope_failure_wins_over_config_and_environment(tmp_path: Path) -> None:
    data = profile_data()
    data["scope"]["windows"] = ["seg-dom 20:00-21:00 UTC"]
    setup = Setup(tmp_path, profile=agenda_profile(scope=data["scope"]))
    setup.host.docker_error = ExternalToolError("parado", hint="abra")
    setup.host.directories.clear()

    error = doctor_failure(setup.doctor.execute("agenda"))

    assert error.exit_code == ExitCode.SCOPE


def test_doctor_never_touches_the_target_or_docker_more_than_to_read(tmp_path: Path) -> None:
    setup = Setup(tmp_path)

    setup.doctor.execute("agenda")

    # 1 consulta de versão + 1 por imagem: leitura pura (o falso não tem como "subir" nada).
    assert setup.host.docker_calls == 1 + len(set(setup.host.images.values()))


# ------------------------------------------------- avisos que olham o perfil (V1.1)


def two_accounts_data() -> dict[str, Any]:
    data = profile_data()
    second = {**data["auth"]["accounts"][0], "alias": "user_b"}
    second["username"] = {"secret_ref": "env:ACME_USER_B_LOGIN"}
    second["password"] = {"secret_ref": "env:ACME_USER_B_SENHA"}
    data["auth"]["accounts"].append(second)
    return data


def test_warns_when_the_profile_has_no_two_accounts_of_the_same_role(tmp_path: Path) -> None:
    check = by_id(Setup(tmp_path).doctor.execute("agenda"))["authz_peers"]

    assert check.status == "warn"
    assert "duas contas do mesmo papel" in check.detail
    assert "hdast run, que o roda por padrão" in check.detail


def test_no_peer_warning_when_two_accounts_share_a_role(tmp_path: Path) -> None:
    profile = ProductProfile.from_data(two_accounts_data())
    setup = Setup(tmp_path, profile=profile)

    assert "authz_peers" not in by_id(setup.doctor.execute("agenda"))


def test_two_accounts_of_different_roles_still_warn(tmp_path: Path) -> None:
    data = two_accounts_data()
    data["auth"]["accounts"][1]["role"] = "admin"
    setup = Setup(tmp_path, profile=ProductProfile.from_data(data))

    assert by_id(setup.doctor.execute("agenda"))["authz_peers"].status == "warn"


def test_warns_about_wide_path_mode_without_failing(tmp_path: Path) -> None:
    data = profile_data()
    data["scope"]["path_mode"] = "wide"
    setup = Setup(tmp_path, profile=ProductProfile.from_data(data))

    report = setup.doctor.execute("agenda")

    check = by_id(report)["path_mode"]
    assert check.status == "warn"
    assert "deny_paths COMPLETO" in check.detail
    assert "1 caminho(s) listado(s)" in check.detail
    assert report.ready is True


def test_no_path_mode_warning_in_the_default_strict_mode(tmp_path: Path) -> None:
    assert "path_mode" not in by_id(Setup(tmp_path).doctor.execute("agenda"))


def test_the_new_warnings_never_suggest_widening_scope_limits_or_window(tmp_path: Path) -> None:
    data = two_accounts_data()
    data["scope"]["path_mode"] = "wide"
    data["auth"]["accounts"][1]["role"] = "admin"
    setup = Setup(tmp_path, profile=ProductProfile.from_data(data))
    report = setup.doctor.execute("agenda")

    text = " ".join(by_id(report)[name].detail for name in ("path_mode", "authz_peers"))

    for word in ("amplie", "aumente", "estenda", "libere"):
        assert word not in text.lower()

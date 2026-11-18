"""Contrato de `hdast doctor`: envelope, códigos de saída e ausência de vazamento.

O Docker é trocado por um falso na montagem da CLI: nenhum teste chama o docker de verdade nem
o alvo.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from harness_dast.cli import composition
from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ExitCode, ExternalToolError
from tests.fakes.host import FakeHost
from tests.fakes.profile_data import dump_yaml, valid_profile_data

pytestmark = pytest.mark.contract

LOGIN = "usuario-do-doctor"
PASSWORD = "SenhaDoDoctor-Nao-Pode-Vazar-31"  # noqa: S105 - sentinela
DATA_KEYS = {"product", "ready", "checks", "summary"}


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeHost:
    fake = FakeHost()
    products = tmp_path / "produtos"
    products.mkdir()
    fake.directories.add(products)
    monkeypatch.setattr(composition, "SystemHost", lambda _env: fake)
    for name in (
        "HDAST_PRODUCTS_DIR",
        "HDAST_ZAP_HOST_PORT",
        "HDAST_PROXY_HOST_PORT",
        "HDAST_STACK_BUILD",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path / "estado"))
    monkeypatch.setenv("ACME_USER_A_LOGIN", LOGIN)
    monkeypatch.setenv("ACME_USER_A_SENHA", PASSWORD)
    return fake


def products_dir(tmp_path: Path) -> Path:
    return tmp_path / "produtos"


def write_product(tmp_path: Path, **changes: Any) -> None:
    data = valid_profile_data("demo")
    data.update(changes)
    folder = products_dir(tmp_path) / "demo"
    folder.mkdir(exist_ok=True)
    (folder / "target.yml").write_text(dump_yaml(data), encoding="utf-8")
    (folder / "openapi.json").write_text("{}", encoding="utf-8")


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = run_app(build_app(), list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def run_json(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any]]:
    code, out, _ = run(capsys, "--json", *args)
    return code, json.loads(out)


def test_doctor_without_product_returns_the_success_envelope_when_the_machine_is_ready(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = run_json(capsys, "doctor", "--products-dir", str(products_dir(tmp_path)))

    assert code == ExitCode.OK
    assert set(envelope) == {"schema_version", "ok", "data"}
    assert envelope["ok"] is True
    data = envelope["data"]
    assert set(data) == DATA_KEYS
    assert data["product"] is None
    assert data["ready"] is True
    assert {"python", "docker", "images", "products_dir"} <= {c["id"] for c in data["checks"]}
    assert set(data["checks"][0]) == {"id", "status", "detail", "kind"}
    assert set(data["summary"]) == {"ok", "warn", "fail"}


def test_doctor_reports_incompatible_proxy_image_with_preflight_exit_code(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host.versions[host.images["scope-proxy"]] = "0.0.0"

    code, envelope = run_json(capsys, "doctor", "--products-dir", str(products_dir(tmp_path)))

    assert code == ExitCode.PREFLIGHT
    assert envelope["error"]["code"] == "PREFLIGHT_FAILED"
    check = next(check for check in envelope["data"]["checks"] if check["id"] == "images")
    assert check["status"] == "fail"
    assert "hdast stack pull" in check["detail"]


def test_doctor_with_product_checks_profile_authorization_window_and_secrets(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_product(tmp_path, openapi="./openapi.json")

    code, envelope = run_json(
        capsys, "doctor", "demo", "--products-dir", str(products_dir(tmp_path))
    )

    ids = [c["id"] for c in envelope["data"]["checks"]]
    assert code == ExitCode.OK
    assert envelope["data"]["product"] == "demo"
    assert ids[-4:] == ["authorization", "window", "secrets:user_a", "authz_peers"]
    assert "profile" in ids


def test_doctor_accepts_the_json_flag_after_the_command(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(capsys, "doctor", "--products-dir", str(products_dir(tmp_path)), "--json")

    assert code == ExitCode.OK
    assert json.loads(out)["ok"] is True


def test_doctor_exits_4_with_error_and_data_when_docker_is_down(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host.docker_error = ExternalToolError("O Docker não respondeu.", hint="Abra o Docker Desktop.")

    code, envelope = run_json(capsys, "doctor", "--products-dir", str(products_dir(tmp_path)))

    assert code == ExitCode.PREFLIGHT
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "PREFLIGHT_FAILED"
    assert "docker" in envelope["error"]["message"]
    assert envelope["data"]["ready"] is False
    docker = next(c for c in envelope["data"]["checks"] if c["id"] == "docker")
    assert docker["status"] == "fail"
    assert "Abra o Docker Desktop." in docker["detail"]


def test_doctor_exits_2_when_the_products_dir_does_not_exist(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = run_json(capsys, "doctor", "--products-dir", str(tmp_path / "nao-existe"))

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"


def test_doctor_exits_2_when_the_product_does_not_exist(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = run_json(
        capsys, "doctor", "fantasma", "--products-dir", str(products_dir(tmp_path))
    )

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert envelope["data"]["checks"][-1]["id"] == "profile"


def test_doctor_exits_3_when_the_authorization_expired(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_profile_data("demo")
    data["scope"]["authorization"]["valid_until"] = "2020-01-01"
    write_product(tmp_path, scope=data["scope"])

    code, envelope = run_json(
        capsys, "doctor", "demo", "--products-dir", str(products_dir(tmp_path))
    )

    assert code == ExitCode.SCOPE
    assert envelope["error"]["code"] == "SCOPE_VIOLATION"


def test_doctor_exits_2_when_a_configured_port_is_not_a_number(
    host: FakeHost,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HDAST_ZAP_HOST_PORT", "oito-mil")

    code, envelope = run_json(capsys, "doctor", "--products-dir", str(products_dir(tmp_path)))

    assert code == ExitCode.USAGE
    assert "HDAST_ZAP_HOST_PORT" in envelope["error"]["hint"]


def test_doctor_never_prints_the_secret_values_or_the_variable_names_in_json(
    host: FakeHost,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_product(tmp_path)
    monkeypatch.delenv("ACME_USER_A_SENHA")

    code, out, err = run(
        capsys, "--json", "doctor", "demo", "--products-dir", str(products_dir(tmp_path))
    )

    assert code == ExitCode.PREFLIGHT
    for text in (out, err):
        assert PASSWORD not in text
        assert LOGIN not in text
        assert "ACME_USER_A_SENHA" not in text


def test_doctor_human_output_names_the_variable_only_for_the_person_and_hides_values(
    host: FakeHost,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_product(tmp_path)
    monkeypatch.delenv("ACME_USER_A_SENHA")

    code, out, _ = run(capsys, "doctor", "demo", "--products-dir", str(products_dir(tmp_path)))

    assert code == ExitCode.PREFLIGHT
    assert "[FALHA] secrets:user_a" in out
    assert "ACME_USER_A_SENHA" in out
    assert PASSWORD not in out
    assert "NÃO está pronto para começar." in out


def test_doctor_human_output_summarises_a_ready_machine(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(capsys, "doctor", "--products-dir", str(products_dir(tmp_path)))

    assert code == ExitCode.OK
    assert "Doctor (ambiente):" in out
    assert "Tudo pronto para começar." in out

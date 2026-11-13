"""Contrato de `hdast init` e `hdast profile validate`: envelope, códigos de saída, vazamentos."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ExitCode
from tests.fakes.profile_data import dump_yaml, valid_profile_data

pytestmark = pytest.mark.contract

SECRET = "SenhaLiteral-Nao-Pode-Vazar-7"  # noqa: S105 - sentinela para provar que não vaza
ENV_SECRET = "valor-da-variavel-de-ambiente-123"  # noqa: S105 - sentinela

VALIDATE_KEYS = {
    "product",
    "environment_name",
    "base_url_host",
    "allow_rules",
    "deny_paths",
    "auth_type",
    "accounts",
    "windows",
    "authorization_reference",
    "authorization_valid_until",
    "authorization_valid_now",
    "window_open_now",
    "limits",
    "cleanup_configured",
    "checked_at",
    "runnable",
    "issues",
}


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HDAST_LOG_LEVEL", "HDAST_PRODUCTS_DIR", "HDAST_ZAP_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = run_app(build_app(), list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _run_json(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any]]:
    code, out, _ = _run(capsys, "--json", *args)
    return code, json.loads(out)


def _write_profile(products: Path, data: dict[str, Any], product: str = "demo") -> Path:
    directory = products / product
    directory.mkdir(exist_ok=True)
    (directory / "target.yml").write_text(dump_yaml(data), encoding="utf-8")
    return directory


# ---------------------------------------------------------------- init


def test_init_returns_success_envelope_when_product_is_new(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = _run_json(capsys, "init", "demo", "--products-dir", str(tmp_path))

    assert code == ExitCode.OK
    assert set(envelope) == {"schema_version", "ok", "data"}
    assert envelope["ok"] is True
    data = envelope["data"]
    assert set(data) == {"product", "directory", "files"}
    assert data["product"] == "demo"
    assert Path(data["directory"]) == (tmp_path / "demo").resolve()
    assert "target.yml" in data["files"]
    assert (tmp_path / "demo" / "target.yml").is_file()


def test_init_does_not_create_cleanup_folder_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = _run_json(capsys, "init", "demo", "--products-dir", str(tmp_path))

    assert code == ExitCode.OK
    assert not (tmp_path / "demo" / "cleanup").exists()
    assert not any(name.startswith("cleanup/") for name in envelope["data"]["files"])


def test_init_creates_cleanup_folder_when_with_cleanup_is_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = _run_json(
        capsys, "init", "demo", "--products-dir", str(tmp_path), "--with-cleanup"
    )

    assert code == ExitCode.OK
    assert set(envelope["data"]) == {"product", "directory", "files"}
    assert "cleanup/README.md" in envelope["data"]["files"]
    assert (tmp_path / "demo" / "cleanup" / "cleanup.sql.example").is_file()


def test_init_human_output_says_whether_the_cleanup_folder_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, plain, _ = _run(capsys, "init", "a", "--products-dir", str(tmp_path))
    _, with_cleanup, _ = _run(
        capsys, "init", "b", "--products-dir", str(tmp_path), "--with-cleanup"
    )

    assert "--with-cleanup" in plain
    assert "foi criada" in with_cleanup


def test_init_accepts_json_flag_after_the_subcommand(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(capsys, "init", "demo", "--products-dir", str(tmp_path), "--json")

    assert code == 0
    assert json.loads(out)["ok"] is True


def test_init_prints_readable_summary_when_human_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(capsys, "init", "demo", "--products-dir", str(tmp_path))

    assert code == 0
    assert "Produto demo criado" in out
    assert "hdast profile validate demo" in out
    assert err == ""


def test_init_fails_with_config_error_when_product_already_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(capsys, "init", "demo", "--products-dir", str(tmp_path))
    target = tmp_path / "demo" / "target.yml"
    target.write_text("editado pela pessoa", encoding="utf-8")

    code, envelope = _run_json(capsys, "init", "demo", "--products-dir", str(tmp_path))

    assert code == ExitCode.USAGE
    assert int(ExitCode.USAGE) == 2
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert "já existe" in envelope["error"]["message"]
    assert target.read_text(encoding="utf-8") == "editado pela pessoa"


@pytest.mark.parametrize("name", ["../fora", "a/b", "..", "C:\\x", "/abs", "Demo", "con"])
def test_init_fails_with_config_error_when_name_is_unsafe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    products = tmp_path / "produtos"
    products.mkdir()

    code, envelope = _run_json(capsys, "init", name, "--products-dir", str(products))

    assert code == 2
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert list(tmp_path.iterdir()) == [products]
    assert list(products.iterdir()) == []


def test_init_fails_when_products_dir_does_not_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nao-existe"

    code, envelope = _run_json(capsys, "init", "demo", "--products-dir", str(missing))

    assert code == 2
    assert "--products-dir" in envelope["error"]["hint"]
    assert not missing.exists()


def test_init_uses_products_dir_from_environment_when_flag_is_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HDAST_PRODUCTS_DIR", str(tmp_path))

    code, _ = _run_json(capsys, "init", "demo")

    assert code == 0
    assert (tmp_path / "demo" / "target.yml").is_file()


def test_flag_takes_precedence_over_environment_variable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from_env = tmp_path / "env"
    from_flag = tmp_path / "flag"
    from_env.mkdir()
    from_flag.mkdir()
    monkeypatch.setenv("HDAST_PRODUCTS_DIR", str(from_env))

    code, _ = _run_json(capsys, "init", "demo", "--products-dir", str(from_flag))

    assert code == 0
    assert (from_flag / "demo").is_dir()
    assert not (from_env / "demo").exists()


# ----------------------------------------------------------- validate


def test_validate_reports_untouched_template_as_valid_but_not_runnable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(capsys, "init", "demo", "--products-dir", str(tmp_path))

    code, envelope = _run_json(
        capsys, "profile", "validate", "demo", "--products-dir", str(tmp_path)
    )

    assert code == ExitCode.OK
    data = envelope["data"]
    assert set(data) == VALIDATE_KEYS
    assert data["runnable"] is False
    assert data["product"] == "demo"
    assert data["accounts"] == [{"alias": "user_a", "role": "usuario"}]
    by_code: dict[str, list[str]] = {}
    for issue in data["issues"]:
        assert set(issue) == {"code", "field", "message"}
        by_code.setdefault(issue["code"], []).append(issue["field"])
    assert by_code["PLACEHOLDER_HOST"] == ["environment.base_url", "scope.allow[0].host"]
    assert by_code["PLACEHOLDER_AUTHORIZATION"] == ["scope.authorization.reference"]
    assert by_code["FILE_MISSING"] == ["openapi", "cleanup.script"]
    assert set(by_code["PLACEHOLDER_SECRET_REF"]) == {
        "auth.accounts[user_a].username",
        "auth.accounts[user_a].password",
        "cleanup.connection",
    }


def test_validate_human_output_says_what_must_be_filled_in_for_the_template(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(capsys, "init", "demo", "--products-dir", str(tmp_path))

    code, out, err = _run(capsys, "profile", "validate", "demo", "--products-dir", str(tmp_path))

    assert code == 0
    assert "estrutura válida" in out
    assert "NÃO executável" in out
    assert "PLACEHOLDER_HOST" in out
    assert "openapi.json" in out
    assert err == ""


def test_validate_reports_runnable_when_profile_is_complete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _write_profile(tmp_path, valid_profile_data())
    (directory / "openapi.json").write_text("{}", encoding="utf-8")

    code, envelope = _run_json(
        capsys, "profile", "validate", "demo", "--products-dir", str(tmp_path)
    )

    data = envelope["data"]
    assert code == 0
    assert data["runnable"] is True
    assert data["issues"] == []
    assert data["base_url_host"] == "api.hml.acme-teste.net.br"
    assert data["authorization_reference"] == "CHG-4821"
    assert data["window_open_now"] is True
    assert data["authorization_valid_now"] is True
    assert data["limits"] == {
        "requests_per_second": 5.0,
        "max_duration_minutes": 60,
        "zap_threads_per_host": 2,
    }


def test_validate_returns_zero_with_issue_when_authorization_is_expired(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_profile_data()
    data["scope"]["authorization"]["valid_until"] = "2020-01-01"
    directory = _write_profile(tmp_path, data)
    (directory / "openapi.json").write_text("{}", encoding="utf-8")

    code, envelope = _run_json(
        capsys, "profile", "validate", "demo", "--products-dir", str(tmp_path)
    )

    assert code == 0
    assert envelope["data"]["authorization_valid_now"] is False
    assert [i["code"] for i in envelope["data"]["issues"]] == ["AUTHORIZATION_EXPIRED"]


def test_validate_fails_with_config_error_when_product_does_not_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = _run_json(
        capsys, "profile", "validate", "inexistente", "--products-dir", str(tmp_path)
    )

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert "hdast init" in envelope["error"]["hint"]
    assert "data" not in envelope


def test_validate_fails_with_field_paths_when_profile_is_structurally_invalid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_profile_data()
    data["limits"]["requests_per_second"] = 9999
    _write_profile(tmp_path, data)

    code, envelope = _run_json(
        capsys, "profile", "validate", "demo", "--products-dir", str(tmp_path)
    )

    assert code == 2
    assert "limits.requests_per_second" in envelope["error"]["message"]


def test_validate_fails_when_base_url_host_is_outside_the_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_profile_data()
    data["environment"]["base_url"] = "https://fora-do-escopo.acme-teste.net.br"
    _write_profile(tmp_path, data)

    code, envelope = _run_json(
        capsys, "profile", "validate", "demo", "--products-dir", str(tmp_path)
    )

    assert code == 2
    assert "environment" in envelope["error"]["message"]


def test_validate_fails_in_human_mode_on_stderr_with_empty_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(capsys, "profile", "validate", "nada", "--products-dir", str(tmp_path))

    assert code == 2
    assert out == ""
    assert "Erro [CONFIG_ERROR]" in err
    assert "Como resolver" in err


@pytest.mark.parametrize(
    "yaml_text",
    [
        "a: &x 1\n",
        "a: 1\na: 2\n",
        "a:\n  <<: {b: 1}\n",
        "x: !!python/object/apply:os.system ['echo oi']\n",
        "- lista\n",
        "",
    ],
)
def test_validate_fails_with_config_error_when_yaml_is_dangerous_or_wrong(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], yaml_text: str
) -> None:
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "target.yml").write_text(yaml_text, encoding="utf-8")

    code, envelope = _run_json(
        capsys, "profile", "validate", "demo", "--products-dir", str(tmp_path)
    )

    assert code == 2
    assert envelope["error"]["code"] == "CONFIG_ERROR"


@pytest.mark.parametrize("name", ["../x", "a/b", "C:\\x", "/etc"])
def test_validate_fails_when_product_name_tries_to_escape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    code, envelope = _run_json(capsys, "profile", "validate", name, "--products-dir", str(tmp_path))

    assert code == 2
    assert "inválido" in envelope["error"]["message"]


def test_profile_group_without_subcommand_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, envelope = _run_json(capsys, "profile")

    assert code == 2
    assert envelope["error"]["code"] == "CONFIG_ERROR"


# ------------------------------------------------- init -> validate


def test_init_then_validate_reaches_a_sensible_result_for_the_untouched_template(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    init_code, _ = _run_json(capsys, "init", "demo", "--products-dir", str(tmp_path))
    code, envelope = _run_json(
        capsys, "profile", "validate", "demo", "--products-dir", str(tmp_path)
    )

    assert (init_code, code) == (0, 0)
    assert envelope["data"]["product"] == "demo"
    assert envelope["data"]["runnable"] is False
    assert len(envelope["data"]["issues"]) >= 5


# ------------------------------------------------ segredos e vazamento


def _all_output(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, *args: str
) -> str:
    _, out, err = _run(capsys, *args)
    return out + err + caplog.text


def test_literal_secret_in_yaml_never_appears_in_output_or_logs_when_validation_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    data = valid_profile_data()
    account = data["auth"]["accounts"][0]
    account["username"] = SECRET
    account["password"] = {"secret_ref": SECRET}
    _write_profile(tmp_path, data)

    for flags in (("--json",), ()):
        everything = _all_output(
            capsys, caplog, *flags, "profile", "validate", "demo", "--products-dir", str(tmp_path)
        )
        assert SECRET not in everything
        assert "CONFIG_ERROR" in everything


def test_literal_secret_never_appears_when_yaml_is_malformed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "target.yml").write_text(
        f"password: {SECRET}\nx: &ancora [\n", encoding="utf-8"
    )

    everything = _all_output(
        capsys, caplog, "--json", "profile", "validate", "demo", "--products-dir", str(tmp_path)
    )

    assert SECRET not in everything


def test_literal_secret_never_appears_when_it_is_the_product_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    everything = _all_output(
        capsys, caplog, "--json", "init", SECRET, "--products-dir", str(tmp_path)
    )

    assert SECRET not in everything


def test_environment_variable_contents_never_appear_when_profile_is_valid(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("ACME_USER_A_SENHA", ENV_SECRET)
    monkeypatch.setenv("ACME_USER_A_LOGIN", ENV_SECRET)
    directory = _write_profile(tmp_path, valid_profile_data())
    (directory / "openapi.json").write_text("{}", encoding="utf-8")

    everything = _all_output(
        capsys, caplog, "--json", "profile", "validate", "demo", "--products-dir", str(tmp_path)
    )

    assert ENV_SECRET not in everything
    assert "ACME_USER_A_SENHA" not in everything
    assert "secret_ref" not in everything


def test_command_output_is_ascii_safe_when_stdout_encoding_is_ascii(tmp_path: Path) -> None:
    # Pelo processo real: `main()` força UTF-8; sem isso as mensagens acentuadas
    # derrubariam o comando com UnicodeEncodeError (saída 10) em página de código antiga.
    result = subprocess.run(  # noqa: S603 - executa o próprio pacote com argumentos fixos
        [
            sys.executable,
            "-m",
            "harness_dast",
            "--json",
            "profile",
            "validate",
            "nada",
            "--products-dir",
            str(tmp_path),
        ],
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "ascii"},
    )

    envelope = json.loads(result.stdout.decode("utf-8"))
    assert result.returncode == 2
    assert envelope["error"]["code"] == "CONFIG_ERROR"

"""Contrato da tabela "quem pode o quê" (ADR 0041): `authz`, `--draft-matrix` e a aprovação.

Usa o mesmo servidor HTTP real e o mesmo produto de `test_cli_authz.py`: um alvo com um `GET
/api/doc/{id}` e duas contas do papel `usuario`.
"""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness_dast.domain.errors import ExitCode
from tests.contract.test_cli_authz import (  # noqa: F401 - `_env` é fixture autouse do módulo
    _env,
    environment,
    invoke_json,
    probe,
)

pytestmark = pytest.mark.contract

FORBIDDEN_DOC: dict[str, Any] = {"operation": "doc", "allow": [], "deny": ["usuario"]}


def draft_file(products: Path) -> Path:
    return products / "demo" / "authz-matrix.draft.yml"


def test_authz_with_a_table_reports_the_matrix_in_the_envelope_and_in_authz_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path, access_matrix=[FORBIDDEN_DOC]) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, _ = invoke_json(
            capsys,
            "authz",
            "demo",
            "--run",
            run_id,
            "--check",
            "access_matrix",
            "--products-dir",
            str(products),
        )

    assert code == ExitCode.OK
    matrix = envelope["data"]["access_matrix"]
    assert matrix["roles"] == ["usuario"]
    [row] = matrix["rows"]
    assert (row["operation_id"], row["method"], row["path"]) == ("doc", "GET", "/api/doc/{id}")
    assert row["cells"][0]["result"] == "failed"
    assert row["cells"][0]["source"] == "probe"
    assert {f["technique"] for f in envelope["data"]["findings"]} == {"authz_access_matrix"}
    on_disk = json.loads((tmp_path / "runs" / run_id / "authz.json").read_text(encoding="utf-8"))
    assert on_disk["access_matrix"] == matrix


def test_a_table_changed_after_the_approval_is_refused_with_scope_not_approved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        target = products / "demo" / "target.yml"
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        data["authz"] = {"access_matrix": [FORBIDDEN_DOC]}
        target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        code, envelope, _ = invoke_json(
            capsys, "authz", "demo", "--run", run_id, "--products-dir", str(products)
        )

    assert code == ExitCode.SCOPE
    assert envelope["error"]["code"] == "SCOPE_NOT_APPROVED"
    assert "authz" in envelope["error"]["message"]


def test_a_table_with_an_unknown_operation_exits_2_with_its_own_error_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    table = [{"operation": "naoExiste", "allow": [], "deny": ["usuario"]}]
    with environment(monkeypatch, tmp_path, access_matrix=table) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, _ = invoke_json(
            capsys, "authz", "demo", "--run", run_id, "--products-dir", str(products)
        )

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "AUTHZ_CONFIG_INVALID"
    assert envelope["error"]["hint"]


def test_draft_matrix_writes_a_draft_without_touching_the_profile_or_the_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        target = products / "demo" / "target.yml"
        before = target.read_bytes()
        sent = len(server.requests)
        code, envelope, _ = invoke_json(
            capsys, "authz", "demo", "--draft-matrix", "--products-dir", str(products)
        )

        assert code == ExitCode.OK
        assert len(server.requests) == sent
        assert target.read_bytes() == before
    assert "run_id" not in envelope
    assert envelope["data"]["operations"] == 1
    assert envelope["data"]["with_run"] is False
    assert "não vale nada" in envelope["data"]["review"]
    text = draft_file(products).read_text(encoding="utf-8")
    assert "RASCUNHO" in text
    assert text.index("HIPÓTESE") < text.index("access_matrix:")
    items = yaml.safe_load(text)["authz"]["access_matrix"]
    assert items == [
        {
            "operation": "doc",
            "method": "GET",
            "path": "/api/doc/{id}",
            "allow": [],
            "deny": [],
            "review": "pendente",
        }
    ]


def test_draft_matrix_with_a_run_fills_allow_from_the_probe_and_never_deny(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        run_id = probe(capsys, products)
        sent = len(server.requests)
        code, envelope, _ = invoke_json(
            capsys,
            "authz",
            "demo",
            "--draft-matrix",
            "--run",
            run_id,
            "--products-dir",
            str(products),
        )

        assert code == ExitCode.OK
        assert len(server.requests) == sent
    assert envelope["data"]["with_run"] is True
    document = yaml.safe_load(draft_file(products).read_text(encoding="utf-8"))
    [item] = document["authz"]["access_matrix"]
    assert item["allow"] == ["usuario"]
    assert item["deny"] == []


def test_draft_matrix_needs_neither_a_valid_approval_nor_the_stack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        target = products / "demo" / "target.yml"
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        data["authz"] = {"disabled_checks": ["horizontal"]}
        target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        monkeypatch.setenv("HDAST_ZAP_BASE_URL", "http://127.0.0.1:9")
        code, _, _ = invoke_json(
            capsys, "authz", "demo", "--draft-matrix", "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert draft_file(products).is_file()


def test_draft_matrix_never_overwrites_an_existing_draft(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        draft_file(products).write_text("# do dono\n", encoding="utf-8")
        code, envelope, _ = invoke_json(
            capsys, "authz", "demo", "--draft-matrix", "--products-dir", str(products)
        )

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert draft_file(products).read_text(encoding="utf-8") == "# do dono\n"


def test_the_profile_loader_does_not_read_the_draft_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        invoke_json(capsys, "authz", "demo", "--draft-matrix", "--products-dir", str(products))
        code, envelope, _ = invoke_json(
            capsys, "profile", "validate", "demo", "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert envelope["ok"] is True


@pytest.mark.parametrize("extra", [["--dry-run"], ["--check", "horizontal"]])
def test_draft_matrix_does_not_combine_with_the_sending_flags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extra: list[str],
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        code, envelope, _ = invoke_json(
            capsys, "authz", "demo", "--draft-matrix", *extra, "--products-dir", str(products)
        )

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert not draft_file(products).exists()


def test_authz_without_run_and_without_draft_matrix_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        code, envelope, _ = invoke_json(capsys, "authz", "demo", "--products-dir", str(products))

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"

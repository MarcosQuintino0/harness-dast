"""Contrato da aprovação humana do escopo (ADR 0037).

`profile approve` é só da pessoa (terminal interativo, sem `--json`, nome digitado); `profile
approval` e `profile validate` só leem; e todo comando que toca o alvo recusa, com o código
`SCOPE_NOT_APPROVED` (saída 3), quando falta aprovação ou o perfil mudou depois dela. Nenhum
teste abre rede, sobe Docker nem usa o cofre real: a recusa acontece antes de qualquer envio.
"""

import json
from pathlib import Path
from typing import Any

import pytest
import typer

from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.approval_prompt import TerminalApprovalPrompt
from harness_dast.cli.commands import profile as profile_command
from harness_dast.domain.errors import ExitCode
from tests.fakes.approvals import approve_product_on_disk
from tests.fakes.profile_data import dump_yaml, valid_profile_data

pytestmark = pytest.mark.contract

RUN_ID = "2026-11-14T12-00-00Z-demo-abcd"
APPROVAL_KEYS = {"state", "approved_at", "changed_blocks", "message"}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HDAST_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.delenv("HDAST_PRODUCTS_DIR", raising=False)


def write_profile(products: Path, **mutation: Any) -> None:
    data = valid_profile_data("demo")
    for key, value in mutation.items():
        data.setdefault(key, {}).update(value)
    folder = products / "demo"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "target.yml").write_text(dump_yaml(data), encoding="utf-8")
    (folder / "openapi.json").write_text("{}", encoding="utf-8")


@pytest.fixture
def products(tmp_path: Path) -> Path:
    folder = tmp_path / "produtos"
    write_profile(folder)
    return folder


def invoke(
    capsys: pytest.CaptureFixture[str], *args: str, json_mode: bool = True
) -> tuple[int, dict[str, Any], str, str]:
    code = run_app(build_app(), (["--json"] if json_mode else []) + list(args))
    captured = capsys.readouterr()
    parsed = json.loads(captured.out) if json_mode and captured.out.strip() else {}
    return code, parsed, captured.out, captured.err


def approval_file(tmp_path: Path) -> Path:
    return tmp_path / "isolated-hdast-state" / "approvals" / "demo.json"


class ScriptedTerminal:
    """Simula uma pessoa diante do terminal: troca o teste de TTY e a confirmação digitada."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, interactive: bool, answer: bool) -> None:
        self.shown: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
        self.answer = answer
        monkeypatch.setattr(profile_command, "_is_interactive", lambda: interactive)
        monkeypatch.setattr(profile_command, "TerminalApprovalPrompt", lambda: self)

    def confirm(self, product: str, summary: tuple[str, ...], changes: tuple[str, ...]) -> bool:
        self.shown.append((product, summary, changes))
        return self.answer


# ------------------------------------------------------------------ profile approve


def test_approve_without_a_terminal_is_refused_with_config_error_and_writes_nothing(
    products: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope, _, _ = invoke(
        capsys, "profile", "approve", "demo", "--products-dir", str(products)
    )

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert "Só uma pessoa" in envelope["error"]["message"]
    assert not approval_file(tmp_path).exists()


def test_approve_with_json_is_refused_even_in_a_real_terminal(
    products: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = ScriptedTerminal(monkeypatch, interactive=True, answer=True)

    code, envelope, _, _ = invoke(
        capsys, "profile", "approve", "demo", "--products-dir", str(products)
    )

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert terminal.shown == []
    assert not approval_file(tmp_path).exists()


def test_wrong_confirmation_does_not_approve(
    products: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = ScriptedTerminal(monkeypatch, interactive=True, answer=False)

    code, _, out, _ = invoke(
        capsys, "profile", "approve", "demo", "--products-dir", str(products), json_mode=False
    )

    assert code == ExitCode.OK
    assert "cancelada" in out
    assert terminal.shown[0][0] == "demo"
    assert not approval_file(tmp_path).exists()


def test_person_confirmation_approves_and_the_file_lives_in_the_state_dir(
    products: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ScriptedTerminal(monkeypatch, interactive=True, answer=True)

    code, _, out, _ = invoke(
        capsys, "profile", "approve", "demo", "--products-dir", str(products), json_mode=False
    )

    assert code == ExitCode.OK
    assert "APROVADO" in out
    record = json.loads(approval_file(tmp_path).read_text(encoding="utf-8"))
    assert record["product"] == "demo"
    assert not (products / "demo" / "approval.json").exists()


def test_terminal_prompt_shows_the_summary_and_accepts_only_the_exact_product_name(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter(["demo", "DEMO", "", "demo "])
    monkeypatch.setattr(typer, "prompt", lambda *a, **k: next(answers))
    prompt = TerminalApprovalPrompt()
    summary = ("Produto: demo", "Pode alcançar (e só isto):")

    results = [prompt.confirm("demo", summary, ("limits: limites de carga",)) for _ in range(4)]

    assert results == [True, False, False, True]
    err = capsys.readouterr().err
    assert "Pode alcançar (e só isto):" in err
    assert "limits: limites de carga" in err
    assert "exige nova aprovação sua" in err


# ------------------------------------------------------------------ approval / validate


def test_approval_command_reports_each_state_and_never_needs_a_terminal(
    products: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ("profile", "approval", "demo", "--products-dir", str(products))

    code, envelope, _, _ = invoke(capsys, *args)
    assert code == ExitCode.OK
    assert set(envelope["data"]) == {"product", *APPROVAL_KEYS}
    assert envelope["data"]["state"] == "not_approved"

    approve_product_on_disk(products, "demo")
    _, envelope, _, _ = invoke(capsys, *args)
    assert envelope["data"]["state"] == "approved"
    assert set(envelope["data"]) == {"product", *APPROVAL_KEYS}

    write_profile(products, limits={"requests_per_second": 9})
    _, envelope, _, _ = invoke(capsys, *args)
    assert envelope["data"]["state"] == "changed"
    assert envelope["data"]["changed_blocks"] == ["limits"]

    approval_file(tmp_path).write_text("{ quebrado", encoding="utf-8")
    code, envelope, _, _ = invoke(capsys, *args)
    assert code == ExitCode.OK
    assert envelope["data"]["state"] == "invalid"


def test_validate_shows_the_approval_state_without_failing_or_changing_runnable(
    products: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ("profile", "validate", "demo", "--products-dir", str(products))

    code, envelope, _, _ = invoke(capsys, *args)
    assert code == ExitCode.OK
    assert envelope["data"]["runnable"] is True
    assert set(envelope["data"]["approval"]) == APPROVAL_KEYS
    assert envelope["data"]["approval"]["state"] == "not_approved"

    approve_product_on_disk(products, "demo")
    write_profile(products, scope={"deny_paths": []})
    code, envelope, _, _ = invoke(capsys, *args)
    assert code == ExitCode.OK
    assert envelope["data"]["runnable"] is True
    assert envelope["data"]["approval"]["state"] == "changed"
    assert envelope["data"]["approval"]["changed_blocks"] == ["scope.deny_paths"]


def test_validate_human_output_has_the_approval_line(
    products: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, out, _ = invoke(
        capsys, "profile", "validate", "demo", "--products-dir", str(products), json_mode=False
    )

    assert "Aprovação do escopo: NÃO aprovado" in out


# ------------------------------------------------------------------ comandos que tocam o alvo

TOUCHING = {
    "preflight": ("preflight", "demo"),
    "probe": ("probe", "demo"),
    "scan": ("scan", "demo", "--run", RUN_ID),
    "authz": ("authz", "demo", "--run", RUN_ID),
    "run": ("run", "demo"),
    "retestar": ("retestar", "demo", "--run", RUN_ID),
    "stack-up": ("stack", "up", "demo"),
    "cleanup": ("cleanup", "demo", "--run", RUN_ID, "--dry-run"),
}


@pytest.mark.parametrize("name", list(TOUCHING))
def test_every_command_that_touches_the_target_refuses_without_approval(
    name: str, products: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope, _, _ = invoke(capsys, *TOUCHING[name], "--products-dir", str(products))

    assert code == ExitCode.SCOPE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "SCOPE_NOT_APPROVED"
    assert "hdast profile approve demo" in envelope["error"]["hint"]


@pytest.mark.parametrize(
    ("name", "mutation", "block"),
    [
        ("preflight", {"scope": {"deny_paths": []}}, "scope.deny_paths"),
        ("probe", {"limits": {"max_duration_minutes": 61}}, "limits"),
        ("scan", {"environment": {"name": "outro"}}, "environment"),
        ("authz", {"scope": {"path_mode": "wide"}}, "scope.path_mode"),
        (
            "run",
            {"scope": {"authorization": {"reference": "CHG-1", "valid_until": "2999-12-31"}}},
            "scope.authorization",
        ),
        ("stack-up", {"limits": {"requests_per_second": 7}}, "limits"),
        ("cleanup", {"scope": {"windows": ["sab 10:00-12:00 UTC"]}}, "scope.windows"),
    ],
)
def test_every_command_that_touches_the_target_refuses_a_profile_changed_after_approval(
    name: str,
    mutation: dict[str, Any],
    block: str,
    products: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    approve_product_on_disk(products, "demo")
    write_profile(products, **mutation)

    code, envelope, _, _ = invoke(capsys, *TOUCHING[name], "--products-dir", str(products))

    assert code == ExitCode.SCOPE
    assert envelope["error"]["code"] == "SCOPE_NOT_APPROVED"
    assert block in envelope["error"]["message"]
    assert "mudou desde a aprovação" in envelope["error"]["message"]


@pytest.mark.parametrize("name", ["preflight", "probe", "run", "stack-up"])
def test_corrupted_approval_file_also_blocks_the_commands(
    name: str, products: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    approve_product_on_disk(products, "demo")
    approval_file(tmp_path).write_text("", encoding="utf-8")

    code, envelope, _, _ = invoke(capsys, *TOUCHING[name], "--products-dir", str(products))

    assert code == ExitCode.SCOPE
    assert envelope["error"]["code"] == "SCOPE_NOT_APPROVED"
    assert "ilegível" in envelope["error"]["message"]


def test_changing_a_field_outside_the_protection_keeps_the_approval(
    products: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    approve_product_on_disk(products, "demo")
    write_profile(products, probe={"health_path": "/api/saude"})

    _, envelope, _, _ = invoke(
        capsys, "profile", "approval", "demo", "--products-dir", str(products)
    )

    assert envelope["data"]["state"] == "approved"


def test_read_only_commands_work_without_approval(
    products: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for args in (
        ("profile", "validate", "demo"),
        ("profile", "approval", "demo"),
        ("secret", "list", "demo"),
    ):
        code, envelope, _, _ = invoke(capsys, *args, "--products-dir", str(products))

        assert code == ExitCode.OK
        assert envelope["ok"] is True


def test_the_approval_is_per_product(
    products: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    other = valid_profile_data("outro")
    (products / "outro").mkdir()
    (products / "outro" / "target.yml").write_text(dump_yaml(other), encoding="utf-8")
    (products / "outro" / "openapi.json").write_text("{}", encoding="utf-8")
    approve_product_on_disk(products, "outro")

    code, envelope, _, _ = invoke(capsys, "preflight", "demo", "--products-dir", str(products))

    assert code == ExitCode.SCOPE
    assert envelope["error"]["code"] == "SCOPE_NOT_APPROVED"

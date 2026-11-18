"""Reúne os casos do hook e a lista integral das negações anteriores para o contrato."""

import importlib.util
import io
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
GUARD = ROOT / ".claude" / "hooks" / "guard.py"
SETTINGS = ROOT / ".claude" / "settings.json"
BASELINE_DENY = (
    "Read(**/.env*)",
    "Read(!.env.example)",
    "Read(//**/hdast/stack.json)",
    "Edit(//**/hdast/approvals/**)",
    "Write(//**/hdast/approvals/**)",
    "Bash(curl:*)",
    "Bash(wget:*)",
    "Bash(printenv:*)",
    "Bash(uv run hdast cleanup:*)",
    "Bash(uv run hdast --json cleanup:*)",
    "Bash(hdast cleanup:*)",
    "Bash(hdast --json cleanup:*)",
    "PowerShell(Invoke-WebRequest:*)",
    "PowerShell(Invoke-RestMethod:*)",
    "PowerShell(curl:*)",
    "PowerShell(uv run hdast cleanup:*)",
    "PowerShell(uv run hdast --json cleanup:*)",
    "PowerShell(hdast cleanup:*)",
    "PowerShell(hdast --json cleanup:*)",
    "Bash(uv run hdast secret set:*)",
    "Bash(uv run hdast --json secret set:*)",
    "Bash(hdast secret set:*)",
    "Bash(hdast --json secret set:*)",
    "Bash(uv run hdast secret delete:*)",
    "Bash(uv run hdast --json secret delete:*)",
    "Bash(hdast secret delete:*)",
    "Bash(hdast --json secret delete:*)",
    "PowerShell(uv run hdast secret set:*)",
    "PowerShell(uv run hdast --json secret set:*)",
    "PowerShell(hdast secret set:*)",
    "PowerShell(hdast --json secret set:*)",
    "PowerShell(uv run hdast secret delete:*)",
    "PowerShell(uv run hdast --json secret delete:*)",
    "PowerShell(hdast secret delete:*)",
    "PowerShell(hdast --json secret delete:*)",
    "Bash(uv run hdast profile approve:*)",
    "Bash(uv run hdast --json profile approve:*)",
    "Bash(hdast profile approve:*)",
    "Bash(hdast --json profile approve:*)",
    "PowerShell(uv run hdast profile approve:*)",
    "PowerShell(uv run hdast --json profile approve:*)",
    "PowerShell(hdast profile approve:*)",
    "PowerShell(hdast --json profile approve:*)",
    "Bash(uv run hdast finding acknowledge:*)",
    "Bash(uv run hdast --json finding acknowledge:*)",
    "Bash(hdast finding acknowledge:*)",
    "Bash(hdast --json finding acknowledge:*)",
    "PowerShell(uv run hdast finding acknowledge:*)",
    "PowerShell(uv run hdast --json finding acknowledge:*)",
    "PowerShell(hdast finding acknowledge:*)",
    "PowerShell(hdast --json finding acknowledge:*)",
    "Bash(uv run hdast mutation release:*)",
    "Bash(uv run hdast --json mutation release:*)",
    "Bash(hdast mutation release:*)",
    "Bash(hdast --json mutation release:*)",
    "PowerShell(uv run hdast mutation release:*)",
    "PowerShell(uv run hdast --json mutation release:*)",
    "PowerShell(hdast mutation release:*)",
    "PowerShell(hdast --json mutation release:*)",
    "WebFetch",
    "WebSearch",
    "Edit(products/*/cleanup/**)",
)


@pytest.fixture(scope="module")
def guard() -> ModuleType:
    spec = importlib.util.spec_from_file_location("claude_guard", GUARD)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _call(guard: ModuleType, tool: str, **tool_input: object) -> tuple[int, str]:
    stdin = io.StringIO(json.dumps({"tool_name": tool, "tool_input": tool_input}))
    stderr = io.StringIO()
    return guard.run(stdin, stderr), stderr.getvalue()


@pytest.mark.parametrize(
    ("tool", "command", "reserved"),
    [
        ("Bash", "hdast profile approve produto", "profile approve"),
        ("Bash", "uv run hdast --json profile approve x", "profile approve"),
        ("Bash", "python -m harness_dast secret set NOME", "secret set"),
        ("Bash", "python3.12 -m harness_dast secret --json delete NOME", "secret delete"),
        ("Bash", "/opt/hdast/bin/hdast finding acknowledge x --json", "finding acknowledge"),
        ("PowerShell", r'& "C:\Program Files\hdast.exe" "mutation" release x', "mutation release"),
        ("PowerShell", r"& '.\.venv\Scripts\hdast.exe' '--json' 'cleanup' x", "cleanup"),
        ("Bash", "hdast cleanup x --dry-run", "cleanup"),
        ("Bash", "uv run --project . .venv/bin/hdast --json profile approve x", "profile approve"),
        ("Bash", "sh -c 'hdast profile approve x'", "profile approve"),
    ],
)
def test_denies_human_command_when_invoked(
    guard: ModuleType, tool: str, command: str, reserved: str
) -> None:
    code, error = _call(guard, tool, command=command)

    assert (code, error) == (2, f"hdast {reserved} barrado. Somente uma pessoa pode executá-lo.\n")


@pytest.mark.parametrize(
    ("tool", "command"),
    [
        ("Bash", "curl example.invalid"),
        ("Bash", "/usr/bin/curl example.invalid"),
        ("Bash", "c'url' example.invalid"),
        ("PowerShell", r'& "C:\Program Files\curl\CURL.EXE" example.invalid'),
        ("Bash", "wget example.invalid"),
        ("PowerShell", "Invoke-WebRequest example.invalid"),
        ("PowerShell", "Invoke-RestMethod example.invalid"),
        ("PowerShell", "iwr example.invalid"),
        ("PowerShell", "irm example.invalid"),
        ("Bash", "http example.invalid"),
        ("Bash", "https example.invalid"),
        ("Bash", "nc example.invalid 443"),
        ("Bash", "ncat example.invalid 443"),
        ("Bash", "telnet example.invalid 443"),
        ("Bash", "openssl s_client -connect example.invalid:443"),
        ("Bash", "python -c \"import httpx; httpx.get('https://example.invalid')\""),
        ("Bash", "python -c 'import requests'"),
        ("Bash", "uv run python -c 'import urllib.request'"),
        ("Bash", "python -c 'import http.client'"),
        ("Bash", "python -c 'from socket import socket'"),
        ("Bash", "python -c 'import aiohttp'"),
        ("Bash", "node -e \"fetch('https://example.invalid')\""),
        ("PowerShell", "powershell -Command 'New-Object System.Net.WebClient'"),
        ("PowerShell", "pwsh -Command '[System.Net.Http.HttpClient]::new()'"),
        ("Bash", "sh -c 'curl example.invalid'"),
        ("Bash", "bash -lc 'git status && /usr/bin/curl example.invalid'"),
        ("Bash", "git status\ncurl example.invalid"),
        ("Bash", "git status;curl example.invalid"),
    ],
)
def test_denies_client_when_shell_would_use_network(
    guard: ModuleType, tool: str, command: str
) -> None:
    code, error = _call(guard, tool, command=command)

    assert (code, error) == (
        2,
        "Cliente de rede barrado. O agente acessa o alvo somente via hdast.\n",
    )


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Read", {"file_path": ".env"}),
        ("Read", {"file_path": r"C:\projects\test\.ENV.local"}),
        ("Read", {"file_path": "/state/hdast/stack.json"}),
        ("Glob", {"pattern": "**/.env*"}),
        ("Glob", {"path": "C:/state/hdast", "pattern": "stack.json"}),
        ("Grep", {"path": ".env.production", "pattern": "EXAMPLE"}),
        ("Grep", {"glob": "**/.env.*", "pattern": "EXAMPLE"}),
        ("Bash", {"command": "cat .env"}),
        ("Bash", {"command": "cat .env.*"}),
        ("Bash", {"command": "cat < .env"}),
        ("PowerShell", {"command": r'type "C:\state\hdast\stack.json"'}),
        ("PowerShell", {"command": r'Get-Content -LiteralPath "C:\project\.env.test"'}),
        ("Bash", {"command": "printenv EXAMPLE"}),
        ("Bash", {"command": "env"}),
        ("Bash", {"command": "env > example.txt"}),
        ("Bash", {"command": "set"}),
        ("PowerShell", {"command": "Get-ChildItem Env:"}),
        ("PowerShell", {"command": "gci env:"}),
        ("PowerShell", {"command": "dir env:"}),
        ("PowerShell", {"command": "ls env:"}),
    ],
)
def test_denies_secret_when_tool_reads_it(
    guard: ModuleType, tool: str, tool_input: dict[str, str]
) -> None:
    code, error = _call(guard, tool, **tool_input)

    assert (code, error) == (
        2,
        "Leitura de segredo barrada. Somente uma pessoa pode consultar esses dados.\n",
    )


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Edit", {"file_path": "C:/state/hdast/approvals/produto.json"}),
        ("Write", {"file_path": "/state/hdast/run/human-confirmations.json"}),
        ("Edit", {"file_path": ".claude/settings.json"}),
        ("Write", {"file_path": ".claude/hooks/guard.py"}),
        ("NotebookEdit", {"notebook_path": ".claude/hooks/demo.ipynb"}),
        ("NotebookEdit", {"file_path": ".claude/hooks/demo.ipynb"}),
        ("Write", {"file_path": ".mcp.json"}),
        ("Bash", {"command": "echo sample > ~/.local/share/hdast/approvals/produto.json"}),
        ("Bash", {"command": "echo sample>>hdast/approvals/produto.json"}),
        (
            "PowerShell",
            {"command": r'Set-Content -Path "C:\state\hdast\approvals\x.json" -Value x'},
        ),
        ("PowerShell", {"command": "Write-Output x | Out-File .claude/settings.json"}),
        ("Bash", {"command": "sed -i.bak 's/x/y/' .claude/settings.json"}),
        ("Bash", {"command": "cp x .mcp.json"}),
        ("Bash", {"command": "cp -t hdast/approvals x"}),
        ("PowerShell", {"command": "cp -Destination .mcp.json -Path x"}),
        ("Bash", {"command": "mv .claude/settings.json x"}),
        ("Bash", {"command": "rm -rf .claude/hooks"}),
        ("PowerShell", {"command": r'Remove-Item "C:\run\human-confirmations.json"'}),
        ("Bash", {"command": "sh -c 'echo x > hdast/approvals/x.json'"}),
    ],
)
def test_denies_control_when_tool_alters_it(
    guard: ModuleType, tool: str, tool_input: dict[str, str]
) -> None:
    code, error = _call(guard, tool, **tool_input)

    assert (code, error) == (
        2,
        "Alteração de arquivo protegido barrada. Somente uma pessoa pode fazê-la.\n",
    )


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Bash", {"command": "uv run hdast run produto"}),
        ("Bash", {"command": "uv run hdast profile approval produto"}),
        ("Bash", {"command": "uv run hdast secret list"}),
        ("Bash", {"command": "uv run hdast mutation list"}),
        ("Bash", {"command": "git status"}),
        ("Bash", {"command": "git log --format ';' curl"}),
        ("Bash", {"command": "git log --format '>' .claude/settings.json"}),
        ("Bash", {"command": "git status 2>&1"}),
        ("Bash", {"command": "gh pr view"}),
        ("Bash", {"command": "uv run pytest -q"}),
        ("Bash", {"command": "pip show httpx"}),
        ("Bash", {"command": "docker ps"}),
        ("Bash", {"command": "openssl version"}),
        ("Bash", {"command": "python -c 'print(42)'"}),
        ("Bash", {"command": "set -e"}),
        ("Bash", {"command": "env EXAMPLE=value git status"}),
        ("Bash", {"command": "cp .claude/settings.json example.json"}),
        ("Read", {"file_path": ".env.example"}),
        ("Read", {"file_path": "fixtures/stack.json"}),
        ("Bash", {"command": "cat .env.example"}),
        ("Glob", {"pattern": "**/.env.example"}),
        ("Grep", {"pattern": ".env"}),
        ("Edit", {"file_path": ".claude/skills/x/SKILL.md"}),
        ("Write", {"file_path": ".claude/agents/example.md"}),
        ("Bash", {"command": "echo exemplo > .claude/skills/x/SKILL.md"}),
    ],
)
def test_allows_call_when_operation_is_allowed(
    guard: ModuleType, tool: str, tool_input: dict[str, str]
) -> None:
    assert _call(guard, tool, **tool_input) == (0, "")


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "{invalid",
        "null",
        "[]",
        '{"tool_name": "Bash"}',
        '{"tool_name": "Bash", "tool_input": []}',
        '{"tool_input": {"command": "echo exemplo"}}',
        '{"tool_name": 10, "tool_input": {}}',
        '{"tool_name": "Outra", "tool_input": {}}',
        '{"tool_name": "Bash", "tool_input": {}}',
        '{"tool_name": "Bash", "tool_input": {"command": 10}}',
        '{"tool_name": "Bash", "tool_input": {"command": "   \\n"}}',
        """{"tool_name": "Bash", "tool_input": {"command": "echo 'sem fechar"}}""",
        '{"tool_name": "Read", "tool_input": {}}',
        '{"tool_name": "Edit", "tool_input": {"file_path": null}}',
        '{"tool_name": "Write", "tool_input": {"file_path": "\\u0000"}}',
        '{"tool_name": "NotebookEdit", "tool_input": {"notebook_path": {}}}',
        '{"tool_name": "Glob", "tool_input": {"path": "."}}',
        '{"tool_name": "Grep", "tool_input": {"path": [], "pattern": "x"}}',
    ],
)
def test_fails_closed_when_input_is_invalid(guard: ModuleType, payload: str) -> None:
    stderr = io.StringIO()

    code = guard.run(io.StringIO(payload), stderr)

    assert code == 2
    assert stderr.getvalue().startswith("Entrada inválida no hook.")


def test_fails_closed_when_internal_processing_raises(
    guard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_command: str) -> str | None:
        raise RuntimeError("detalhe interno")

    # Injeta uma falha difícil de provocar e verifica a resposta pública do hook.
    monkeypatch.setattr(guard, "_check_shell", fail)

    code, error = _call(guard, "Bash", command="git status")

    assert (code, error) == (2, "Falha interna no hook. Peça a uma pessoa para revisar a trava.\n")


def test_settings_preserve_every_baseline_deny_rule() -> None:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    deny = set(settings["permissions"]["deny"])

    assert set(BASELINE_DENY) <= deny


def test_settings_deny_editing_the_guards_and_mcp_config() -> None:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    deny = set(settings["permissions"]["deny"])

    assert {
        f"{tool}({path})"
        for tool in ("Edit", "Write")
        for path in (".claude/settings.json", ".claude/hooks/**", ".mcp.json")
    } <= deny


def test_settings_register_the_guard_for_the_expected_tools() -> None:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    pre_tool_use = settings["hooks"]["PreToolUse"]

    assert {
        "matcher": "Bash|PowerShell|Read|Edit|Write|NotebookEdit|Glob|Grep",
        "hooks": [
            {
                "type": "command",
                "command": (
                    "uv run --no-project --quiet python "
                    '"$CLAUDE_PROJECT_DIR/.claude/hooks/guard.py"'
                ),
            }
        ],
    } in pre_tool_use

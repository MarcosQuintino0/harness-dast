"""Reúne os casos do hook e a lista integral das negações anteriores para o contrato."""

import importlib.util
import io
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
GUARD = ROOT / "plugin" / "hooks" / "guard.py"
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
    "Bash(hdast demo:*)",
    "Bash(hdast --json demo:*)",
    "Bash(uv run hdast demo:*)",
    "Bash(uv run hdast --json demo:*)",
    "PowerShell(hdast demo:*)",
    "PowerShell(hdast --json demo:*)",
    "PowerShell(uv run hdast demo:*)",
    "PowerShell(uv run hdast --json demo:*)",
    "Bash(uv run hdast profile approve:*)",
    "Bash(uv run hdast --json profile approve:*)",
    "Bash(hdast profile approve:*)",
    "Bash(hdast --json profile approve:*)",
    "PowerShell(uv run hdast profile approve:*)",
    "PowerShell(uv run hdast --json profile approve:*)",
    "PowerShell(hdast profile approve:*)",
    "PowerShell(hdast --json profile approve:*)",
    "Bash(uv run hdast setup:*)",
    "Bash(uv run hdast --json setup:*)",
    "Bash(hdast setup:*)",
    "Bash(hdast --json setup:*)",
    "PowerShell(uv run hdast setup:*)",
    "PowerShell(uv run hdast --json setup:*)",
    "PowerShell(hdast setup:*)",
    "PowerShell(hdast --json setup:*)",
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


@pytest.fixture(autouse=True)
def clone_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(ROOT))


def _call(guard: ModuleType, tool: str, **tool_input: object) -> tuple[int, str]:
    stdin = io.StringIO(json.dumps({"tool_name": tool, "tool_input": tool_input}))
    stderr = io.StringIO()
    return guard.run(stdin, stderr), stderr.getvalue()


@pytest.mark.parametrize(
    ("tool", "command", "reserved"),
    [
        ("Bash", "hdast demo", "demo"),
        ("Bash", "uv run hdast demo --keep", "demo"),
        ("Bash", "hdast --json demo", "demo"),
        ("Bash", "uv run hdast --json demo", "demo"),
        ("PowerShell", "hdast demo", "demo"),
        ("PowerShell", "uv run hdast demo", "demo"),
        ("PowerShell", "hdast --json demo --keep", "demo"),
        ("PowerShell", "uv run hdast --json demo", "demo"),
        ("PowerShell", r"& '.\.venv\Scripts\hdast.exe' 'demo' '--json'", "demo"),
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
        ("Bash", "hdast setup produto", "setup"),
        ("Bash", "uv run hdast setup produto --products-dir x", "setup"),
        ("Bash", "uv run hdast --json setup produto", "setup"),
        ("Bash", "hdast setup --json produto", "setup"),
        ("Bash", "python -m harness_dast setup produto", "setup"),
        ("Bash", "sh -c 'hdast setup x'", "setup"),
        ("PowerShell", r'& ".\.venv\Scripts\hdast.exe" "setup" x', "setup"),
        ("PowerShell", "uv run hdast --json setup x", "setup"),
    ],
)
def test_denies_human_command_when_invoked(
    guard: ModuleType, tool: str, command: str, reserved: str
) -> None:
    code, error = _call(guard, tool, command=command)

    assert (code, error) == (2, f"hdast {reserved} barrado. Somente uma pessoa pode executá-lo.\n")


@pytest.mark.parametrize(
    "command",
    [
        "printf '\\ndemo\\n' | script -q -c \"uv run hdast setup demo\" /dev/null",
        "script -qc 'hdast profile approve demo' /dev/null",
        "timeout 60 uv run hdast setup demo",
        "nohup hdast --json secret set NOME",
        "unbuffer python -m harness_dast mutation release x",
        "winpty hdast.exe finding acknowledge x",
        "env hdast demo",
        "env HDAST_X=1 uv run hdast --json demo --keep",
    ],
)
def test_denies_human_command_when_wrapped_by_another_program(
    guard: ModuleType, command: str
) -> None:
    code, error = _call(guard, "Bash", command=command)

    assert code == 2
    assert "barrado" in error


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "feat(cli): adicionar o comando humano hdast setup"',
        'gh pr create --title "hdast setup" --body "x"',
        'grep -rn "hdast profile approve" docs',
        "rg 'hdast setup' .claude",
    ],
)
def test_allows_human_command_text_when_program_only_quotes_it(
    guard: ModuleType, command: str
) -> None:
    assert _call(guard, "Bash", command=command) == (0, "")


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
        ("Bash", {"command": "cat .claude/settings.json"}),
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
        "matcher": "Bash|PowerShell|Read|Edit|Write|NotebookEdit|Glob|Grep|mcp__.*",
        "hooks": [
            {
                "type": "command",
                "command": (
                    "uv run --no-project --quiet python "
                    '"$' + '{CLAUDE_PROJECT_DIR}/plugin/hooks/guard.py"'
                ),
                "onFailure": "block",
                "timeout": 30,
            }
        ],
    } in pre_tool_use


@pytest.mark.parametrize(
    "command",
    [
        "uvx hdast profile approve x",
        "uvx --from pacote hdast secret set NOME",
        ".venv/bin/hdast cleanup x",
        r".venv\Scripts\hdast.exe mutation release x",
        "uvx hdast setup x",
        ".venv/bin/hdast setup x",
        "echo $(curl example.invalid)",
        "echo `curl example.invalid`",
        "echo \"$(sh -c 'curl example.invalid')\"",
        "cmd /c curl example.invalid",
        "powershell -Command 'curl example.invalid'",
        "pwsh -c 'curl example.invalid'",
        "Start-Process -FilePath curl -ArgumentList example.invalid",
        "Start-Process -FilePath python -ArgumentList '-c', 'import httpx'",
        "pwsh -EncodedCommand ZWNobyB4",
        "powershell -enc ZWNobyB4",
        "pwsh -e ZWNobyB4",
        "cd ~/.local/state/hdast && echo x > approvals/demo.json",
        "tee approvals/demo.json",
        "Copy-Item x approvals/demo.json",
        "Move-Item x approvals/demo.json",
        "New-Item approvals/demo.json",
        "Add-Content approvals/demo.json x",
        "dd if=x of=approvals/demo.json",
        "install x approvals/demo.json",
        "ln -s x approvals/demo.json",
        "git checkout -- approvals/demo.json",
        "git restore approvals/demo.json",
        "git apply approvals/demo.json",
        "git mv x approvals/demo.json",
        "git rm approvals/demo.json",
        "python -c \"open('approvals/demo.json', 'w')\"",
        "python -c \"open('.env').read()\"",
        "python -c \"open('.env.example.local').read()\"",
        "node -e \"read('.env.local')\"",
        "ruby -e \"read('stack.json')\"",
        "perl -e \"read('.env')\"",
        "powershell -Command 'Get-Content .env'",
    ],
)
def test_denies_adversarial_command_when_it_contains_a_restricted_operation(
    guard: ModuleType, command: str
) -> None:
    code, error = _call(guard, "Bash", command=command)

    assert code == 2
    assert error


@pytest.mark.parametrize(
    "command",
    [
        "uvx hdast secret list",
        "uvx --from pacote hdast profile approval x",
        "echo $(git status)",
        "echo `git status`",
        "cmd /c git status",
        "Start-Process -FilePath git -ArgumentList status",
        "python -c \"open('.env.example').read()\"",
        "git diff -- approvals/demo.json",
        "tee reports/demo.json",
    ],
)
def test_allows_similar_command_when_operation_is_permitted(
    guard: ModuleType, command: str
) -> None:
    assert _call(guard, "Bash", command=command) == (0, "")


@pytest.mark.parametrize(
    ("tool", "data"),
    [
        ("Edit", {"file_path": "approvals/demo.json"}),
        ("Write", {"file_path": r"any\approvals\demo.json"}),
        ("Glob", {"pattern": "**/.e*"}),
        ("Glob", {"pattern": ".env*"}),
        ("Glob", {"pattern": ".env.secret*"}),
        ("Glob", {"pattern": "*"}),
        ("Grep", {"path": "src", "glob": "*", "pattern": "example"}),
        ("Grep", {"path": "**/.e*", "pattern": "example"}),
    ],
)
def test_denies_path_when_pattern_or_segment_covers_restricted_file(
    guard: ModuleType, tool: str, data: dict[str, str]
) -> None:
    assert _call(guard, tool, **data)[0] == 2


@pytest.mark.parametrize(
    ("tool", "data"),
    [
        ("Glob", {"pattern": "**/*.py"}),
        ("Grep", {"path": "src", "pattern": "example"}),
        ("Edit", {"file_path": "approved/demo.json"}),
    ],
)
def test_allows_path_when_pattern_or_segment_is_permitted(
    guard: ModuleType, tool: str, data: dict[str, str]
) -> None:
    assert _call(guard, tool, **data) == (0, "")


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "fix: tratar a pasta approvals no proxy"',
        "git add src/harness_dast/domain/approvals.py",
        'gh pr create --title "x" --body "mexe em .claude/settings.json"',
    ],
)
def test_allows_mention_of_control_when_command_does_not_rewrite_files(
    guard: ModuleType, command: str
) -> None:
    assert _call(guard, "Bash", command=command)[0] == 0


@pytest.mark.parametrize(
    "command",
    [
        "git checkout -- .claude/settings.json",
        "git restore .claude/hooks/guard.py",
        "gh pr checkout 12 && echo x > approvals/a.json",
    ],
)
def test_denies_git_or_gh_command_when_it_rewrites_control_files(
    guard: ModuleType, command: str
) -> None:
    assert _call(guard, "Bash", command=command)[0] == 2


def _event(guard: ModuleType, event: dict[str, object]) -> tuple[int, str]:
    stderr = io.StringIO()
    code = guard.run(io.StringIO(json.dumps(event)), stderr)
    return code, stderr.getvalue()


@pytest.mark.parametrize(
    ("cwd", "tool", "tool_input"),
    [
        ("/state/hdast/approvals", "Bash", {"command": "echo x > demo.json"}),
        ("/project/.claude/hooks", "Bash", {"command": "tee guard.py"}),
        ("/project/.claude", "Bash", {"command": "echo x > settings.json"}),
        (r"C:\state\hdast\approvals", "Write", {"file_path": "demo.json"}),
        ("/project/.claude/hooks", "Edit", {"file_path": "guard.py"}),
        ("/project/.claude", "Write", {"file_path": "settings.json"}),
        ("/project/.claude", "Bash", {"command": "python -c \"open('settings.json','w')\""}),
    ],
)
def test_denies_relative_write_when_cwd_resolves_to_protected_path(
    guard: ModuleType, cwd: str, tool: str, tool_input: dict[str, str]
) -> None:
    code, error = _event(guard, {"cwd": cwd, "tool_name": tool, "tool_input": tool_input})

    assert code == 2
    assert "protegido" in error


def test_allows_relative_write_when_cwd_is_unprotected(guard: ModuleType) -> None:
    event: dict[str, object] = {
        "cwd": "/project/src",
        "tool_name": "Write",
        "tool_input": {"file_path": "demo.py"},
    }

    assert _event(guard, event) == (0, "")


@pytest.mark.parametrize(
    "command",
    [
        "git apply changes.patch",
        "git am changes.patch",
        "patch -p1 < changes.patch",
        "$VAR x",
        "${VAR} x",
        "%VAR% x",
        "$env:VAR x",
        "echo x > $VAR",
        "echo x >> ${VAR}",
        "tee %VAR%",
        "Set-Content $env:VAR x",
        "cmd /d /s /c curl x",
        "powershell -NoProfile -Command 'iwr x'",
        "powershell -ExecutionPolicy Bypass -Command 'iwr x'",
        "pwsh -NoProfile -com 'iwr x'",
        "python -B -c 'import httpx'",
        "python -W ignore -c 'import httpx'",
        "node --no-warnings -e \"require('http')\"",
        "bash -l -c 'curl x'",
        "sh -e -c 'curl x'",
        "rg --hidden palavra .env",
        "grep --hidden x hdast/stack.json",
        "python -c 'print(environ)'",
        "python -c 'getenv(\"X\")'",
        "node -e 'console.log(process.env.X)'",
        "powershell -Command 'echo $env:NAME'",
        "Get-ChildItem Env:QUALQUER",
        "gci env:TEST",
        "dir env:TEST",
        "node -e \"require('https')\"",
        "node -e 'http.get(x)'",
        "node -e 'https.get(x)'",
        "node -e 'client.request(x)'",
        "node -e 'axios(x)'",
        "node -e 'net.connect(x)'",
        "node -e 'new WebSocket(x)'",
        "node -e 'new XMLHttpRequest()'",
    ],
)
def test_denies_third_review_case_when_command_is_restricted(
    guard: ModuleType, command: str
) -> None:
    code, error = _call(guard, "Bash", command=command)

    assert code == 2
    assert error


@pytest.mark.parametrize(
    "command",
    [
        "echo $HOME",
        'git commit -m "env"',
        "uv run pytest",
        "rg -n approve src",
        'node -e "console.log(1)"',
        "git diff changes.patch",
        "cmd /d /s /c git status",
        "python -B -c 'print(1)'",
        "powershell -ExecutionPolicy Bypass -Command 'echo ok'",
        "Get-ChildItem src",
        "echo .env.example",
    ],
)
def test_allows_third_review_case_when_command_is_permitted(
    guard: ModuleType, command: str
) -> None:
    assert _call(guard, "Bash", command=command) == (0, "")


@pytest.mark.parametrize("value", [".env", "hdast/stack.json", "approvals/demo.json"])
def test_denies_mcp_when_nested_value_mentions_protected_data(
    guard: ModuleType, value: str
) -> None:
    event: dict[str, object] = {
        "tool_name": "mcp__server__call",
        "tool_input": {"nested": [{"path": value}]},
    }

    assert _event(guard, event)[0] == 2


def test_allows_mcp_when_nested_values_are_safe(guard: ModuleType) -> None:
    event: dict[str, object] = {
        "tool_name": "mcp__server__call",
        "tool_input": {"nested": [{"path": "src/main.py"}]},
    }

    assert _event(guard, event) == (0, "")


@pytest.mark.parametrize(
    "command",
    ["python -m pytest tests/unit -q", "python --version", "node --version", "python3 -V"],
)
def test_allows_interpreter_when_no_inline_code_follows(guard: ModuleType, command: str) -> None:
    assert _call(guard, "Bash", command=command)[0] == 0


@pytest.mark.parametrize(
    "command",
    [
        "python --unknown-flag -c 'import httpx'",
        "node --some-flag -e \"require('https').get('https://x')\"",
    ],
)
def test_denies_inline_code_after_unknown_option(guard: ModuleType, command: str) -> None:
    assert _call(guard, "Bash", command=command)[0] == 2


@pytest.fixture
def products_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = tmp_path / "workspace"
    project.mkdir()
    for directory in ("products", "runs", "cartas"):
        (project / directory).mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    return project


@pytest.mark.parametrize(
    ("manifest", "has_package", "expected"),
    [
        (None, False, 2),
        ('[project]\nname = "harness-dast"\n', False, 2),
        ("[project", True, 2),
        ('[project]\nname = "outro-projeto"\n', True, 2),
        ('[project]\nname = "harness-dast"\n', True, 0),
    ],
)
def test_selects_write_policy_when_project_changes(
    guard: ModuleType,
    products_workspace: Path,
    manifest: str | None,
    has_package: bool,
    expected: int,
) -> None:
    if manifest is not None:
        (products_workspace / "pyproject.toml").write_text(manifest, encoding="utf-8")
    if has_package:
        (products_workspace / "src" / "harness_dast").mkdir(parents=True)

    assert _call(guard, "Write", file_path="README.md")[0] == expected


def test_uses_current_directory_when_project_dir_is_missing(
    guard: ModuleType, products_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    monkeypatch.chdir(products_workspace)

    assert _call(guard, "Write", file_path="README.md")[0] == 2


@pytest.mark.parametrize(
    ("tool", "input_key", "path"),
    [
        ("Edit", "file_path", "products/demo.yml"),
        ("Write", "file_path", "cartas/demo.carta.yml"),
        ("NotebookEdit", "notebook_path", "runs/demo.ipynb"),
    ],
)
def test_allows_edit_when_path_is_inside_product_directories(
    guard: ModuleType, products_workspace: Path, tool: str, input_key: str, path: str
) -> None:
    assert _call(guard, tool, **{input_key: path}) == (0, "")


@pytest.mark.parametrize("path", ["README.md", "../demo.yml", "PRODUCTS/demo.yml", "products/../x"])
def test_denies_edit_when_path_is_outside_product_directories(
    guard: ModuleType, products_workspace: Path, path: str
) -> None:
    assert _call(guard, "Edit", file_path=path) == (2, guard.PRODUCT_DENIED + "\n")


def test_denies_edit_when_absolute_path_leaves_project(
    guard: ModuleType, products_workspace: Path
) -> None:
    path = products_workspace.parent / "other" / "products" / "demo.yml"

    assert _call(guard, "Write", file_path=path.as_posix())[0] == 2


def test_denies_edit_when_symlink_leaves_project(
    guard: ModuleType, products_workspace: Path
) -> None:
    outside = products_workspace.parent / "outside"
    outside.mkdir()
    try:
        (products_workspace / "products" / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("O ambiente não permite criar links simbólicos.")

    assert _call(guard, "Write", file_path="products/link/demo.yml")[0] == 2


@pytest.mark.parametrize("clone", [True, False])
@pytest.mark.parametrize("tool", ["Read", "Write", "Bash"])
@pytest.mark.parametrize("protected", ["plugin", "state"])
def test_denies_access_when_destination_is_private(
    guard: ModuleType,
    products_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    clone: bool,
    tool: str,
    protected: str,
) -> None:
    if clone:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(ROOT))
    home = products_workspace.parent / "home"
    if protected == "plugin":
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
        path = home / ".claude" / "plugins" / "cache" / "private.txt"
    else:
        path = home / "state" / "private.txt"
        monkeypatch.setenv("HDAST_STATE_DIR", str(path.parent))
    inputs = {"command": f"cat '{path.as_posix()}'"} if tool == "Bash" else {"file_path": str(path)}

    assert _call(guard, tool, **inputs) == (2, guard.PROTECTED_DENIED + "\n")


def test_denies_shell_glob_when_it_enters_plugin_cache(guard: ModuleType) -> None:
    result = _call(guard, "Bash", command="cat ~/.claude/plugins/cache/*")

    assert result == (2, guard.PROTECTED_DENIED + "\n")


def test_allows_powershell_literal_destination_with_spaces(
    guard: ModuleType, products_workspace: Path
) -> None:
    destination = products_workspace / "cartas" / "arquivo local.txt"

    result = _call(
        guard, "PowerShell", command=f'Set-Content -LiteralPath "{destination}" -Value x'
    )

    assert result == (0, "")


@pytest.mark.parametrize(
    ("tool", "template"),
    [
        ("Bash", "echo x > {path}"),
        ("Bash", "echo x >> {path}"),
        ("Bash", "echo x | tee -a {path}"),
        ("Bash", "cp products/input.txt {path}"),
        ("Bash", "mv products/input.txt {path}"),
        ("Bash", "rm -rf {path}"),
        ("Bash", "mkdir -p {path}"),
        ("Bash", "touch {path}"),
        ("Bash", "sed -i 's/x/y/' {path}"),
        ("Bash", "install products/input.txt {path}"),
        (
            "Bash",
            "git diff --no-index --no-ext-diff --no-textconv --output={path} -- "
            "products/a.txt products/b.txt",
        ),
        ("PowerShell", "Set-Content -Path {path} -Value x"),
        ("PowerShell", "Write-Output x | Out-File -FilePath {path}"),
        ("PowerShell", "New-Item -Path {path} -ItemType Directory"),
        ("PowerShell", "Remove-Item -LiteralPath {path}"),
        ("PowerShell", "Copy-Item -Destination {path} -Path products/input.txt"),
        ("PowerShell", "Move-Item -Path products/input.txt -Destination {path}"),
    ],
)
@pytest.mark.parametrize(("path", "expected"), [("products/result.txt", 0), ("result.txt", 2)])
def test_checks_explicit_shell_destination(
    guard: ModuleType, products_workspace: Path, tool: str, template: str, path: str, expected: int
) -> None:
    assert _call(guard, tool, command=template.format(path=path))[0] == expected


@pytest.mark.parametrize(
    ("tool", "command", "expected"),
    [
        ("Bash", "python -c \"print(open('products/in.txt', 'r').read())\"", 0),
        ("Bash", "python -c \"open('products/out.txt', 'w')\"", 2),
        ("Bash", 'python -c "print(load())"', 2),
        ("Bash", "python - <<'PY'\nprint(42)\nPY", 0),
        ("Bash", "python - < products/script.py", 2),
        ("Bash", "python - <<'PY'\nopen('products/out.txt', 'w')\nPY", 2),
        ("Bash", "node -e 'console.log(1)'", 0),
        ("PowerShell", "pwsh -Command 'Get-Content products/input.txt'", 0),
        ("PowerShell", "pwsh -Command 'Set-Content products/out.txt x'", 2),
        ("Bash", "hdast profile status example", 0),
        ("Bash", "uv run hdast secret list", 0),
        ("Bash", "uv run hdast setup example", 2),
        ("Bash", "hdast -- setup example", 2),
        ("Bash", "tee products/ok.txt outside.txt", 2),
        ("Bash", "mv outside.txt products/ok.txt", 2),
        ("Bash", "echo x > products/result.txt && touch outside.txt", 2),
        ("Bash", "touch products/$NAME", 2),
        ("Bash", "git init products/repo", 2),
        ("Bash", "pip install --target products/deps pacote", 2),
    ],
)
def test_checks_all_shell_effects_in_products_workspace(
    guard: ModuleType, products_workspace: Path, tool: str, command: str, expected: int
) -> None:
    assert _call(guard, tool, command=command)[0] == expected


def test_denies_mcp_when_write_contract_is_unknown(
    guard: ModuleType, products_workspace: Path
) -> None:
    assert _call(guard, "mcp__example__write", path="products/demo.yml")[0] == 2


@pytest.mark.parametrize(
    ("tool", "command"),
    [
        ("Bash", "hdast stack up --build"),
        ("Bash", "hdast --json stack up produto --build"),
        ("Bash", "uv run hdast stack up --build"),
        ("Bash", "HDAST_STACK_BUILD=1 hdast stack up"),
        ("Bash", "export HDAST_STACK_BUILD=1; hdast stack up"),
        ("Bash", "env HDAST_STACK_BUILD=reuse hdast stack up"),
        ("PowerShell", "hdast stack up --build"),
    ],
)
def test_denies_stack_build_when_folder_is_products_workspace(
    guard: ModuleType, products_workspace: Path, tool: str, command: str
) -> None:
    assert _call(guard, tool, command=command) == (2, guard.STACK_BUILD_DENIED + "\n")


@pytest.mark.parametrize(
    "command",
    ["hdast stack up", "hdast --json stack up produto", "hdast stack pull", "hdast probe produto"],
)
def test_allows_stack_commands_without_build_when_folder_is_products_workspace(
    guard: ModuleType, products_workspace: Path, command: str
) -> None:
    assert _call(guard, "Bash", command=command) == (0, "")


@pytest.mark.parametrize(
    "command", ["hdast stack up --build", "HDAST_STACK_BUILD=1 hdast stack up"]
)
def test_keeps_stack_build_untouched_when_folder_is_clone(guard: ModuleType, command: str) -> None:
    # `clone_workspace` (autouse) aponta o projeto para o clone: a regra nova não vale aqui.
    assert _call(guard, "Bash", command=command) == (0, "")


def test_denies_stack_build_variable_when_powershell_sets_it(
    guard: ModuleType, products_workspace: Path
) -> None:
    code, _ = _call(guard, "PowerShell", command="$env:HDAST_STACK_BUILD = '1'; hdast stack up")

    assert code == 2


@pytest.fixture
def plugin_root(products_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = products_workspace.parent / "home" / ".claude" / "plugins" / "cache" / "hdast" / "1.0"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (root / "skills").mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root.parents[3]))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
    monkeypatch.setenv("HDAST_STATE_DIR", str(products_workspace.parent / "state"))
    return root


@pytest.mark.parametrize(
    ("tool", "inputs"),
    [
        ("Read", {"file_path": ".claude-plugin/plugin.json"}),
        ("Read", {"file_path": "skills/SKILL.md"}),
        ("Glob", {"pattern": "skills/**/SKILL.md"}),
        ("Glob", {"pattern": "**/*.md"}),
        ("Grep", {"pattern": "preparar"}),
    ],
)
def test_allows_plugin_read_when_target_is_inside_active_plugin_root(
    guard: ModuleType, plugin_root: Path, tool: str, inputs: dict[str, str]
) -> None:
    inputs = dict(inputs)
    if tool == "Read":
        inputs["file_path"] = str(plugin_root / inputs["file_path"])
    else:
        inputs["path"] = str(plugin_root)

    assert _call(guard, tool, **inputs) == (0, "")


@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_denies_plugin_write_when_target_is_inside_active_plugin_root(
    guard: ModuleType, plugin_root: Path, tool: str
) -> None:
    code, _ = _call(guard, tool, file_path=str(plugin_root / "skills" / "x.md"))

    assert code == 2


def test_denies_plugin_shell_read_when_target_is_inside_active_plugin_root(
    guard: ModuleType, plugin_root: Path
) -> None:
    assert _call(guard, "Bash", command=f"cat '{plugin_root.as_posix()}/skills'")[0] == 2


def test_denies_read_when_plugin_root_sibling_or_state_is_requested(
    guard: ModuleType, plugin_root: Path, products_workspace: Path
) -> None:
    state = products_workspace.parent / "state"
    state.mkdir()

    assert _call(guard, "Read", file_path=str(plugin_root.parent / "outro.txt"))[0] == 2
    assert _call(guard, "Read", file_path=str(state / "approvals" / "x.json"))[0] == 2
    assert _call(guard, "Glob", pattern="*", path=str(state))[0] == 2
    assert _call(guard, "Glob", pattern="*", path=str(plugin_root.parent))[0] == 2
    assert _call(guard, "Grep", pattern="x", path=str(plugin_root.parent.parent))[0] == 2


def test_denies_read_when_state_dir_lives_under_plugin_root(
    guard: ModuleType, plugin_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = plugin_root / "estado"
    state.mkdir()
    monkeypatch.setenv("HDAST_STATE_DIR", str(state))

    assert _call(guard, "Read", file_path=str(state / "approvals.json"))[0] == 2
    assert _call(guard, "Grep", pattern="x", path=str(state))[0] == 2


def test_denies_read_when_plugin_secret_name_is_requested(
    guard: ModuleType, plugin_root: Path
) -> None:
    assert _call(guard, "Read", file_path=str(plugin_root / ".env"))[0] == 2


def test_denies_plugin_read_when_clone_mode_is_active(
    guard: ModuleType, plugin_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(ROOT))
    manifest = plugin_root / ".claude-plugin" / "plugin.json"

    code, reason = _call(guard, "Read", file_path=str(manifest))

    assert (code, reason) == (2, guard.PROTECTED_DENIED + "\n")


@pytest.mark.parametrize(
    "command",
    [
        "uname",
        "uname -a",
        "whoami",
        "pwd",
        "ls",
        "df -h",
        "free -h",
        "nproc",
        "uv --version",
        "uv tool list",
        "uv tool dir",
        "hdast --version",
        "hdast doctor",
        "hdast --help",
        "docker --version",
        "docker version",
        "docker info",
        "docker ps",
        "wsl --status",
        "wsl --list --verbose",
        "winget --version",
        "systeminfo",
        "uname -a; uv --version; hdast --version; docker --version",
        "docker info && df -h || pwd",
        "uv tool list | grep hdast",
        "docker ps | head -n 5",
        "df -h | tail -2 | wc -l",
        "uv tool list | sort -r | cut -d ' ' -f 1",
    ],
)
def test_allows_read_only_diagnostic_when_folder_is_products_workspace(
    guard: ModuleType, products_workspace: Path, command: str
) -> None:
    assert _call(guard, "Bash", command=command) == (0, "")


@pytest.mark.parametrize(
    "command",
    [
        "grep -A4 '\"servers\"' inputs/openapi.json",
        "grep servers inputs/openapi.json",
        "grep -o '\"servers\"[^]]*]' inputs/openapi.json | head -3",
        "find . -maxdepth 3",
        "ls -la && find . -maxdepth 3 | head -50",
        "hdast doctor 2>&1",
        "hdast doctor 2>&1 | tail -30",
        "uv run hdast doctor 2>&1 | tail -30",
        "hdast doctor >&2",
        "hdast doctor 1>&2",
        "cat >> products/crapi/data-rules.yml <<'EOF'\nresource: example\nEOF",
        "cat > products/crapi/x.yml <<'EOF'\nvalue: '$(literal)'\nEOF\n",
    ],
)
def test_allows_literal_shell_operations_when_folder_is_products_workspace(
    guard: ModuleType, products_workspace: Path, command: str
) -> None:
    assert _call(guard, "Bash", command=command) == (0, "")


@pytest.mark.parametrize(
    "command",
    [
        "echo x > fora.txt",
        "cat > ../fora.yml <<'EOF'\nvalue: 1\nEOF",
        "cat > products/crapi/x.yml <<'EOF'\nvalue: 1\nEOF\necho x > fora.txt",
        "cat > products/crapi/x.yml <<EOF\nvalue: 1\nEOF",
        "find . -delete",
        r"find . -exec rm {} \;",
        r"find . -execdir rm {} \;",
        r"find . -ok rm {} \;",
        r"find . -okdir rm {} \;",
        "find . -fprint fora.txt",
        "find . -fprint0 fora.txt",
        "find . -fprintf fora.txt x",
        "find . -fls fora.txt",
        "grep -r senha ~/.claude",
        "grep -rn servers inputs",
        "grep senha .env",
        "grep -o 'senha' .env",
        "grep -f inputs/patterns inputs/openapi.json",
        "hdast doctor 2> fora.log",
        "hdast doctor > fora.txt 2>&1",
        "hdast doctor >&fora.log",
        "hdast doctor >&2\u00a0",
        "hdast stack up --build",
        "cat .env",
    ],
)
def test_denies_unsafe_shell_operations_when_folder_is_products_workspace(
    guard: ModuleType, products_workspace: Path, command: str
) -> None:
    assert _call(guard, "Bash", command=command)[0] == 2


def test_keeps_output_outside_products_allowed_when_folder_is_clone(guard: ModuleType) -> None:
    assert _call(guard, "Bash", command="hdast doctor > fora.txt 2>&1") == (0, "")


@pytest.mark.parametrize("command", ["find . -maxdepth 3", "grep -o 'x' private/report.txt"])
def test_denies_shell_read_when_path_covers_private_state(
    guard: ModuleType, products_workspace: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    monkeypatch.setenv("HDAST_STATE_DIR", str(products_workspace / "private"))
    assert _call(guard, "Bash", command=command)[0] == 2


@pytest.mark.parametrize(
    "command", ["Get-PSDrive", "systeminfo", "wsl --status", "winget --version"]
)
def test_allows_read_only_diagnostic_when_powershell_runs_it(
    guard: ModuleType, products_workspace: Path, command: str
) -> None:
    assert _call(guard, "PowerShell", command=command) == (0, "")


@pytest.mark.parametrize(
    "command",
    [
        "docker run alpine",
        "docker exec x sh",
        "docker --version --help x",
        "docker compose up",
        "docker image rm x",
        "uv tool install pacote",
        "uv tool uninstall hdast",
        "uv pip install x",
        "winget install x",
        "wsl --unregister x",
        "wsl --install",
        "uname -a x",
        "df /etc",
        "cat ~/.claude/.credentials.json",
        "uv --version; docker run alpine",
        "uv --version && cat .env",
        "docker info || curl http://x",
        "echo $(whoami)",
        "echo `whoami`",
        "uname -$(id)",
        "grep x ~/.claude/.credentials.json",
        "uv tool list | sort -o saida.txt",
        "uv tool list | tee fora.txt",
        "uv tool list | grep -r x",
        "uv tool list | xargs rm",
        "uv tool list | sh",
        "grep hdast",
        "head -n 5",
    ],
)
def test_denies_command_when_diagnostic_does_not_pass_alone(
    guard: ModuleType, products_workspace: Path, command: str
) -> None:
    assert _call(guard, "Bash", command=command)[0] == 2


def test_denies_powershell_install_when_diagnostic_list_does_not_cover_it(
    guard: ModuleType, products_workspace: Path
) -> None:
    assert _call(guard, "PowerShell", command="Get-PSDrive; winget install x")[0] == 2
    assert _call(guard, "PowerShell", command="Get-PSDrive -Name C")[0] == 2


@pytest.mark.parametrize(
    "command",
    [
        "rmdir products/crapi",
        "rm products/crapi/decision-log.md",
        "rm -f runs/20260101/log.txt",
        "rm -rf products/crapi",
        "rm -r runs/antiga",
        "rm -rf cartas/velha",
        "rm -rf ./products/crapi",
        "rm products/a.md products/b.md",
        "rmdir products/crapi && rm cartas/x.yml",
    ],
)
def test_allows_removal_when_target_is_inside_permitted_folders(
    guard: ModuleType, products_workspace: Path, command: str
) -> None:
    assert _call(guard, "Bash", command=command) == (0, "")


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf products",
        "rm -rf runs",
        "rm -rf cartas",
        "rm -rf products/",
        "rm -rf products/.",
        "rm -rf products runs cartas",
        "rm -rf .",
        "rm -rf ..",
        "rm -rf ../products/x",
        "rm -rf products/..",
        "rm -rf products/../src",
        "rm -rf /",
        "rm -rf src",
        "rm README.md",
        "rm -rf",
        "rm -rf products/*",
        "rm -rf $HOME",
        "rm -R products/x",
        "rmdir products",
        "rmdir -p products/a/b",
        "rmdir",
        "rmdir src",
        "rm -rf products/x; rm -rf src",
        "rm -rf products/x/cleanup",
    ],
)
def test_denies_removal_when_target_is_outside_or_is_a_permitted_folder(
    guard: ModuleType, products_workspace: Path, command: str
) -> None:
    assert _call(guard, "Bash", command=command)[0] == 2


def test_denies_removal_when_symlink_leaves_permitted_folders(
    guard: ModuleType, products_workspace: Path
) -> None:
    outside = products_workspace.parent / "outside"
    outside.mkdir()
    try:
        (products_workspace / "products" / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Sem permissão para criar link simbólico.")

    assert _call(guard, "Bash", command="rm -rf products/link")[0] == 2


def test_denies_powershell_removal_when_target_is_a_permitted_folder(
    guard: ModuleType, products_workspace: Path
) -> None:
    assert _call(guard, "PowerShell", command="Remove-Item products/crapi")[0] == 0
    assert _call(guard, "PowerShell", command="Remove-Item products")[0] == 2
    assert _call(guard, "PowerShell", command="Remove-Item README.md")[0] == 2

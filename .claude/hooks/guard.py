"""Decide se uma chamada do Claude Code pode prosseguir, sem executá-la."""

import io
import json
import posixpath
import re
import sys
from collections.abc import Iterator
from typing import TextIO

HUMAN_COMMANDS = (
    ("profile", "approve"),
    ("secret", "set"),
    ("secret", "delete"),
    ("finding", "acknowledge"),
    ("mutation", "release"),
    ("cleanup",),
)
NETWORK_CLIENTS = frozenset(
    (
        "curl",
        "wget",
        "invoke-webrequest",
        "invoke-restmethod",
        "iwr",
        "irm",
        "http",
        "https",
        "nc",
        "ncat",
        "telnet",
    )
)
INLINE_NETWORK = re.compile(
    r"\b(?:requests|httpx|urllib|http\.client|socket|aiohttp)\b|\bfetch\s*\("
)
POWERSHELL_NETWORK = re.compile(r"\b(?:net\.webclient|httpclient)\b")
PYTHON = re.compile(r"python(?:3(?:\.\d+)?)?")
SHELLS = frozenset(("sh", "bash", "dash", "zsh", "ksh"))
POWERSHELLS = frozenset(("powershell", "pwsh"))
FILE_READERS = frozenset(("cat", "type", "get-content"))
FILE_WRITERS = frozenset(("set-content", "out-file", "mv", "rm", "remove-item"))
ENV_LISTERS = frozenset(("get-childitem", "gci", "dir", "ls"))
SHELL_TOOLS = frozenset(("Bash", "PowerShell"))
WRITE_TOOLS = frozenset(("Edit", "Write", "NotebookEdit"))
SEARCH_TOOLS = frozenset(("Glob", "Grep"))
# Em aspas duplas, preserva as barras mesmo quando precedem aspas no código inline.
QUOTED_PART = re.compile(r"""'[^']*'|"(?:\\["\\]|[^"\\]|\\(?!["\\]))*["]""")
SHELL_TOKEN = re.compile(
    r"(?P<comment>\#[^\n]*)"
    r"|(?P<redirect>\d*(?:&>>?|>&|>\||>>?|<&|<<?))"
    r"|(?P<separator>[;&|()\n])"
    rf"""|(?P<word>(?:{QUOTED_PART.pattern}|[^\s'";&|()<>])+)"""
    r"|(?P<space>[^\S\n]+)|(?P<invalid>.)"
)
UV_VALUE_OPTIONS = frozenset(
    (
        "--directory",
        "--project",
        "--python",
        "-p",
        "--with",
        "--with-editable",
        "--with-requirements",
    )
)

NETWORK_DENIED = "Cliente de rede barrado. O agente acessa o alvo somente via hdast."
SENSITIVE_READ_DENIED = "Leitura de segredo barrada. Somente uma pessoa pode consultar esses dados."
WRITE_DENIED = "Alteração de arquivo protegido barrada. Somente uma pessoa pode fazê-la."
INVALID_INPUT = "Entrada inválida no hook. Corrija a chamada da ferramenta antes de tentar de novo."
INTERNAL_FAILURE = "Falha interna no hook. Peça a uma pessoa para revisar a trava."


def _normalize_path(path: str) -> str:
    path = path.lower().replace("\\", "/")
    return posixpath.normpath(path)


def _reads_secret(path: str) -> bool:
    path = _normalize_path(path)
    name = posixpath.basename(path)
    return (
        path == "hdast/stack.json"
        or path.endswith("/hdast/stack.json")
        or (
            name != ".env.example"
            and (name == ".env" or name.startswith((".env.", ".env*", ".env?")))
        )
    )


def _writes_control(path: str) -> bool:
    path = f"/{_normalize_path(path).strip('/')}/"
    return path.endswith(
        ("/human-confirmations.json/", "/.claude/settings.json/", "/.mcp.json/")
    ) or ("/hdast/approvals/" in path or "/.claude/hooks/" in path)


def _executable(word: str) -> str:
    name = posixpath.basename(_normalize_path(word))
    stem, extension = posixpath.splitext(name)
    return stem if extension in {".exe", ".cmd", ".bat", ".ps1"} else name


def _skip_uv_options(words: tuple[str, ...]) -> tuple[str, ...]:
    index = 0
    while index < len(words) and words[index].startswith("-"):
        option = words[index]
        index += 2 if option in UV_VALUE_OPTIONS else 1
        if option == "--":
            break
    return words[index:]


def _normalize_command(words: list[str]) -> tuple[str, ...]:
    command, *arguments = (word.lower() for word in words)
    name, args = _executable(command), tuple(arguments)
    if name == "uv" and args[:1] == ("run",):
        inner = _skip_uv_options(args[1:])
        if inner:
            return _normalize_command(list(inner))
    if PYTHON.fullmatch(name) and args[:2] == ("-m", "harness_dast"):
        name, args = "hdast", args[2:]
    if name == "hdast":
        args = tuple(arg for arg in args if arg != "--json")
    return (name, *args)


def _shell_commands(command: str) -> Iterator[list[tuple[str, str]]]:
    # As aspas mantêm separadores literais no argumento e preservam barras de caminhos Windows.
    tokens: list[tuple[str, str]] = []
    for match in SHELL_TOKEN.finditer(command):
        kind = match.lastgroup
        if kind == "invalid":
            raise ValueError(INVALID_INPUT)
        if kind == "separator" and tokens:
            yield tokens
            tokens = []
        if kind == "word":
            tokens.append((kind, QUOTED_PART.sub(lambda part: part[0][1:-1], match[0])))
        if kind == "redirect":
            tokens.append((kind, match[0]))
    if tokens:
        yield tokens


def _inline_code(name: str, args: tuple[str, ...]) -> str | None:
    if len(args) < 2:
        return None
    flag, code = args[:2]
    if name in SHELLS and re.fullmatch(r"-[a-z]*c[a-z]*", flag):
        return code
    if name in POWERSHELLS and flag in {"-command", "-c"}:
        return " ".join(args[1:])
    if PYTHON.fullmatch(name) and flag == "-c":
        return code
    if name == "node" and flag in {"-e", "--eval"}:
        return code
    return None


def _check_redirection(operator: str, path: str) -> str | None:
    if ">" in operator and _writes_control(path):
        return WRITE_DENIED
    if operator.endswith("<") and not operator.endswith("<<") and _reads_secret(path):
        return SENSITIVE_READ_DENIED
    return None


def _copy_target(args: tuple[str, ...]) -> str:
    for index, arg in enumerate(args):
        option, _, path = arg.partition("=")
        if option in {"-t", "--target-directory", "-destination"}:
            return path or next(iter(args[index + 1 :]), "")
    return args[-1] if args else ""


def _writes_control_with_command(name: str, args: tuple[str, ...]) -> bool:
    if name in {"cp", "copy-item"}:
        return _writes_control(_copy_target(args))
    in_place = name == "sed" and any(arg.startswith(("-i", "--in-place")) for arg in args)
    return (name in FILE_WRITERS or in_place) and any(_writes_control(arg) for arg in args)


def _reads_secret_with_command(name: str, args: tuple[str, ...]) -> bool:
    if name == "printenv" or (name in {"env", "set"} and not args):
        return True
    if name in ENV_LISTERS and any(_normalize_path(arg) == "env:" for arg in args):
        return True
    return name in FILE_READERS and any(_reads_secret(arg) for arg in args)


def _check_inline(name: str, args: tuple[str, ...]) -> str | None:
    code = _inline_code(name, args)
    if code is None:
        return None
    if name in POWERSHELLS and POWERSHELL_NETWORK.search(code):
        return NETWORK_DENIED
    if name in SHELLS or name in POWERSHELLS:
        return _check_shell(code)
    return NETWORK_DENIED if INLINE_NETWORK.search(code) else None


def _check_command(tokens: list[tuple[str, str]]) -> str | None:
    words: list[str] = []
    remaining = iter(tokens)
    for kind, value in remaining:
        if kind == "word":
            words.append(value)
            continue
        target_kind, path = next(remaining, ("", ""))
        if target_kind != "word":
            raise ValueError(INVALID_INPUT)
        if reason := _check_redirection(value, path):
            return reason
    return _check_words(words) if words else None


def _check_words(words: list[str]) -> str | None:
    if not words[0]:
        raise ValueError(INVALID_INPUT)
    command = _normalize_command(words)
    name, args = command[0], command[1:]
    if name == "hdast":
        for reserved in HUMAN_COMMANDS:
            if args[: len(reserved)] == reserved:
                return f"hdast {' '.join(reserved)} barrado. Somente uma pessoa pode executá-lo."
    if name in NETWORK_CLIENTS or (name == "openssl" and args[:1] == ("s_client",)):
        return NETWORK_DENIED
    if _reads_secret_with_command(name, args):
        return SENSITIVE_READ_DENIED
    if _writes_control_with_command(name, args):
        return WRITE_DENIED
    return _check_inline(name, args)


def _check_shell(command: str) -> str | None:
    found_command = False
    for words in _shell_commands(command):
        found_command = True
        if reason := _check_command(words):
            return reason
    if not found_command:
        raise ValueError(INVALID_INPUT)
    return None


def _require_text(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(INVALID_INPUT)
    return value


def _check_search(tool: str, data: dict[str, object]) -> str | None:
    pattern = _require_text(data, "pattern")
    base = _require_text(data, "path") if "path" in data else ""
    selector = ""
    if tool == "Glob":
        selector = pattern
    elif "glob" in data:
        # O padrão de Grep é uma expressão de conteúdo. Os filtros selecionam arquivos.
        selector = _require_text(data, "glob")
    paths = (base, selector, f"{base}/{selector}")
    return SENSITIVE_READ_DENIED if any(_reads_secret(path) for path in paths) else None


def _check_call(event: object) -> str | None:
    if not isinstance(event, dict) or not isinstance(data := event.get("tool_input"), dict):
        raise TypeError(INVALID_INPUT)
    tool = _require_text(event, "tool_name")
    if tool in SHELL_TOOLS:
        return _check_shell(_require_text(data, "command"))
    if tool == "Read":
        return SENSITIVE_READ_DENIED if _reads_secret(_require_text(data, "file_path")) else None
    if tool in WRITE_TOOLS:
        key = "notebook_path" if tool == "NotebookEdit" and "notebook_path" in data else "file_path"
        return WRITE_DENIED if _writes_control(_require_text(data, key)) else None
    if tool in SEARCH_TOOLS:
        return _check_search(tool, data)
    raise ValueError(INVALID_INPUT)


def run(stdin: TextIO, stderr: TextIO) -> int:
    """Lê a chamada em JSON e retorna 0 para liberar ou 2 para barrar."""
    try:
        reason = _check_call(json.load(stdin))
    except (TypeError, ValueError):
        reason = INVALID_INPUT
    except Exception:  # noqa: BLE001 — O Claude Code só bloqueia com código 2.
        reason = INTERNAL_FAILURE
    if reason is None:
        return 0
    stderr.write(f"{reason}\n")
    return 2


if __name__ == "__main__":
    # O Claude Code lê o stderr como UTF-8; no Windows o padrão seria a página de código local.
    for stream in (sys.stdin, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    sys.exit(run(sys.stdin, sys.stderr))

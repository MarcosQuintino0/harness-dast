"""Decide chamadas do Claude Code sem executá-las.

O módulo reúne a validação de entrada e a análise de shell para manter o hook
autônomo, executável com a biblioteca padrão e sem dependências do projeto.
"""

import fnmatch
import io
import itertools
import json
import posixpath
import re
import sys
from collections.abc import Iterator
from typing import TextIO

HUMAN_COMMANDS = (
    ("profile", "approve"),
    ("setup",),
    ("secret", "set"),
    ("secret", "delete"),
    ("finding", "acknowledge"),
    ("mutation", "release"),
    ("cleanup",),
    ("demo",),
)
# Comando humano citado dentro de outro programa (script -c, timeout, nohup, cmd /c...). Um
# lançador de pseudoterminal poderia simular a pessoa no TTY; por isso o texto inteiro é olhado.
HUMAN_COMMAND_TEXT = re.compile(
    r"\b(?:hdast(?:\.exe)?|harness_dast)['\"]?(?:\s+['\"]?--json['\"]?)*\s+['\"]?(?:"
    + "|".join(r"\s+".join(command) for command in HUMAN_COMMANDS)
    + r")\b"
)
# Só citam texto: mensagem de commit, busca e leitura não executam o comando citado.
QUOTES_ONLY = frozenset(("git", "gh"))
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
    r"\b(?:requests|httpx|urllib|http\.client|socket|aiohttp|axios|xmlhttprequest)\b"
    r"|\bfetch\s*\(|\brequire\s*\(\s*['\"]https?['\"]"
    r"|\bhttps?\.(?:get|request)\s*\(|\.request\s*\("
    r"|\bnet\.connect\s*\(|\bnew\s+websocket\b"
)
INLINE_ENVIRONMENT = re.compile(r"\b(?:environ|getenv|process\.env)\b|\$env:", re.IGNORECASE)
VARIABLE = re.compile(r"\$(?:\{[^}]+\}|env:[\w]+|[A-Za-z_]\w*)|%[^%]+%", re.IGNORECASE)
POWERSHELL_NETWORK = re.compile(r"\b(?:net\.webclient|httpclient)\b")
PYTHON = re.compile(r"python(?:3(?:\.\d+)?)?")
SHELLS = frozenset(("sh", "bash", "dash", "zsh", "ksh"))
POWERSHELLS = frozenset(("powershell", "pwsh"))
READ_ONLY = frozenset(
    ("cat", "type", "get-content", "head", "tail", "less", "grep", "rg", "ls", "dir")
)
WRITERS = frozenset(
    (
        "tee",
        "set-content",
        "out-file",
        "add-content",
        "new-item",
        "copy-item",
        "move-item",
        "cp",
        "mv",
        "rm",
        "remove-item",
        "dd",
        "install",
        "ln",
        "sed",
    )
)
ENV_LISTERS = frozenset(("get-childitem", "gci", "dir", "ls"))
# Subcomandos do git que não reescrevem arquivos da pasta de trabalho: citar um caminho
# protegido neles (inclusive numa mensagem de commit) não altera o arquivo.
GIT_NO_WORKTREE_WRITE = frozenset(
    (
        ("diff",),
        ("log",),
        ("show",),
        ("status",),
        ("commit",),
        ("add",),
        ("push",),
        ("fetch",),
        ("grep",),
        ("blame",),
    )
)
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
        "--from",
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
    parts = _normalize_path(path).strip("/").split("/")
    if "approvals" in parts or "human-confirmations.json" in parts or ".mcp.json" in parts:
        return True
    return any(
        part == ".claude" and next_part in {"settings.json", "hooks"}
        for part, next_part in itertools.pairwise(parts)
    )


def _resolve_path(path: str, cwd: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[a-zA-Z]:/", normalized):
        return normalized
    return posixpath.join(cwd.replace("\\", "/"), normalized)


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
    if name == "uvx":
        inner = _skip_uv_options(args)
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
    index = 0
    while index < len(args):
        flag = args[index]
        if not flag.startswith("-"):
            break
        shell_flag = name in SHELLS and re.fullmatch(r"-[a-z]*c[a-z]*", flag)
        ps_flag = name in POWERSHELLS and flag in {
            "-c",
            "-co",
            "-com",
            "-comm",
            "-comma",
            "-comman",
            "-command",
        }
        python_flag = PYTHON.fullmatch(name) and flag == "-c"
        node_flag = name in {"node", "ruby", "perl"} and flag in {"-e", "--eval"}
        if shell_flag or ps_flag or python_flag or node_flag:
            if index + 1 >= len(args):
                raise ValueError(INVALID_INPUT)
            return " ".join(args[index + 1 :]) if ps_flag else args[index + 1]
        if flag in {"-file", "-f"} and name in POWERSHELLS:
            break
        if PYTHON.fullmatch(name) and flag == "-m":
            # Execução de módulo (python -m pytest): não há código inline a analisar.
            break
        try:
            index += _option_step(name, flag)
        except ValueError:
            # Opção desconhecida: em vez de travar o uso normal (--version etc.), procura uma
            # bandeira de código inline mais adiante; se houver, o código é analisado.
            return _later_inline_code(name, args[index + 1 :])
        if index > len(args):
            raise ValueError(INVALID_INPUT)
    return None


def _later_inline_code(name: str, rest: tuple[str, ...]) -> str | None:
    inline_flags = {"-c", "-e", "--eval", "-command", "/c", "/k"}
    for position, arg in enumerate(rest):
        if arg in inline_flags or (name in SHELLS and re.fullmatch(r"-[a-z]*c[a-z]*", arg)):
            if position + 1 >= len(rest):
                raise ValueError(INVALID_INPUT)
            return " ".join(rest[position + 1 :])
    return None


def _option_step(name: str, flag: str) -> int:
    if name in POWERSHELLS:
        if flag in {"-executionpolicy", "-ep", "-windowstyle", "-w", "-workingdirectory"}:
            return 2
        if flag not in {"-noprofile", "-nop", "-noninteractive"}:
            raise ValueError(INVALID_INPUT)
    return _language_option_step(name, flag)


def _language_option_step(name: str, flag: str) -> int:
    if PYTHON.fullmatch(name):
        if flag in {"-w", "-x"}:
            return 2
        if flag not in {"-b", "-bb", "-i", "-o", "-oo", "-s", "-e", "-u", "-v", "-q"}:
            raise ValueError(INVALID_INPUT)
    if name in SHELLS and not re.fullmatch(r"-[a-z]+", flag):
        raise ValueError(INVALID_INPUT)
    if name in {"node", "ruby", "perl"}:
        if flag in {"-r", "--require", "--import"}:
            return 2
        if flag not in {"--no-warnings", "--trace-warnings", "-w"}:
            raise ValueError(INVALID_INPUT)
    return 1


def _check_redirection(operator: str, path: str, cwd: str) -> str | None:
    if ">" in operator and (VARIABLE.search(path) or _writes_control(_resolve_path(path, cwd))):
        return WRITE_DENIED
    if operator.endswith("<") and not operator.endswith("<<") and _reads_secret(path):
        return SENSITIVE_READ_DENIED
    return None


def _mentions_control(text: str, cwd: str = "") -> bool:
    # Examina também caminhos dentro de literais de linguagens e argumentos nomeados.
    parts = re.split(r"""[\s'"\x60(),;=]+""", text)
    return any(_writes_control(_resolve_path(part, cwd)) for part in parts if part)


def _clearly_read_only(name: str, args: tuple[str, ...]) -> bool:
    if name in READ_ONLY:
        return True
    if name == "gh":
        # O gh fala com o GitHub; só o checkout reescreve arquivos locais.
        return args[:2] != ("pr", "checkout")
    return (
        name == "git"
        and args[:1] in GIT_NO_WORKTREE_WRITE
        and not any(arg == "--output" or arg.startswith("--output=") for arg in args)
    )


def _mentions_secret(text: str) -> bool:
    return bool(re.search(r"(?i)(?<![\w])\.env(?!\.example(?![\w.-]))|\bstack\.json\b", text))


def _check_substitutions(command: str, cwd: str) -> str | None:
    # Apenas substituições fora de aspas simples são executadas pelo shell.
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        if char == "'" and quote != '"':
            quote = "" if quote else "'"
        elif char == '"' and quote != "'":
            quote = "" if quote else '"'
        elif quote != "'" and (command.startswith("$(", index) or char == "`"):
            end = _substitution_end(command, index)
            offset = 2 if char == "$" else 1
            if reason := _check_shell(command[index + offset : end], cwd):
                return reason
            index = end
        index += 1
    return None


def _substitution_end(command: str, start: int) -> int:
    if command[start] == "`":
        end = command.find("`", start + 1)
        if end < 0:
            raise ValueError(INVALID_INPUT)
        return end
    depth = 1
    for index in range(start + 2, len(command)):
        if command[index] == "(":
            depth += 1
        elif command[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError(INVALID_INPUT)


def _reads_secret_with_command(name: str, args: tuple[str, ...]) -> bool:
    if name == "printenv" or (name in {"env", "set"} and not args):
        return True
    if name in ENV_LISTERS and any(_normalize_path(arg).startswith("env:") for arg in args):
        return True
    if name == "gh" or (name == "git" and args[:1] in {("commit",), ("add",), ("status",)}):
        return False
    return any(_reads_secret_reference(arg) for arg in args)


def _reads_secret_reference(text: str) -> bool:
    return bool(
        re.search(r"(?i)(?<![\w])\.env(?!\.example(?![\w.-]))", text)
        or re.search(r"(?i)(?<![\w])hdast[\\/]+stack\.json\b", text)
    )


def _check_inline(name: str, args: tuple[str, ...], cwd: str) -> str | None:
    if name in POWERSHELLS and any(
        arg.split(":", 1)[0] in {"-encodedcommand", "-enc", "-e"} for arg in args
    ):
        return "Comando PowerShell codificado barrado. Uma pessoa deve executá-lo."
    if name == "cmd":
        for index, arg in enumerate(args):
            if arg in {"/c", "/k"}:
                return _check_shell(" ".join(args[index + 1 :]), cwd)
        raise ValueError(INVALID_INPUT)
    if name == "start-process":
        return _check_start_process(args, cwd)
    code = _inline_code(name, args)
    if code is None:
        return None
    return _check_inline_code(name, code, cwd)


def _check_inline_code(name: str, code: str, cwd: str) -> str | None:
    if _mentions_secret(code) or INLINE_ENVIRONMENT.search(code):
        return SENSITIVE_READ_DENIED
    if name in POWERSHELLS and POWERSHELL_NETWORK.search(code):
        return NETWORK_DENIED
    if name in SHELLS or name in POWERSHELLS:
        return _check_shell(code, cwd)
    if _mentions_control(code, cwd):
        return WRITE_DENIED
    return NETWORK_DENIED if INLINE_NETWORK.search(code) else None


def _check_start_process(args: tuple[str, ...], cwd: str) -> str | None:
    values = [
        arg.strip(",")
        for arg in args
        if arg.strip(",") not in {"-filepath", "-argumentlist", "-args"}
    ]
    if not values:
        raise ValueError(INVALID_INPUT)
    if reason := _check_words(values, cwd):
        return reason
    return _check_shell(" ".join(values), cwd)


def _check_command(tokens: list[tuple[str, str]], cwd: str) -> str | None:
    words: list[str] = []
    remaining = iter(tokens)
    for kind, value in remaining:
        if kind == "word":
            words.append(value)
            continue
        target_kind, path = next(remaining, ("", ""))
        if target_kind != "word":
            raise ValueError(INVALID_INPUT)
        if reason := _check_redirection(value, path, cwd):
            return reason
    return _check_words(words, cwd) if words else None


def _check_human_command(name: str, args: tuple[str, ...]) -> str | None:
    if name == "hdast":
        for reserved in HUMAN_COMMANDS:
            if args[: len(reserved)] == reserved:
                return f"hdast {' '.join(reserved)} barrado. Somente uma pessoa pode executá-lo."
    # Shells são analisados por recursão (_check_inline), com a mensagem exata do comando.
    analyzed = QUOTES_ONLY | READ_ONLY | SHELLS | POWERSHELLS | {"cmd"}
    if name not in analyzed and HUMAN_COMMAND_TEXT.search(" ".join(args)):
        return "Comando humano do hdast dentro de outro programa barrado. Uma pessoa deve rodá-lo."
    return None


def _check_words(words: list[str], cwd: str) -> str | None:
    if not words[0]:
        raise ValueError(INVALID_INPUT)
    command = _normalize_command(words)
    name, args = command[0], command[1:]
    if VARIABLE.search(name):
        return WRITE_DENIED
    if name == "patch" or (name == "git" and args[:1] in {("apply",), ("am",)}):
        return "Aplicação de patch barrada. Somente uma pessoa pode aplicá-lo."
    if reason := _check_human_command(name, args):
        return reason
    if name in NETWORK_CLIENTS or (name == "openssl" and args[:1] == ("s_client",)):
        return NETWORK_DENIED
    if _reads_secret_with_command(name, args):
        return SENSITIVE_READ_DENIED
    if reason := _check_inline(name, args, cwd):
        return reason
    return _check_write(name, args, cwd)


def _check_write(name: str, args: tuple[str, ...], cwd: str) -> str | None:
    if name in WRITERS and any(VARIABLE.search(arg) for arg in args):
        return WRITE_DENIED
    git_write = name == "git" and args[:1] in {("checkout",), ("restore",), ("mv",), ("rm",)}
    if git_write and any(VARIABLE.search(arg) for arg in args):
        return WRITE_DENIED
    if name in WRITERS and any(
        _writes_control(_resolve_path(arg, cwd)) for arg in args if not arg.startswith("-")
    ):
        return WRITE_DENIED
    if _writes_control(cwd) and name != "echo" and not _clearly_read_only(name, args):
        return WRITE_DENIED
    if not _clearly_read_only(name, args) and any(_mentions_control(arg, cwd) for arg in args):
        return WRITE_DENIED
    return None


def _check_shell(command: str, cwd: str = "") -> str | None:
    if reason := _check_substitutions(command, cwd):
        return reason
    found_command = False
    for words in _shell_commands(command):
        found_command = True
        if reason := _check_command(words, cwd):
            return reason
    if not found_command:
        raise ValueError(INVALID_INPUT)
    return None


def _require_text(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(INVALID_INPUT)
    return value


def _secret_pattern(pattern: str) -> bool:
    parts = _normalize_path(pattern).split("/")
    if not any(char in pattern for char in "*?["):
        return _reads_secret(pattern)
    candidates = (".env", ".env.local", ".env.production", "stack.json")
    return (parts[-1].startswith(".env.") and _reads_secret(parts[-1])) or any(
        fnmatch.fnmatchcase(name, parts[-1]) for name in candidates
    )


def _check_search(tool: str, data: dict[str, object]) -> str | None:
    pattern = _require_text(data, "pattern")
    base = _require_text(data, "path") if "path" in data else ""
    selector = pattern if tool == "Glob" else ""
    if tool == "Grep" and "glob" in data:
        selector = _require_text(data, "glob")
    paths = (base, selector, f"{base}/{selector}")
    return SENSITIVE_READ_DENIED if any(_secret_pattern(path) for path in paths) else None


def _check_mcp(value: object) -> str | None:
    if isinstance(value, str):
        if _mentions_control(value):
            return WRITE_DENIED
        if _reads_secret_reference(value):
            return SENSITIVE_READ_DENIED
    elif isinstance(value, list):
        for item in value:
            if reason := _check_mcp(item):
                return reason
    elif isinstance(value, dict):
        for item in value.values():
            if reason := _check_mcp(item):
                return reason
    return None


def _check_call(event: object) -> str | None:
    if not isinstance(event, dict) or not isinstance(data := event.get("tool_input"), dict):
        raise TypeError(INVALID_INPUT)
    tool = _require_text(event, "tool_name")
    cwd = _require_text(event, "cwd") if "cwd" in event else ""
    if tool.startswith("mcp__"):
        return _check_mcp(data)
    if tool in SHELL_TOOLS:
        command = _require_text(data, "command")
        return _check_shell(command, cwd) if cwd else _check_shell(command)
    if tool == "Read":
        return SENSITIVE_READ_DENIED if _reads_secret(_require_text(data, "file_path")) else None
    if tool in WRITE_TOOLS:
        key = "notebook_path" if tool == "NotebookEdit" and "notebook_path" in data else "file_path"
        path = _resolve_path(_require_text(data, key), cwd)
        return WRITE_DENIED if _writes_control(path) else None
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

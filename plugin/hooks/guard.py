"""Decide chamadas do Claude Code sem executá-las.

O módulo reúne a validação de entrada e a análise de shell para manter o hook
autônomo, executável com a biblioteca padrão e sem dependências do projeto. O
arquivo único preserva o ponto de entrada e a cópia independente do hook.

Por que um arquivo só, com mais de mil linhas: o hook roda como script autônomo,
lançado por `uv run --no-project`, sem o pacote `harness_dast` nem dependência
alguma. Um arquivo único mantém o lançador simples (um caminho, nenhum
`sys.path`) e se copia inteiro para o cache do plugin e para a cópia cega. Dividir
o arquivo exigiria importar irmãos do próprio diretório e abriria um modo de falha
no lançamento; por isso a divisão é recusada de propósito.
"""

import ast
import fnmatch
import io
import itertools
import json
import os
import posixpath
import re
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path, PureWindowsPath
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
PROTECTED_DENIED = "Acesso à pasta de plugins ou ao estado privado do hdast barrado."
PRODUCT_DENIED = (
    "Nesta pasta, o agente só escreve em products/, runs/ e cartas/. "
    "Use caminhos literais e uma operação que o hook consiga verificar. "
    "Mude a ferramenta no repositório dela."
)
PRODUCT_DIRECTORIES = frozenset(("products", "runs", "cartas"))
STACK_BUILD_DENIED = (
    "Construir as imagens da cerca barrado nesta pasta. Use as imagens já presentes: "
    "retire --build e HDAST_STACK_BUILD e peça a uma pessoa se faltar imagem."
)
# Na pasta de produtos, a CLI pode ser a do clone do coordenador (instalação editável) e aceitar o
# build local. O agente nunca o liga: nem pela opção, nem pela variável de ambiente.
STACK_BUILD_VARIABLE = re.compile(r"HDAST_STACK_BUILD", re.IGNORECASE)
STACK_BUILD_FLAG = re.compile(r"(?<![\w-])--build(?![\w-])")
HDAST_WORD = re.compile(r"\b(?:hdast|harness_dast)\b", re.IGNORECASE)


def _is_clone(project: Path) -> bool:
    package = project / "src" / "harness_dast"
    manifest_path = project / "pyproject.toml"
    if not package.is_dir() or not package.resolve().is_relative_to(project):
        return False
    if manifest_path.is_symlink():
        return False
    try:
        with manifest_path.open("rb") as manifest:
            metadata = tomllib.load(manifest).get("project")
            return isinstance(metadata, dict) and metadata.get("name") == "harness-dast"
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return False


def _state_root() -> Path:
    if override := os.environ.get("HDAST_STATE_DIR"):
        return Path(override)
    if sys.platform == "win32" and (local := os.environ.get("LOCALAPPDATA")):
        return Path(local) / "hdast"
    base = os.environ.get("XDG_STATE_HOME")
    return (Path(base) if base else Path.home() / ".local" / "state") / "hdast"


def _protected_roots() -> tuple[Path, ...]:
    roots = [Path.home() / ".claude" / "plugins", _state_root()]
    if config := os.environ.get("CLAUDE_CONFIG_DIR"):
        roots.append(Path(config) / "plugins")
    for key in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA"):
        if value := os.environ.get(key):
            roots.append(Path(value))
    return tuple(roots)


def _plugin_readable(path: Path) -> bool:
    """Diz se o caminho está na raiz do plugin ativo e fora do estado privado do hdast.

    Só vale para leitura: o plugin é código e instrução do próprio agente, sem segredo. A raiz
    vem de `CLAUDE_PLUGIN_ROOT`; sem ela nada é liberado. O estado do hdast (aprovações,
    confirmações, cofre) e a pasta de dados do plugin seguem barrados mesmo se ficarem sob a raiz.
    """
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return False
    base = Path(root)
    private = [_state_root()]
    if data := os.environ.get("CLAUDE_PLUGIN_DATA"):
        private.append(Path(data))
    locations = (Path(os.path.abspath(path)), path.resolve())
    bases = (Path(os.path.abspath(base)), base.resolve())
    if not all(
        location.is_relative_to(boundary)
        for location, boundary in zip(locations, bases, strict=True)
    ):
        return False
    return not any(
        location.is_relative_to(boundary)
        for location in locations
        for secret in private
        for boundary in (Path(os.path.abspath(secret)), secret.resolve())
    )


def _native_path(value: str, cwd: Path) -> Path:
    if sys.platform == "win32" and (msys := re.fullmatch(r"/([a-zA-Z])(/.*)", value)):
        value = f"{msys[1]}:{msys[2]}"
    path = Path(value)
    return cwd / (path.expanduser() if path.parts[:1] == ("~",) else path)


def _protected_path(value: str, cwd: Path, *, tree: bool = False) -> bool:
    path = _native_path(value, cwd)
    locations = (Path(os.path.abspath(path)), path.resolve())
    for root in _protected_roots():
        for boundary in (Path(os.path.abspath(root)), root.resolve()):
            if any(location.is_relative_to(boundary) for location in locations):
                return True
            if tree and any(boundary.is_relative_to(location) for location in locations):
                return True
    return False


def _product_component(path: Path, project: Path) -> bool:
    if not path.is_relative_to(project):
        return False
    parts = path.relative_to(project).parts
    # O Windows compara Path sem distinguir caixa. A lista exige a grafia da pasta.
    return bool(parts and parts[0] in PRODUCT_DIRECTORIES)


def _product_destination(value: str, cwd: Path, project: Path) -> bool:
    if not value or re.search(r"[\x00-\x1f*?\[\]${}%~]", value):
        return False
    raw = Path(value)
    if raw.anchor and not raw.is_absolute():
        return False
    parts = raw.parts[1:] if raw.anchor else raw.parts
    if any(":" in part for part in parts):
        return False
    if sys.platform == "win32" and any(
        PureWindowsPath(part).is_reserved() or (part != ".." and part.endswith((".", " ")))
        for part in parts
    ):
        return False
    path = cwd / raw
    resolved = path.resolve()
    return (
        _product_component(Path(os.path.abspath(path)), project)
        and _product_component(resolved, project)
        and not _protected_path(value, cwd, tree=True)
        and not _writes_control(str(resolved))
        and (not resolved.is_file() or resolved.stat().st_nlink == 1)
    )


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


_PRODUCT_LEXER_PATTERN = (
    r"(?P<redirect>>>?|<)|(?P<separator>&&|\|\||[;|\n])"
    r"""|(?P<word>{quoted}|[^\s'";&|()<>]+)"""
    r"|(?P<space>[^\S\n]+)|(?P<invalid>.)"
)
_PRODUCT_BASH_TOKEN = re.compile(_PRODUCT_LEXER_PATTERN.format(quoted=QUOTED_PART.pattern))
_PS_QUOTED = r"'[^']*'|\"[^\"]*\""
_PRODUCT_POWERSHELL_TOKEN = re.compile(_PRODUCT_LEXER_PATTERN.format(quoted=_PS_QUOTED))
_POSITIONAL_WRITERS = {
    "tee": frozenset(("-a", "--append")),
    "cp": frozenset(("-f", "--force")),
    "install": frozenset(),
    "mv": frozenset(("-f", "--force")),
    "rm": frozenset(("-f", "-r", "-rf", "-fr", "--force", "--recursive")),
    "rmdir": frozenset(),
    "mkdir": frozenset(("-p", "--parents")),
    "touch": frozenset(),
}
_PS_WRITERS = frozenset(
    (
        "set-content",
        "out-file",
        "new-item",
        "remove-item",
        "copy-item",
        "move-item",
        "add-content",
    )
)


def _product_shell_segments(
    command: str, tool: str
) -> Iterator[tuple[list[tuple[str, str]], bool]]:
    # Cada parte sai com um sinal: veio logo depois de `|`? Só então um filtro de leitura vale.
    tokens: list[tuple[str, str]] = []
    piped = False
    end = 0
    previous = "space"
    pattern = _PRODUCT_BASH_TOKEN if tool == "Bash" else _PRODUCT_POWERSHELL_TOKEN
    for token in pattern.finditer(command):
        kind = token.lastgroup or "invalid"
        value = token[0]
        if token.start() != end or kind == "invalid":
            raise ValueError(PRODUCT_DENIED)
        end = token.end()
        if kind == "separator":
            if not tokens:
                raise ValueError(PRODUCT_DENIED)
            yield tokens, piped
            tokens = []
            piped = value == "|"
        elif kind in {"word", "redirect"}:
            if previous == "word" and (kind == "word" or tokens[-1][1].isdigit()):
                raise ValueError(PRODUCT_DENIED)
            tokens.append((kind, _literal_word(value, tool) if kind == "word" else value))
        previous = kind
    if end != len(command) or (not tokens and previous != "separator"):
        raise ValueError(PRODUCT_DENIED)
    if tokens:
        yield tokens, piped


def _literal_word(value: str, tool: str) -> str:
    if value[:1] in {"'", '"'} and value[1:2] == "-":
        raise ValueError(PRODUCT_DENIED)
    if value.startswith("'"):
        return value[1:-1]
    if value.startswith('"'):
        if re.search(r"[\x00-\x1f$`!]", value) or (tool == "Bash" and "\\" in value):
            raise ValueError(PRODUCT_DENIED)
        return value[1:-1]
    if re.search(r"[\x00-\x1f$`^%*?\[\]{}~#,!@]", value) or (tool == "Bash" and "\\" in value):
        raise ValueError(PRODUCT_DENIED)
    return value


def _literal_operands(args: list[str], flags: frozenset[str]) -> list[str]:
    operands: list[str] = []
    for index, arg in enumerate(args):
        if arg == "--":
            return operands + args[index + 1 :]
        if arg in flags:
            continue
        if arg.startswith("-"):
            raise ValueError(PRODUCT_DENIED)
        operands.append(arg)
    return operands


def _copy_destinations(name: str, source: str, target: str, cwd: Path) -> list[str]:
    if not _safe_read_path(source, cwd, tree=True):
        raise ValueError(PRODUCT_DENIED)
    origin = _native_path(source, cwd)
    destination = _native_path(target, cwd)
    if origin.is_dir() or not origin.name:
        raise ValueError(PRODUCT_DENIED)
    paths = [target]
    if destination.is_dir():
        paths.append(str(destination / origin.name))
    return [source, *paths] if name in {"mv", "move-item"} else paths


def _sed_destinations(args: list[str]) -> list[str]:
    if len(args) < 3 or not re.fullmatch(r"-i(?:\.[a-zA-Z0-9_-]+)?", args[0]):
        raise ValueError(PRODUCT_DENIED)
    if not re.fullmatch(r"s/[^/\\\n]*/[^/\\\n]*/g?", args[1]):
        raise ValueError(PRODUCT_DENIED)
    paths = _literal_operands(args[2:], frozenset())
    suffix = args[0][2:]
    return paths + [path + suffix for path in paths if suffix]


def _inside_product_folder(value: str, cwd: Path, project: Path) -> bool:
    """Diz se o alvo fica dentro de products/, runs/ ou cartas/, nunca nelas mesmas."""
    path = _native_path(value, cwd)
    for location in (Path(os.path.abspath(path)), path.resolve()):
        if not location.is_relative_to(project):
            return False
        parts = location.relative_to(project).parts
        if len(parts) < 2 or parts[0] not in PRODUCT_DIRECTORIES:
            return False
        # O script de limpeza é de autoria humana: o agente também não o apaga.
        if "cleanup" in parts[2:]:
            return False
    return True


def _check_removal(paths: list[str], cwd: Path, project: Path) -> list[str]:
    # Apagar exige alvo explícito dentro das pastas permitidas; as três pastas e a raiz ficam.
    if not paths or not all(_inside_product_folder(path, cwd, project) for path in paths):
        raise ValueError(PRODUCT_DENIED)
    return paths


def _positional_destinations(name: str, args: list[str], cwd: Path, project: Path) -> list[str]:
    operands = _literal_operands(args, _POSITIONAL_WRITERS[name])
    if name in {"rm", "rmdir"}:
        return _check_removal(operands, cwd, project)
    if name in {"cp", "mv", "install"}:
        if len(operands) != 2:
            raise ValueError(PRODUCT_DENIED)
        return _copy_destinations(name, operands[0], operands[1], cwd)
    return operands


def _ps_operands(args: list[str]) -> tuple[dict[str, str], list[str]]:
    named: dict[str, str] = {}
    positional = []
    remaining = iter(args)
    for arg in remaining:
        flag = arg.lower()
        if flag in {"-force", "-append"}:
            continue
        if not flag.startswith("-"):
            positional.append(arg)
            continue
        options = {"-path", "-literalpath", "-filepath", "-destination", "-value", "-itemtype"}
        if flag not in options:
            raise ValueError(PRODUCT_DENIED)
        value = next(remaining, "")
        if flag in named or not value or value.startswith("-"):
            raise ValueError(PRODUCT_DENIED)
        named[flag] = value
    return named, positional


def _ps_destinations(name: str, args: list[str], cwd: Path) -> list[str]:
    named, positional = _ps_operands(args)
    selectors = [named[key] for key in ("-path", "-literalpath", "-filepath") if key in named]
    path = selectors[0] if selectors else (positional.pop(0) if positional else "")
    if len(selectors) > 1 or not path:
        raise ValueError(PRODUCT_DENIED)
    if name in {"copy-item", "move-item"}:
        target = named.get("-destination", "") or (positional.pop(0) if positional else "")
        if positional or not target:
            raise ValueError(PRODUCT_DENIED)
        return _copy_destinations(name, path, target, cwd)
    if name == "new-item" and named.get("-itemtype", "file").lower() not in {"file", "directory"}:
        raise ValueError(PRODUCT_DENIED)
    if len(positional) > int(name in {"set-content", "add-content"} and "-value" not in named):
        raise ValueError(PRODUCT_DENIED)
    return [path]


def _ast_path(node: ast.expr, cwd: Path) -> bool:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return False
    value = node.value
    return not _reads_secret_reference(value) and _safe_read_path(value, cwd)


def _python_read(node: ast.Call, cwd: Path) -> bool:
    if node.keywords or not isinstance(node.func, ast.Attribute):
        return False
    source = node.func.value
    if node.args or not isinstance(source, ast.Call) or not isinstance(source.func, ast.Name):
        return False
    if source.keywords or not source.args or not _ast_path(source.args[0], cwd):
        return False
    if source.func.id == "Path":
        return node.func.attr in {"read_text", "read_bytes"} and len(source.args) == 1
    if source.func.id != "open" or node.func.attr != "read":
        return False
    return len(source.args) == 1 or (
        len(source.args) == 2
        and isinstance(source.args[1], ast.Constant)
        and source.args[1].value in ("r", "rt", "rb")
    )


def _python_expression(node: ast.expr, cwd: Path) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name) and node.func.id == "print":
        return not node.keywords and all(_python_expression(arg, cwd) for arg in node.args)
    return _python_read(node, cwd)


def _python_read_only(code: str, cwd: Path, *, isolated: bool = False) -> bool:
    try:
        statements = ast.parse(code).body
    except SyntaxError:
        return False
    for statement in statements:
        if isinstance(statement, ast.Expr) and _python_expression(statement.value, cwd):
            continue
        if (
            isolated
            and isinstance(statement, ast.ImportFrom)
            and statement.level == 0
            and statement.module == "pathlib"
            and [(alias.name, alias.asname) for alias in statement.names] == [("Path", None)]
        ):
            continue
        return False
    return bool(statements)


def _node_read_only(code: str) -> bool:
    match = re.fullmatch(r"\s*console\.log\((.*)\);?\s*", code)
    if not match:
        return False
    try:
        json.loads(match[1])
    except ValueError:
        return False
    return True


def _safe_reader(name: str, args: list[str], cwd: Path) -> bool:
    if name in {"pwd", "get-location"}:
        return not args
    if name in {"echo", "write-output"}:
        return not any(arg.startswith("-") for arg in args)
    if name in {"cat", "type", "get-content", "head", "tail"}:
        paths = _literal_operands(args, frozenset(("-path", "-literalpath")))
        return all(_safe_read_path(path, cwd) for path in paths)
    if name in {"ls", "dir", "get-childitem"}:
        flags = frozenset(("-a", "-l", "-al", "-la", "-path", "-literalpath"))
        paths = _literal_operands(args, flags)
        return all(_safe_read_path(path, cwd, tree=True) for path in paths or ["."])
    return False


def _safe_read_path(path: str, cwd: Path, *, tree: bool = False) -> bool:
    raw = Path(path)
    return not (
        re.search(r"[\x00-\x1f*?\[\]${}%~]", path)
        or (raw.anchor and not raw.is_absolute())
        or bool(re.match(r"(?i)env:", path))
        or _reads_secret(str(_native_path(path, cwd).resolve()))
        or _protected_path(path, cwd, tree=tree)
    )


def _git_destinations(args: list[str], cwd: Path) -> list[str]:
    # Esta forma compara arquivos e grava uma saída explícita, sem alterar metadados do Git.
    if len(args) != 8 or args[:4] != ["diff", "--no-index", "--no-ext-diff", "--no-textconv"]:
        raise ValueError(PRODUCT_DENIED)
    option, separator, left, right = args[4:]
    if not option.startswith("--output=") or separator != "--":
        raise ValueError(PRODUCT_DENIED)
    if not all(
        _safe_read_path(path, cwd, tree=True) and not _native_path(path, cwd).is_dir()
        for path in (left, right)
    ):
        raise ValueError(PRODUCT_DENIED)
    return [option.removeprefix("--output=")]


# Diagnóstico só de leitura: formas exatas, sem instalar, gravar nem ler segredo.
_DIAGNOSTIC_FORMS: dict[str, tuple[tuple[str, ...], ...]] = {
    "uv": (("--version",), ("tool", "list"), ("tool", "dir")),
    "docker": (("--version",), ("version",), ("info",), ("ps",), ("ps", "-a"), ("ps", "--all")),
    "wsl": (
        ("--status",),
        ("--list",),
        ("-l",),
        ("--list", "--verbose"),
        ("--list", "-v"),
        ("-l", "--verbose"),
        ("-l", "-v"),
    ),
    "winget": (("--version",),),
    "whoami": ((),),
    "nproc": ((),),
    "systeminfo": ((),),
    "get-psdrive": ((),),
}
_DIAGNOSTIC_FLAGS = {
    "uname": re.compile(r"-[asmrnopvi]+"),
    "df": re.compile(r"-[hHkTPal]+"),
    "free": re.compile(r"-[hmgbkw]+"),
}
_FILTER_NUMBER = re.compile(r"\+?\d+")


def _diagnostic_command(name: str, args: list[str]) -> bool:
    name = name.removesuffix(".exe")
    if name in _DIAGNOSTIC_FLAGS:
        return all(_DIAGNOSTIC_FLAGS[name].fullmatch(arg) for arg in args)
    return tuple(arg.lower() for arg in args) in _DIAGNOSTIC_FORMS.get(name, ())


def _count_filter(args: list[str]) -> bool:
    # head e tail só da entrada padrão: `-n N`, `-c N`, `-N`, `-nN`, `-cN`.
    remaining = iter(args)
    for arg in remaining:
        if arg in {"-n", "-c"}:
            if not _FILTER_NUMBER.fullmatch(next(remaining, "")):
                return False
        elif not re.fullmatch(r"-(?:[nc]\+?)?\d+", arg):
            return False
    return True


def _cut_filter(args: list[str]) -> bool:
    remaining = iter(args)
    for arg in remaining:
        if arg in {"-d", "-f", "-c", "-b"}:
            if not next(remaining, ""):
                return False
        elif not re.fullmatch(r"-[dfcb].+|-s|--complement", arg):
            return False
    return True


def _grep_filter(args: list[str]) -> bool:
    patterns = [arg for arg in args if not arg.startswith("-")]
    flags = [arg for arg in args if arg.startswith("-")]
    return len(patterns) == 1 and all(re.fullmatch(r"-[ivcnwxFEHhqsoa]+", arg) for arg in flags)


def _pipe_filter(name: str, args: list[str]) -> bool:
    """Filtros de leitura que só leem a entrada padrão; valem depois de `|`."""
    if name in {"head", "tail"}:
        return _count_filter(args)
    if name == "wc":
        return all(re.fullmatch(r"-[lwcmL]+", arg) for arg in args)
    if name == "sort":
        return all(re.fullmatch(r"-[rnufhV]+", arg) for arg in args)
    if name == "cut":
        return _cut_filter(args)
    return name == "grep" and _grep_filter(args)


def _hdast_command(name: str, args: list[str]) -> bool:
    if name == "uv" and args[:2] == ["run", "hdast"]:
        args = args[2:]
    elif name not in {"hdast", "hdast.exe"}:
        return False
    remaining = [arg for arg in args if arg != "--json"]
    return (
        not remaining
        or remaining in [["--help"], ["--version"]]
        or not remaining[0].startswith("-")
    )


def _reads_only(name: str, args: list[str], cwd: Path, tool: str, *, piped: bool) -> bool:
    if piped and tool == "Bash" and _pipe_filter(name, args):
        return True
    return _diagnostic_command(name, args) or _safe_reader(name, args, cwd)


def _ps_writer(name: str, args: list[str], cwd: Path, project: Path) -> list[str]:
    paths = _ps_destinations(name, args, cwd)
    return _check_removal(paths, cwd, project) if name == "remove-item" else paths


def _product_command(
    words: list[str], cwd: Path, project: Path, tool: str, *, nested: bool, piped: bool = False
) -> list[str]:
    name, *args = words
    name = name.lower()
    if tool == "Bash" and any("\\" in arg for arg in args) and not PYTHON.fullmatch(name):
        raise ValueError(PRODUCT_DENIED)
    nested_readers = {"echo", "write-output", "get-location", "get-content", "get-childitem"}
    if nested and name not in nested_readers:
        raise ValueError(PRODUCT_DENIED)
    if _reads_only(name, args, cwd, tool, piped=piped) or _hdast_command(name, args):
        return []
    if name in _POSITIONAL_WRITERS and tool == "Bash":
        return _positional_destinations(name, args, cwd, project)
    if name in _PS_WRITERS and tool == "PowerShell":
        return _ps_writer(name, args, cwd, project)
    if name == "sed" and tool == "Bash":
        return _sed_destinations(args)
    if name == "git":
        return _git_destinations(args, cwd)
    if _safe_inline(name, args, cwd, project):
        return []
    raise ValueError(PRODUCT_DENIED)


def _safe_inline(name: str, args: list[str], cwd: Path, project: Path) -> bool:
    if PYTHON.fullmatch(name) and len(args) == 5 and args[:4] == ["-I", "-B", "-S", "-c"]:
        return _python_read_only(args[-1], cwd, isolated=True)
    if len(args) != 2:
        return False
    option, code = args
    if PYTHON.fullmatch(name) and option == "-c":
        return _python_read_only(code, cwd)
    if name == "node" and option in {"-e", "--eval"}:
        return _node_read_only(code)
    if name in POWERSHELLS and option.lower() in {"-c", "-command"}:
        _check_product_shell(code, cwd, project, "PowerShell", nested=True)
        return True
    return False


def _split_product_command(
    tokens: list[tuple[str, str]], cwd: Path, tool: str
) -> tuple[list[str], list[str]]:
    words = []
    writes = []
    remaining = iter(tokens)
    for kind, value in remaining:
        if kind == "word":
            words.append(value)
            continue
        target_kind, target = next(remaining, ("", ""))
        if target_kind != "word" or (value == "<" and not _safe_read_path(target, cwd)):
            raise ValueError(PRODUCT_DENIED)
        if tool == "Bash" and "\\" in target:
            raise ValueError(PRODUCT_DENIED)
        if value != "<":
            writes.append(target)
    return words, writes


def _check_product_shell(
    command: str, cwd: Path, project: Path, tool: str, *, nested: bool = False
) -> None:
    command = command.strip()
    if re.search(r"[\x00-\x08\x0b-\x1f]", command):
        raise ValueError(PRODUCT_DENIED)
    heredoc = re.fullmatch(r"python(?:3)? -\s+<<\s*'([A-Za-z_]\w*)'\n(.*?)\n\1", command, re.S)
    if heredoc and tool == "Bash" and not nested:
        delimiter, code = heredoc.groups()
        if delimiter not in code.splitlines() and _python_read_only(code, cwd):
            return
        raise ValueError(PRODUCT_DENIED)
    for tokens, piped in _product_shell_segments(command, tool):
        words, destinations = _split_product_command(tokens, cwd, tool)
        if not words or (nested and destinations):
            raise ValueError(PRODUCT_DENIED)
        destinations.extend(_product_command(words, cwd, project, tool, nested=nested, piped=piped))
        if not all(_product_destination(path, cwd, project) for path in destinations):
            raise ValueError(PRODUCT_DENIED)


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


def _protected_reference(value: str, cwd: Path) -> bool:
    settings = r"(?:CLAUDE_PLUGIN_(?:DATA|ROOT)|HDAST_STATE_DIR)"
    if re.search(rf"(?i)(?:\$(?:\{{|env:)?{settings}\b|%{settings}%)", value):
        return True
    if re.search(r"(?i)(?:\$\{?HOME\}?|\$env:USERPROFILE)[\\/]\.claude[\\/]plugins\b", value):
        return True
    fragments = re.split(r"[\s'\"`(),;=]+", value)
    return any(_protected_fragment(part, cwd) for part in (value, *fragments))


def _protected_fragment(part: str, cwd: Path) -> bool:
    if not part or re.search(r"[\x00-\x1f<>|\"]", part):
        return False
    prefix = re.split(r"[*?\[]", part, maxsplit=1)[0]
    if prefix == part:
        return _protected_path(prefix, cwd)
    directory = posixpath.dirname(prefix.replace("\\", "/"))
    return bool(prefix and _protected_path(prefix, cwd)) or _protected_path(
        directory or ".", cwd, tree=True
    )


def _protected_mcp(value: object, cwd: Path) -> bool:
    if isinstance(value, str):
        return _protected_reference(value, cwd)
    if isinstance(value, dict):
        return any(_protected_mcp(item, cwd) for item in value.values())
    if isinstance(value, list):
        return any(_protected_mcp(item, cwd) for item in value)
    return False


def _protected_search(tool: str, data: dict[str, object], cwd: Path) -> bool:
    return _protected_path(str(_search_location(tool, data, cwd)), cwd, tree=True)


def _search_location(tool: str, data: dict[str, object], cwd: Path) -> Path:
    base = _require_text(data, "path") if "path" in data else "."
    selector = _require_text(data, "pattern") if tool == "Glob" else ""
    prefix = re.split(r"[*?\[]", selector, maxsplit=1)[0]
    if prefix != selector and not prefix.endswith(("/", "\\")):
        prefix = posixpath.dirname(prefix.replace("\\", "/"))
    return _native_path(prefix or ".", _native_path(base, cwd))


def _protected_shell(command: str, cwd: Path) -> bool:
    if _protected_path(".", cwd) or _protected_reference(command, cwd):
        return True
    return any(
        _protected_reference(value, cwd)
        for segment in _shell_commands(command)
        for kind, value in segment
        if kind == "word"
    )


def _requests_stack_build(command: str) -> bool:
    if STACK_BUILD_VARIABLE.search(command):
        return True
    return bool(STACK_BUILD_FLAG.search(command) and HDAST_WORD.search(command))


def _check_shell_call(
    tool: str, data: dict[str, object], project: Path, context: str
) -> str | None:
    command = _require_text(data, "command")
    cwd = _native_path(context or ".", project)
    baseline = _check_shell(command, context) if context else _check_shell(command)
    if baseline:
        return baseline
    if _protected_shell(command, cwd):
        return PROTECTED_DENIED
    if not _is_clone(project):
        if _requests_stack_build(command):
            return STACK_BUILD_DENIED
        try:
            _check_product_shell(command, cwd, project, tool)
        except ValueError:
            return PRODUCT_DENIED
    return None


def _check_file_call(tool: str, data: dict[str, object], project: Path, context: str) -> str | None:
    cwd = _native_path(context or ".", project)
    key = "notebook_path" if tool == "NotebookEdit" and "notebook_path" in data else "file_path"
    path = _require_text(data, key)
    if tool == "Read" and (
        _reads_secret(path) or _reads_secret(str(_native_path(path, cwd).resolve()))
    ):
        return SENSITIVE_READ_DENIED
    if tool != "Read" and _writes_control(_resolve_path(path, context)):
        return WRITE_DENIED
    if _protected_path(path, cwd) and not (
        tool == "Read" and not _is_clone(project) and _plugin_readable(_native_path(path, cwd))
    ):
        return PROTECTED_DENIED
    if tool != "Read" and not _is_clone(project) and not _product_destination(path, cwd, project):
        return PRODUCT_DENIED
    return None


def _check_call(event: object) -> str | None:
    if not isinstance(event, dict) or not isinstance(data := event.get("tool_input"), dict):
        raise TypeError(INVALID_INPUT)
    tool = _require_text(event, "tool_name")
    cwd = _require_text(event, "cwd") if "cwd" in event else ""
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()
    if tool.startswith("mcp__"):
        if reason := _check_mcp(data):
            return reason
        if _protected_mcp(data, _native_path(cwd or ".", project)):
            return PROTECTED_DENIED
        return None if _is_clone(project) else PRODUCT_DENIED
    if tool in SHELL_TOOLS:
        return _check_shell_call(tool, data, project, cwd)
    if tool == "Read" or tool in WRITE_TOOLS:
        return _check_file_call(tool, data, project, cwd)
    if tool in SEARCH_TOOLS:
        if reason := _check_search(tool, data):
            return reason
        where = _native_path(cwd or ".", project)
        if _protected_search(tool, data, where) and not (
            not _is_clone(project) and _plugin_readable(_search_location(tool, data, where))
        ):
            return PROTECTED_DENIED
        return None
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

"""Seleciona testes do laboratório e registra a rodada sob uma trava exclusiva."""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from getpass import getuser
from pathlib import Path
from typing import Annotated, BinaryIO, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from harness_dast.domain.errors import ConfigError, ExitCode, HarnessError

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = "tests/integration"
MAP = ROOT / INTEGRATION / "lab_areas.toml"
ARTIFACTS = Path("C:/harness-dast-artefatos")
LEVELS = ("changed", "fast", "prova", "regressao", "carga", "tudo")
CARGA_FILES = ("test_guard_benchmark.py", "test_scan_performance_matrix.py")
# Cada dimensão parte um arquivo em pedaços; o teste que não casa com nenhum valor vai ao resto.
SPLIT_DIMENSIONS = (
    ("vulnerable", "secure"),
    ("clinica-piloto", "vampi"),
    ("pilot", "vampi"),
)
MIN_SPLIT = 8  # arquivo ou balde com até 8 testes não vale o custo de outra pilha.

type Level = Literal["changed", "fast", "prova", "regressao", "carga", "tudo"]
type PlannedLevel = Literal["fast", "prova", "regressao", "carga"]
# Níveis que o workflow do GitHub planeja quando o pedido é "tudo".
PLANNED_LEVELS: tuple[PlannedLevel, ...] = ("fast", "prova", "regressao", "carga")
type NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
type TestFile = Annotated[str, StringConstraints(pattern=r"^test_[a-zA-Z0-9_]+\.py$")]


class LabArea(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonEmpty
    paths: Annotated[tuple[NonEmpty, ...], Field(min_length=1)]
    fast: tuple[TestFile, ...]
    prova: tuple[TestFile, ...]

    def matches(self, path: str) -> bool:
        name = path.removeprefix(f"{INTEGRATION}/")
        return (name != path and name in (*self.fast, *self.prova)) or any(
            fnmatchcase(path, pattern) for pattern in self.paths
        )


class AreaMap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    shared: tuple[NonEmpty, ...]
    all_areas: tuple[NonEmpty, ...] = ()
    areas: Annotated[dict[NonEmpty, LabArea], Field(min_length=1)]

    def files(self, level: Literal["fast", "prova"]) -> tuple[str, ...]:
        files = {name for area in self.areas.values() for name in getattr(area, level)}
        return tuple(sorted(files))


class RoundOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    level: Level
    base: NonEmpty
    dry_run: bool
    suffix: str
    output: Path | None
    lock: Path
    owner: NonEmpty
    file: TestFile | None
    keyword: NonEmpty | None
    pieces_json: bool


class LabBusy(HarnessError):
    code = "LAB_BUSY"
    exit_code = ExitCode.BUSY


@dataclass(frozen=True)
class Selection:
    marker: str
    paths: tuple[str, ...]


class Piece(BaseModel):
    """Um pedaço da rodada: um arquivo, num nível, com a expressão `-k` do modo, se houver."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    level: PlannedLevel
    file: TestFile
    keyword: NonEmpty | None
    name: NonEmpty


def load_map(path: Path) -> AreaMap:
    """Lê e valida o mapa antes de usá-lo na seleção."""
    try:
        with path.open("rb") as stream:
            areas = AreaMap.model_validate(tomllib.load(stream))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Não foi possível ler o mapa {path}. Confira o TOML. {exc}") from exc
    if any(not (area.fast or area.prova) for area in areas.areas.values()):
        raise ConfigError(f"Área sem testes no mapa {path}. Liste ao menos um arquivo por área.")
    return areas


def render_area_table(areas: AreaMap) -> str:
    """Monta a tabela da escada de testes a partir do mapa."""
    rows = [
        "| Mudei... | Exemplo de caminho | Núcleo (`lab_fast`) | Provas (`lab_prova`) |",
        "| --- | --- | ---: | ---: |",
    ]
    for area in areas.areas.values():
        rows.append(f"| {area.name} | `{area.paths[0]}` | {len(area.fast)} | {len(area.prova)} |")
    return "\n".join(rows)


def _is_documentation(path: str) -> bool:
    return path.startswith("docs/") or path in {"README.md", "CHANGELOG.md", "CONTRIBUTING.md"}


def _select_files(marker: str, files: Iterable[str]) -> Selection:
    paths = tuple(f"{INTEGRATION}/{name}" for name in sorted(set(files)))
    if not paths:
        raise ConfigError(f"O mapa não lista arquivos para {marker}. Confira as áreas.")
    return Selection(marker, paths)


def select_changed(areas: AreaMap, paths: Iterable[str]) -> Selection | None:
    """Soma as áreas atingidas e inclui o núcleo inteiro se um caminho ficar sem cobertura."""
    relevant = {path for path in paths if not _is_documentation(path)}
    if not relevant:
        return None
    all_proofs = bool(relevant.intersection(areas.all_areas))
    affected: list[LabArea] = []
    covered: set[str] = set()
    for area in areas.areas.values():
        matches = relevant if all_proofs else {path for path in relevant if area.matches(path)}
        if matches:
            affected.append(area)
            covered.update(matches)
    all_fast = (
        all_proofs
        or relevant != covered
        or any(fnmatchcase(path, pattern) for path in relevant for pattern in areas.shared)
    )
    fast = areas.files("fast") if all_fast else tuple(f for area in affected for f in area.fast)
    prova = tuple(name for area in affected for name in area.prova)
    marker = "lab_fast or lab_prova" if fast and prova else "lab_prova" if prova else "lab_fast"
    return _select_files(marker, (*fast, *prova))


def select_level(level: Level, areas: AreaMap, changes: Iterable[str] = ()) -> Selection | None:
    if level == "changed":
        return select_changed(areas, changes)
    if level in ("fast", "prova"):
        return _select_files(f"lab_{level}", areas.files(level))
    if level == "regressao":
        return Selection("regressao_dirigida", (INTEGRATION,))
    if level == "carga":
        return _select_files("integration or e2e", CARGA_FILES)
    return Selection("integration or e2e", ("tests",))


def _git(repo: Path, executable: str, *args: str) -> str:
    try:
        return subprocess.run(  # noqa: S603 - Git local, sem shell.
            (executable, *args), cwd=repo, capture_output=True, check=True, encoding="utf-8"
        ).stdout
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip()
        raise ConfigError(
            f"Git não pôde listar as mudanças. Confira --base e o checkout. {detail}"
        ) from exc


def changed_paths(repo: Path, base: str) -> set[str]:
    """Inclui as mudanças da branch e os caminhos preparados, locais e novos."""
    git = shutil.which("git")
    if git is None:
        raise ConfigError("Git indisponível. Inclua o executável no PATH para usar changed.")
    commit = _git(
        repo, git, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"
    ).strip()
    diff = ("diff", "--no-renames", "--name-only", "-z")
    changes = (
        _git(repo, git, *diff, f"{commit}...HEAD", "--"),
        _git(repo, git, *diff, "--cached", "--"),
        _git(repo, git, *diff, "--"),
        _git(repo, git, "ls-files", "--others", "--exclude-standard", "-z"),
    )
    return {path for output in changes for path in output.split("\0") if path}


def restrict_to_file(selection: Selection, filename: str) -> Selection:
    """Seleciona um arquivo da rodada, preservando o filtro de marcadores."""
    path = Path(INTEGRATION) / filename
    allowed = any(path == Path(item) or Path(item) in path.parents for item in selection.paths)
    if not allowed or not (ROOT / path).is_file():
        raise ConfigError(f"O arquivo {filename} não pertence à seleção. Confira --nivel.")
    return Selection(selection.marker, (path.as_posix(),))


def collect_node_ids(selection: Selection) -> tuple[str, ...]:
    """Coleta os identificadores dos testes da seleção, sem executá-los."""
    command = (
        sys.executable,
        "-m",
        "pytest",
        *selection.paths,
        "-m",
        selection.marker,
        "--collect-only",
        "-q",
    )
    result = subprocess.run(  # noqa: S603 - pytest local, sem shell e só em coleta.
        command, cwd=ROOT, capture_output=True, check=False, encoding="utf-8", errors="replace"
    )
    if result.returncode not in (0, 5):
        raise ConfigError(
            f"A coleta do pytest falhou com código {result.returncode}. "
            f"Rode a coleta à mão e corrija o erro. {result.stdout[-500:]}"
        )
    return tuple(line for line in result.stdout.splitlines() if "::" in line)


@dataclass(frozen=True)
class _Bucket:
    ids: tuple[str, ...]
    labels: tuple[str, ...]
    exprs: tuple[str, ...]


def _needles(value: str) -> tuple[str, ...]:
    """Trechos que só aparecem no identificador de parâmetro, nunca em nome de função."""
    return (f"[{value}", f"-{value}-", f"-{value}]")


def _matches(node_id: str, value: str) -> bool:
    bracket = node_id[node_id.find("[") :].lower() if "[" in node_id else ""
    return any(needle in bracket for needle in _needles(value))


def _expression(values: Iterable[str]) -> str:
    return " or ".join(needle for value in values for needle in _needles(value))


def _partition(bucket: _Bucket, values: tuple[str, ...]) -> list[_Bucket] | None:
    """Parte o balde por um conjunto de valores, ou devolve `None` se a partição for ambígua."""
    counts = [sum(_matches(i, v) for v in values) for i in bucket.ids]
    present = tuple(v for v in values if any(_matches(i, v) for i in bucket.ids))
    if max(counts, default=0) > 1 or len(present) < 2:
        return None
    parts = [
        _Bucket(
            tuple(i for i in bucket.ids if _matches(i, v)),
            (*bucket.labels, v),
            (*bucket.exprs, _expression((v,))),
        )
        for v in present
    ]
    rest = tuple(i for i, count in zip(bucket.ids, counts, strict=True) if count == 0)
    if rest:
        expr = f"not ({_expression(present)})"
        parts.append(_Bucket(rest, (*bucket.labels, "resto"), (*bucket.exprs, expr)))
    return parts


def _split_file(node_ids: Sequence[str]) -> list[_Bucket]:
    """Parte um arquivo por modo e produto, enquanto o balde for maior que `MIN_SPLIT`."""
    buckets = [_Bucket(tuple(node_ids), (), ())]
    for values in SPLIT_DIMENSIONS:
        refined: list[_Bucket] = []
        for bucket in buckets:
            parts = _partition(bucket, values) if len(bucket.ids) > MIN_SPLIT else None
            refined.extend(parts or [bucket])
        buckets = refined
    return buckets


def _level_pieces(level: str, node_ids: Iterable[str]) -> Iterator[tuple[str, str, str | None]]:
    by_file: dict[str, list[str]] = {}
    for node_id in node_ids:
        by_file.setdefault(Path(node_id.split("::")[0]).name, []).append(node_id)
    for file, ids in sorted(by_file.items()):
        stem = file.removeprefix("test_").removesuffix(".py")
        for bucket in _split_file(ids):
            name = "-".join((level, stem, *bucket.labels))
            keyword = " and ".join(f"({expr})" for expr in bucket.exprs) or None
            yield file, name, keyword


def plan_pieces(
    level: Level,
    areas: AreaMap,
    collect: Callable[[Selection], Sequence[str]] | None = None,
) -> tuple[Piece, ...]:
    """Planeja os pedaços de um nível: um arquivo, partido por modo ou produto se possível.

    `tudo` soma `fast`, `prova`, `regressao` e `carga`. Os arquivos da carga saem de `prova`,
    porque a carga os roda inteiros e a prova repetiria parte deles.
    """
    if level == "changed":
        raise ConfigError("Os pedaços não existem para o nível changed. Use outro --nivel.")
    levels: tuple[PlannedLevel, ...] = PLANNED_LEVELS if level == "tudo" else (level,)
    pieces: list[Piece] = []
    for current in levels:
        selection = select_level(current, areas)
        if selection is None:  # pragma: no cover - só `changed` devolve vazio.
            continue
        ids = (collect or collect_node_ids)(selection)
        if level == "tudo" and current != "carga":
            ids = [i for i in ids if Path(i.split("::")[0]).name not in CARGA_FILES]
        for file, name, keyword in _level_pieces(current, ids):
            pieces.append(
                Piece(
                    index=len(pieces),
                    level=current,
                    file=file,
                    keyword=keyword,
                    name=name,
                )
            )
    if not pieces:
        raise ConfigError("A coleta não achou testes para o nível. Confira o mapa e os marcadores.")
    return tuple(pieces)


def build_command(
    selection: Selection, output: Path, keyword: str | None = None
) -> tuple[str, ...]:
    """Monta a chamada do pytest no mesmo Python que iniciou a rodada."""
    return (
        sys.executable,
        "-m",
        "pytest",
        *selection.paths,
        "-m",
        selection.marker,
        *(("-k", keyword) if keyword is not None else ()),
        f"--junitxml={output / 'junit.xml'}",
        "--durations=30",
        "-rfE",
    )


def _lock_owner(path: Path) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            return stream.read(4096).strip() or "dono não registrado"
    except OSError as exc:
        return f"dono indisponível ({exc})"


def _owns_lock(path: Path, stream: BinaryIO, token_line: bytes, *, written: bool) -> bool:
    try:
        named = path.lstat()
    except FileNotFoundError:
        sys.stderr.write(f"A trava {path} sumiu durante a rodada. Confira o laboratório.\n")
        return False
    # No POSIX o caminho pode ser renomeado mesmo com o arquivo aberto.
    same_file = os.name == "nt" or os.path.samestat(os.fstat(stream.fileno()), named)
    stream.seek(0)
    current = stream.readline(len(token_line))
    # Uma falha de escrita pode deixar vazio ou apenas um prefixo no arquivo recém-criado.
    token_matches = current == token_line if written else token_line.startswith(current)
    if same_file and token_matches:
        return True
    sys.stderr.write(f"A trava {path} mudou de identidade ou token. Confira o laboratório.\n")
    return False


@contextmanager
def lab_lock(path: Path, owner: str, started: datetime, level: Level) -> Iterator[None]:
    """Mantém aberto o arquivo criado exclusivamente até o fim da rodada.

    No Windows, outro processo não pode apagar ou substituir o arquivo aberto pelo
    Python. A liberação confere o token pelo identificador aberto e, no POSIX,
    a identidade do caminho. A janela entre fechar e apagar é aceitável porque
    as outras sessões só criam a trava de forma exclusiva e nunca a substituem.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    token_line = f"token: {uuid4()}\n".encode("ascii")
    try:
        stream = path.open("x+b", buffering=0)
    except FileExistsError as exc:
        raise LabBusy(f"Laboratório ocupado em {path}. {_lock_owner(path)}") from exc
    written = owned = False
    try:
        with stream:
            try:
                metadata = f"dono: {owner}\nUTC: {started.isoformat()}\nnível: {level}\n"
                data = token_line + metadata.encode("utf-8")
                if stream.write(data) != len(data):
                    raise OSError(f"Escrita incompleta da trava {path}. Confira o armazenamento.")
                written = True
                yield
            finally:
                owned = _owns_lock(path, stream, token_line, written=written)
    finally:
        if owned:
            try:
                path.unlink()
            except FileNotFoundError:
                sys.stderr.write(f"A trava {path} sumiu na liberação. Confira o laboratório.\n")


def _run_pytest(command: tuple[str, ...], output: Path, suffix: str) -> int:
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ConfigError(f"A pasta {output} contém arquivos. Escolha uma pasta de saída vazia.")
    metrics = output / "metricas"
    metrics.mkdir()
    env = dict(
        os.environ,
        HDAST_IT_STACK_SUFFIX=suffix,
        HDAST_IT_METRICS_DIR=str(metrics),
        PYTHONIOENCODING="utf-8",
    )
    log_path = output / "pytest.log"
    sys.stdout.write(f"Log da rodada em {log_path}\n")
    sys.stdout.flush()
    with log_path.open("xb") as log:
        return subprocess.run(  # noqa: S603 - executa o pytest local, sem shell.
            command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False
        ).returncode


def _parse_options(argv: Sequence[str] | None) -> RoundOptions:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nivel", dest="level", choices=LEVELS, default="changed")
    parser.add_argument("--base", default="origin/chore/reestruturacao")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sufixo", dest="suffix", default="-claude")
    parser.add_argument("--saida", dest="output", type=Path)
    parser.add_argument("--trava", dest="lock", type=Path, default=ARTIFACTS / "lab.lock")
    parser.add_argument("--dono", dest="owner", default=getuser())
    parser.add_argument("--arquivo", dest="file", help="Nome do arquivo de teste da seleção.")
    parser.add_argument("--k", dest="keyword", help="Expressão de seleção do pytest (-k).")
    parser.add_argument(
        "--pedacos-json",
        dest="pieces_json",
        action="store_true",
        help="Imprime os pedaços do nível em JSON, sem rodar. Com tudo, soma os quatro níveis.",
    )
    try:
        return RoundOptions.model_validate(vars(parser.parse_args(argv)))
    except ValidationError as exc:
        raise ConfigError(f"Opções inválidas. Confira --help. {exc}") from exc


def _run_round(options: RoundOptions) -> int:
    areas = load_map(MAP)
    if options.pieces_json:
        pieces = plan_pieces(options.level, areas)
        sys.stdout.write(json.dumps([piece.model_dump(mode="json") for piece in pieces]) + "\n")
        return 0
    changes = changed_paths(ROOT, options.base) if options.level == "changed" else ()
    selection = select_level(options.level, areas, changes)
    if selection is None:
        sys.stdout.write("Sem mudanças de código ou testes. Nenhuma rodada de laboratório.\n")
        return 0
    if options.file is not None:
        selection = restrict_to_file(selection, options.file)
    started = datetime.now(UTC)
    stamp = started.strftime("%Y%m%dT%H%M%S.%fZ")
    output = (options.output or ARTIFACTS / "rodadas" / f"{stamp}-{options.level}").absolute()
    command = build_command(selection, output, options.keyword)
    if options.dry_run:
        display = subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
        sys.stdout.write(f"{display}\nCaminhos selecionados\n")
        sys.stdout.writelines(f"  {path}\n" for path in selection.paths)
        return 0
    with lab_lock(options.lock, options.owner, started, options.level):
        return _run_pytest(command, output, options.suffix)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _run_round(_parse_options(argv))
    except HarnessError as exc:
        sys.stderr.write(f"{exc.message}\n")
        return exc.exit_code
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"Não foi possível preparar ou executar a rodada. {exc}\n")
        return ExitCode.USAGE
    except KeyboardInterrupt:
        sys.stderr.write("Rodada interrompida.\n")
        return ExitCode.INTERRUPTED


if __name__ == "__main__":
    raise SystemExit(main())

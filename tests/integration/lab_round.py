"""Seleciona testes do laboratório e registra a rodada sob uma trava exclusiva."""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from getpass import getuser
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from harness_dast.domain.errors import ConfigError, ExitCode, HarnessError

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = "tests/integration"
MAP = ROOT / INTEGRATION / "lab_areas.toml"
ARTIFACTS = Path("C:/harness-dast-artefatos")
LEVELS = ("changed", "fast", "prova", "regressao", "tudo")

type Level = Literal["changed", "fast", "prova", "regressao", "tudo"]
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


class LabBusy(HarnessError):
    code = "LAB_BUSY"
    exit_code = ExitCode.BUSY


@dataclass(frozen=True)
class Selection:
    marker: str
    paths: tuple[str, ...]


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
    affected: list[LabArea] = []
    covered: set[str] = set()
    for area in areas.areas.values():
        matches = {path for path in relevant if area.matches(path)}
        if matches:
            affected.append(area)
            covered.update(matches)
    all_fast = relevant != covered or bool(relevant.intersection(areas.shared))
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


def build_command(selection: Selection, output: Path) -> tuple[str, ...]:
    """Monta a chamada do pytest no mesmo Python que iniciou a rodada."""
    return (
        sys.executable,
        "-m",
        "pytest",
        *selection.paths,
        "-m",
        selection.marker,
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


@contextmanager
def lab_lock(path: Path, owner: str, started: datetime, level: Level) -> Iterator[None]:
    """Adquire a trava sem substituir uma existente e libera apenas a própria."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        stream = path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise LabBusy(f"Laboratório ocupado em {path}. {_lock_owner(path)}") from exc
    identity = os.fstat(stream.fileno())
    try:
        with stream:
            stream.write(f"dono: {owner}\nUTC: {started.isoformat()}\nnível: {level}\n")
        yield
    finally:
        if os.path.samestat(path.lstat(), identity):
            path.unlink()


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
    try:
        return RoundOptions.model_validate(vars(parser.parse_args(argv)))
    except ValidationError as exc:
        raise ConfigError(f"Opções inválidas. Confira --help. {exc}") from exc


def _run_round(options: RoundOptions) -> int:
    areas = load_map(MAP)
    changes = changed_paths(ROOT, options.base) if options.level == "changed" else ()
    selection = select_level(options.level, areas, changes)
    if selection is None:
        sys.stdout.write("Sem mudanças de código ou testes. Nenhuma rodada de laboratório.\n")
        return 0
    started = datetime.now(UTC)
    stamp = started.strftime("%Y%m%dT%H%M%S.%fZ")
    output = (options.output or ARTIFACTS / "rodadas" / f"{stamp}-{options.level}").absolute()
    command = build_command(selection, output)
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

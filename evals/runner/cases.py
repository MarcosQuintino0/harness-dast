"""Leitura dos casos de avaliacao e dos caminhos da pasta de uma rodada."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from evals.runner.models import Case

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = REPO_ROOT / "evals" / "cases"


class EvalError(Exception):
    """Erro de uso do executor: a mensagem diz o que houve e o que fazer."""


@dataclass(frozen=True)
class RoundDirs:
    """Pastas de uma rodada, todas dentro de `<out>`."""

    out: Path

    @property
    def workspace(self) -> Path:
        """Copia cega do repositorio, a unica coisa que o agente ve."""
        return self.out / "workspace"

    @property
    def plugin(self) -> Path:
        """Copia do plugin do layout `plugin`: fora do workspace, carregada com `--plugin-dir`."""
        return self.out / "plugin"

    @property
    def sealed(self) -> Path:
        """Lacrado: modo sorteado, segredos e relatorio de exclusao. Fora do workspace."""
        return self.out / "sealed"

    @property
    def trace(self) -> Path:
        """Rastro coletado depois da rodada."""
        return self.out / "trace"

    @property
    def state(self) -> Path:
        """`HDAST_STATE_DIR` da rodada (auditoria do proxy, estado da pilha)."""
        return self.out / "state"


def load_case(name: str, cases_dir: Path = CASES_DIR) -> Case:
    """Le `evals/cases/<name>/case.yml`.

    Raises:
        EvalError: Caso inexistente ou invalido.
    """
    path = cases_dir / name / "case.yml"
    if not path.is_file():
        known = sorted(item.name for item in cases_dir.iterdir() if item.is_dir())
        raise EvalError(f"Caso '{name}' nao existe em {cases_dir}. Casos: {', '.join(known)}.")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and "flaws_from" in loaded:
            loaded = _with_inherited_flaws(loaded, cases_dir)
        return Case.model_validate(loaded)
    except (yaml.YAMLError, ValidationError) as error:
        raise EvalError(f"{path} invalido: {error}") from error


def _with_inherited_flaws(loaded: dict[str, object], cases_dir: Path) -> dict[str, object]:
    """Resolve `flaws_from: <caso>`: o gabarito de falhas e o do outro caso, sem copia.

    Raises:
        EvalError: O caso de origem nao existe ou nao tem `flaws`.
    """
    merged = dict(loaded)
    source = str(merged.pop("flaws_from"))
    origin = cases_dir / source / "case.yml"
    base = yaml.safe_load(origin.read_text(encoding="utf-8")) if origin.is_file() else None
    if not isinstance(base, dict) or "flaws" not in base:
        raise EvalError(f"flaws_from: o caso '{source}' nao existe ou nao tem flaws.")
    merged["flaws"] = base["flaws"]
    return merged


def read_authorization(name: str, case: Case, cases_dir: Path = CASES_DIR) -> str:
    """Le a carta de autorizacao do caso.

    Raises:
        EvalError: Arquivo ausente.
    """
    path = cases_dir / name / case.authorization
    if not path.is_file():
        raise EvalError(f"Carta de autorizacao ausente: {path}.")
    return path.read_text(encoding="utf-8")


def load_round_case(
    dirs: RoundDirs, name: str, cases_dir: Path = CASES_DIR, *, case_file: Path | None = None
) -> Case:
    """Carrega o lacre ou o caso historico explicitamente informado pelo coordenador."""
    snapshot = dirs.sealed / "case.json"
    if case_file is not None and snapshot.exists():
        raise EvalError("A rodada ja tem case.json lacrado; nao substitua por --case-file.")
    path = case_file if case_file is not None else snapshot
    if path.exists() and not path.is_file():
        raise EvalError(f"Gabarito nao e um arquivo: {path}.")
    if path.is_file():
        try:
            case = Case.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as error:
            raise EvalError(f"Gabarito invalido: {path}: {error}") from error
        if case.name != name:
            raise EvalError(f"Gabarito {path} e do caso {case.name}, nao da rodada {name}.")
        return case
    if case_file is not None:
        raise EvalError(f"Gabarito historico nao encontrado: {case_file}.")
    if cases_dir == CASES_DIR:
        raise EvalError(
            "Rodada sem sealed/case.json: recupere o gabarito exato da rodada e informe "
            "--case-file CAMINHO; nao e seguro presumir a carta."
        )
    return load_case(name, cases_dir)

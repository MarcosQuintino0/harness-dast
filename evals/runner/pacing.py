"""Ritmo escolhido para a cópia da rodada, sem promover o padrão do produto."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from evals.runner.cases import EvalError

Pacing = Literal["legacy", "proxy"]
PACINGS = ("legacy", "proxy")


class RoundMeta(BaseModel):
    """Escolha explícita do coordenador; rodadas históricas podem não ter metadado."""

    model_config = ConfigDict(frozen=True, extra="ignore")
    schema_version: Literal[1] = 1
    pacing: Pacing


def configure_pacing(workspace: Path, pacing: str) -> RoundMeta:
    """Altera só a cópia do modelo quando proxy foi pedido; recusa YAML inválido."""
    try:
        meta = RoundMeta.model_validate({"pacing": pacing})
    except ValidationError as error:
        raise EvalError("Ritmo inválido: use legacy ou proxy.") from error
    if meta.pacing == "legacy":
        return meta
    path = workspace / "products" / "_template" / "target.yml"
    try:
        profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise EvalError(
            "Modelo da cópia ausente ou ilegível; não foi possível escolher proxy."
        ) from error
    if not isinstance(profile, dict) or not isinstance(profile.get("scan", {}), dict):
        raise EvalError("O modelo da cópia precisa ser um mapa YAML com scan como mapa.")
    profile.setdefault("scan", {})["pacing"] = "proxy"
    path.write_text(yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return meta


def read_pacing(out: Path) -> Pacing | None:
    """Ritmo registrado, ou desconhecido para rodada histórica sem meta; não infere legacy."""
    path = out / "meta.json"
    if not path.exists():
        return None
    try:
        return RoundMeta.model_validate_json(path.read_text(encoding="utf-8")).pacing
    except (OSError, ValidationError) as error:
        raise EvalError(
            "meta.json da rodada inválido; confira o ritmo registrado no prepare."
        ) from error

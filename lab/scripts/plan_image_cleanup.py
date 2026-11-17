"""Simula candidatos explicitamente registrados, sem executar Docker nem remoção."""

import argparse
import json
import re
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ImageRecord(BaseModel):
    """Registro exportado e conferido pelo coordenador, não uma prova de propriedade."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    image_id: str
    reference: str
    harness_created: bool
    in_use: bool
    protected: bool
    tags: list[str] = Field(min_length=1)

    @field_validator("image_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        """Exige ID completo para evitar ambiguidades."""
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            raise ValueError("ID deve ser sha256 completo")
        return value

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        """Restringe o registro a uma referência temporária nomeada."""
        if not re.fullmatch(r"hdast[-/][a-z0-9._/-]+:[a-z0-9._-]+", value):
            raise ValueError("referência temporária do harness inválida")
        return value


class Inventory(BaseModel):
    """Lista explícita; duplicatas são recusadas antes de qualquer seleção."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    images: list[ImageRecord] = Field(min_length=1)


def plan_cleanup(inventory: Inventory) -> list[str]:
    """Seleciona apenas registros elegíveis; não confirma estado nem remove imagens."""
    ids = [image.image_id for image in inventory.images]
    refs = [image.reference for image in inventory.images]
    if len(ids) != len(set(ids)) or len(refs) != len(set(refs)):
        raise ValueError("IDs ou referências duplicados")
    return [
        image.image_id
        for image in inventory.images
        if image.harness_created
        and not image.in_use
        and not image.protected
        and image.tags == [image.reference]
    ]


def main() -> int:
    """Lê um inventário e escreve somente um plano simulado."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    args = parser.parse_args()
    try:
        inventory = Inventory.model_validate_json(args.inventory.read_text(encoding="utf-8"))
        candidates = plan_cleanup(inventory)
    except (OSError, UnicodeError, ValidationError, ValueError) as exc:
        parser.exit(2, f"Inventário recusado: {exc}\n")
    sys.stdout.write(json.dumps({"simulation": True, "candidates": candidates}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

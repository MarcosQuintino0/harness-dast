"""O simulador de limpeza só apresenta candidatos explicitamente registrados."""

import pytest
from pydantic import ValidationError

from lab.scripts.plan_image_cleanup import ImageRecord, Inventory, plan_cleanup


def record(**changes: object) -> ImageRecord:
    data: dict[str, object] = {
        "image_id": "sha256:" + "a" * 64,
        "reference": "hdast-test:temporary",
        "harness_created": True,
        "in_use": False,
        "protected": False,
        "tags": ["hdast-test:temporary"],
    }
    data.update(changes)
    return ImageRecord.model_validate(data)


def test_seleciona_imagem_temporaria_explicita() -> None:
    image = record()
    assert plan_cleanup(Inventory(images=[image])) == [image.image_id]


@pytest.mark.parametrize(
    "changes",
    [
        {"harness_created": False},
        {"in_use": True},
        {"protected": True},
        {"tags": ["hdast-test:temporary", "other:latest"]},
    ],
)
def test_ignora_imagem_sem_condicoes_de_seguranca(changes: dict[str, object]) -> None:
    assert plan_cleanup(Inventory(images=[record(**changes)])) == []


@pytest.mark.parametrize("changes", [{"image_id": "sha256:bad"}, {"reference": "other:latest"}])
def test_recusa_registro_invalido(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        record(**changes)


def test_recusa_ids_duplicados() -> None:
    image = record()
    with pytest.raises(ValueError, match="duplicados"):
        plan_cleanup(Inventory(images=[image, image]))


def test_recusa_inventario_ausente_ou_malformado() -> None:
    for text in ("{}", "{", '{"images": []}'):
        with pytest.raises(ValidationError):
            Inventory.model_validate_json(text)

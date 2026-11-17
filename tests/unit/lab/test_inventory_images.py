"""Testes sintÃ©ticos do inventÃ¡rio que nunca consulta o Docker real."""

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from lab.scripts.inventory_images import Image, classify, compose_references, docker_inventory

A = "sha256:" + "a" * 64
B = "sha256:" + "b" * 64
D = "sha256:" + "d" * 64


def image(image_id: str, tags: list[str] | None, digests: list[str] | None = None) -> Image:
    return Image(id=image_id, tags=tags, digests=digests, size=2048, created="2026-01-01")


def test_composes_multiplos_e_build_padrao(tmp_path: Path) -> None:
    first = tmp_path / "compose.yaml"
    second = tmp_path / "compose.override.yml"
    first.write_text("name: hdast\nservices:\n  proxy:\n    build: .\n", encoding="utf-8")
    second.write_text("services:\n  app:\n    image: hdast/app:v1\n", encoding="utf-8")
    assert compose_references([first, second]) == {"hdast-proxy:latest", "hdast/app:v1"}


def test_alias_digest_e_containers() -> None:
    images = [image(A, ["hdast/app:v2"], ["outro/app@" + D]), image(B, ["hdast/old:v1"])]
    rows = classify(images, {B}, {"hdast/app:v1@" + D})
    assert [row["categoria"] for row in rows] == ["em_uso", "em_uso"]
    assert rows[0]["compose"] == ["outro/app@" + D]
    assert rows[1]["em_conteiner"] is True
    assert rows[0]["bytes"] == 2048
    assert rows[0]["tamanho"] == "2.00 KiB"


def test_imagens_proprias_alheias_e_sem_proveniencia() -> None:
    rows = classify(
        [image(A, ["harness/old:v1"]), image(B, ["other/app:v1"]), image(D, None)], set(), set()
    )
    assert [row["categoria"] for row in rows] == ["fora_compose", "nao_atribuivel"]
    assert rows[1]["referencias"] == []


@pytest.mark.parametrize(
    "content",
    [
        "services: [",
        "services: []",
        "services:\n  app:\n    image: ${IMAGE}\n",
        "include: [other.yml]\n",
    ],
)
def test_recusa_compose_invalido_ou_indeterminado(tmp_path: Path, content: str) -> None:
    path = tmp_path / "compose.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises((ValueError, ValidationError, yaml.YAMLError)):
        compose_references([path])


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"id": A, "tags": [], "digests": [], "size": -1, "created": "hoje"},
        {"id": "ruim", "tags": [], "digests": [], "size": 1, "created": "hoje"},
    ],
)
def test_recusa_imagem_ausente_ou_invalida(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Image.model_validate(data)


def test_consulta_apenas_campos_permitidos(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_command(args: list[str]) -> str:
        if args[1:3] == ["image", "ls"]:
            return json.dumps(A)
        if args[1:3] == ["image", "inspect"]:
            return "|".join(map(json.dumps, [A, ["hdast/app:v1"], [], 123, "hoje"]))
        if args[1] == "ps":
            return json.dumps("c" * 64)
        assert args[1:4] == ["inspect", "--type", "container"]
        assert args[5] == "{{json .Image}}"
        return json.dumps(A)

    monkeypatch.setattr("lab.scripts.inventory_images.command", fake_command)
    images, used = docker_inventory()
    assert images[0].size == 123
    assert used == {A}


@pytest.mark.parametrize("field", ["image", "build"])
def test_recusa_campo_de_servico_nulo(tmp_path: Path, field: str) -> None:
    path = tmp_path / "compose.yaml"
    path.write_text(f"services:\n  app:\n    {field}: null\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        compose_references([path])


def test_recusa_referencia_de_imagem_malformada() -> None:
    with pytest.raises(ValidationError):
        image(A, ["<none>:<none>"])

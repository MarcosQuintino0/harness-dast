"""Planejamento de imagens com inventários e Docker falsos, sem remoção."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from lab.scripts.plan_image_cleanup import (
    ROOT,
    BaselineRow,
    Candidate,
    Ledger,
    ProtectedImages,
    plan_cleanup,
    read_baseline,
)

IMAGE = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
REF = "hdast/v1-12-oast-temp:test"


class FakeDocker:
    def __init__(self) -> None:
        self.image: dict[str, object] = {"Id": IMAGE, "RepoTags": [REF], "RepoDigests": []}
        self.containers: list[dict[str, str]] = []
        self.resolved_baseline = OTHER

    def __call__(self, args: list[str]) -> object:
        if args[0] == "ps":
            return ["c" * 64 for _ in self.containers]
        if args[:3] == ["inspect", "--type", "container"]:
            return self.containers
        assert args[:4] == [
            "image",
            "inspect",
            "--format",
            "{{json .Id}}|{{json .RepoTags}}|{{json .RepoDigests}}",
        ]
        if args[-1] == REF:
            return [self.image]
        assert args[-1] in {IMAGE, OTHER}
        resolved = self.resolved_baseline if args[-1] == OTHER else args[-1]
        return [{"Id": resolved, "RepoTags": [], "RepoDigests": []}]


def inputs() -> tuple[Ledger, list[BaselineRow], ProtectedImages, FakeDocker]:
    return (
        Ledger(images=[Candidate(image_id=IMAGE, reference=REF)]),
        [BaselineRow(ID=OTHER, Digest=OTHER, Repository="existing", Tag="old")],
        ProtectedImages(images=["alpine:3@" + OTHER]),
        FakeDocker(),
    )


def test_gera_comando_restrito_para_imagem_propria() -> None:
    ledger, baseline, protected, docker = inputs()
    assert plan_cleanup(ledger, baseline, protected, docker) == [f"docker image rm {IMAGE}"]


def test_ledger_vazio_nao_consulta_docker() -> None:
    _, baseline, protected, _ = inputs()

    def unavailable(args: list[str]) -> object:
        raise AssertionError("consulta inesperada")

    assert plan_cleanup(Ledger(images=[]), baseline, protected, unavailable) == []


def test_baseline_sem_digest_preserva_bloqueio_por_id() -> None:
    ledger, _, protected, docker = inputs()
    baseline = [
        BaselineRow.model_validate({"ID": IMAGE, "Digest": "<none>", "Repository": "x", "Tag": "v"})
    ]
    assert baseline[0].Digest is None
    with pytest.raises(ValueError, match="imagem"):
        plan_cleanup(ledger, baseline, protected, docker)


def test_recusa_digest_malformado_na_captura() -> None:
    with pytest.raises(ValidationError):
        BaselineRow.model_validate(
            {"ID": IMAGE, "Digest": "sha256:bad", "Repository": "x", "Tag": "v"}
        )


def test_comando_nao_depende_de_tag_remapeavel() -> None:
    ledger, baseline, protected, docker = inputs()
    command = plan_cleanup(ledger, baseline, protected, docker)[0]
    docker.image["Id"] = OTHER
    assert command == f"docker image rm {IMAGE}"
    assert REF not in command


@pytest.mark.parametrize(
    "reason",
    [
        "baseline",
        "resolved_baseline",
        "baseline_digest",
        "remapped",
        "in_use",
        "foreign_tag",
        "protected",
    ],
)
def test_recusa_imagem_inelegivel(reason: str) -> None:
    ledger, baseline, protected, docker = inputs()
    if reason == "baseline":
        baseline.append(BaselineRow(ID=IMAGE, Digest=IMAGE, Repository="old", Tag="old"))
    elif reason == "resolved_baseline":
        docker.resolved_baseline = IMAGE
    elif reason == "baseline_digest":
        docker.image["RepoDigests"] = ["old@" + OTHER]
    elif reason == "remapped":
        docker.image["Id"] = OTHER
    elif reason == "in_use":
        docker.containers = [{"Image": IMAGE}]
    elif reason == "foreign_tag":
        docker.image["RepoTags"] = [REF, "other:latest"]
    else:
        docker.image["RepoDigests"] = ["alpine@" + OTHER]
    with pytest.raises(ValueError, match=r"imagem|referência"):
        plan_cleanup(ledger, baseline, protected, docker)


@pytest.mark.parametrize("reference", ["other:latest", "hdast/test:latest", REF + ";evil"])
def test_recusa_referencia_de_outro_projeto(reference: str) -> None:
    with pytest.raises(ValidationError):
        Candidate(image_id=IMAGE, reference=reference)


@pytest.mark.parametrize("content", ["", "{", "{}", '{"ID":"bad"}'])
def test_recusa_baseline_ausente_ou_malformado(tmp_path: Path, content: str) -> None:
    path = tmp_path / "baseline.jsonl"
    path.write_text(content, encoding="utf-8")
    with pytest.raises((ValueError, ValidationError)):
        read_baseline(path, hashlib.sha256(content.encode()).hexdigest())


def test_recusa_baseline_alterado(tmp_path: Path) -> None:
    path = tmp_path / "baseline.jsonl"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="captura inicial"):
        read_baseline(path)


def test_aceita_captura_jsonl_com_bom(tmp_path: Path) -> None:
    path = tmp_path / "baseline.jsonl"
    data = (
        b'\xef\xbb\xbf{"ID":"'
        + OTHER.encode()
        + b'","Digest":"'
        + OTHER.encode()
        + b'","Repository":"x","Tag":"v"}\n'
    )
    path.write_bytes(data)
    assert read_baseline(path, hashlib.sha256(data).hexdigest())[0].ID == OTHER


def test_manifesto_protege_todas_imagens_dos_composes() -> None:
    protected = json.loads((ROOT / "lab/scripts/protected-images.json").read_text())
    for name in (
        "compose.yaml",
        "lab/pilot/compose.yaml",
        "lab/crapi/compose.yaml",
        "lab/oast/compose.yaml",
    ):
        compose = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
        assert {s["image"] for s in compose["services"].values() if "image" in s} <= set(
            protected["images"]
        )
    readme = (ROOT / "lab/README.md").read_text(encoding="utf-8")
    assert all(f"`{ref}`" in readme for ref in protected["images"])

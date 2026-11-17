"""Gera comandos para revisão humana após validar imagens locais; nunca remove."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ROOT = Path(__file__).resolve().parents[2]
PROTECTED = ROOT / "lab/scripts/protected-images.json"
BASELINE_SHA256 = "e7aa7746b87f428e0f928a855c4947cf6389e25954f22398982feebf6130747e"
IMAGE_ID = r"sha256:[0-9a-f]{64}"
TEMP_REF = r"hdast/v1-12-oast-temp:[a-z0-9][a-z0-9._-]{0,63}"
Id = Annotated[str, Field(pattern=f"^{IMAGE_ID}$")]
Ref = Annotated[str, Field(pattern=f"^{TEMP_REF}$")]
Runner = Callable[[list[str]], object]


class Candidate(BaseModel):
    """Identidade explicitamente registrada ao criar a imagem nesta trilha."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    image_id: Id
    reference: Ref


class Ledger(BaseModel):
    """Registro explícito de imagens criadas durante esta trilha."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    images: list[Candidate] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_images(self) -> "Ledger":
        """Recusa entradas repetidas ou ambíguas."""
        if len({i.image_id for i in self.images}) != len(self.images) or len(
            {i.reference for i in self.images}
        ) != len(self.images):
            raise ValueError("IDs ou referências duplicados")
        return self


class BaselineRow(BaseModel):
    """Campos necessários da captura anterior à trilha."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
    ID: Id
    Digest: Id
    Repository: str
    Tag: str


class ProtectedImages(BaseModel):
    """Referências protegidas da tabela do laboratório."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    images: list[str] = Field(min_length=1)


class DockerImage(BaseModel):
    """Campos essenciais de `docker image inspect`."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
    Id: Id
    RepoTags: list[str] | None
    RepoDigests: list[str] | None


class DockerContainer(BaseModel):
    """Imagem efetivamente usada por um contêiner, inclusive parado."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
    Image: Id


def read_baseline(path: Path, expected_hash: str = BASELINE_SHA256) -> list[BaselineRow]:
    """Exige captura inicial não vazia e registros válidos."""
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError("captura inicial não corresponde ao registro do coordenador")
    rows = [
        BaselineRow.model_validate_json(line)
        for line in content.decode("utf-8-sig").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("baseline vazio")
    return rows


def container_ids(runner: Runner) -> set[str]:
    """Consulta todos os contêineres e exige inspeção completa de cada um."""
    listing = runner(["ps", "-a", "--no-trunc", "--format", "{{json .ID}}"])
    if not isinstance(listing, list) or not all(isinstance(item, str) for item in listing):
        raise ValueError("lista de contêineres inválida")
    if not listing:
        return set()
    if not all(re.fullmatch(r"[0-9a-f]{64}", item) for item in listing):
        raise ValueError("ID de contêiner inválido")
    data = runner(["inspect", "--type", "container", "--format", "{{json .Image}}", *listing])
    if not isinstance(data, list) or len(data) != len(listing):
        raise ValueError("inspeção de contêineres incompleta")
    return {DockerContainer.model_validate(item).Image for item in data}


def inspect_image(runner: Runner, reference: str) -> DockerImage:
    """Lê somente ID, tags e digests, sem dados de ambiente da imagem."""
    fields = "{{json .Id}}|{{json .RepoTags}}|{{json .RepoDigests}}"
    inspected = runner(["image", "inspect", "--format", fields, reference])
    if not isinstance(inspected, list) or len(inspected) != 1:
        raise ValueError("inspeção de imagem incompleta")
    return DockerImage.model_validate(inspected[0])


def protected_parts(protected: ProtectedImages) -> tuple[set[str], set[str]]:
    """Separa tags e digests para reconhecer aliases protegidos."""
    names: set[str] = set()
    digests: set[str] = set()
    for ref in protected.images:
        tag, separator, digest = ref.partition("@")
        if not tag or (separator and not re.fullmatch(IMAGE_ID, digest)):
            raise ValueError("referência protegida inválida")
        names.add(tag)
        if separator:
            digests.add(digest)
    return names, digests


def plan_cleanup(
    ledger: Ledger, baseline: list[BaselineRow], protected: ProtectedImages, runner: Runner
) -> list[str]:
    """Valida todas as imagens antes de devolver comandos estritos para revisão."""
    if not baseline:
        raise ValueError("baseline vazio")
    baseline_ids = {row.ID for row in baseline}
    baseline_digests = {row.Digest for row in baseline}
    for baseline_id in set(baseline_ids):
        baseline_image = inspect_image(runner, baseline_id)
        baseline_ids.add(baseline_image.Id)
        baseline_digests.update(ref.partition("@")[2] for ref in baseline_image.RepoDigests or [])
    baseline_refs = {f"{row.Repository}:{row.Tag}" for row in baseline}
    names, digests = protected_parts(protected)
    in_use = container_ids(runner)
    commands: list[str] = []
    for candidate in ledger.images:
        image = inspect_image(runner, candidate.reference)
        tags = image.RepoTags or []
        repo_digests = image.RepoDigests or []
        if image.Id != candidate.image_id or image.Id in baseline_ids or image.Id in in_use:
            raise ValueError("imagem remapeada, anterior à trilha ou em uso")
        if candidate.reference in baseline_refs or tags != [candidate.reference]:
            raise ValueError("referência anterior à trilha ou tags adicionais")
        if any(d.partition("@")[2] in baseline_digests for d in repo_digests):
            raise ValueError("imagem presente na captura inicial")
        if names.intersection(tags) or any(d.partition("@")[2] in digests for d in repo_digests):
            raise ValueError("imagem protegida")
        if any(not re.fullmatch(r"[^@\s]+@" + IMAGE_ID, digest) for digest in repo_digests):
            raise ValueError("digest de imagem inválido")
        commands.append(f"docker image rm {candidate.reference}")
    return commands


def main() -> int:
    """Lê registro e baseline e exibe comandos; não executa remoção."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("baseline", type=Path)
    args = parser.parse_args()
    try:
        ledger = Ledger.model_validate_json(args.ledger.read_text(encoding="utf-8"))
        baseline = read_baseline(args.baseline)
        protected = ProtectedImages.model_validate_json(PROTECTED.read_text(encoding="utf-8"))
        commands = plan_cleanup(ledger, baseline, protected, cli_docker_json)
    except (OSError, UnicodeError, ValidationError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"Plano recusado: {exc}\n")
    sys.stdout.write(json.dumps({"simulation": True, "commands": commands}) + "\n")
    return 0


def cli_docker_json(args: list[str]) -> object:
    """Lê campos selecionados do Docker, sem coletar variáveis de ambiente."""
    executable = shutil.which("docker")
    if executable is None:
        raise FileNotFoundError("Docker indisponível")
    done = subprocess.run(  # noqa: S603 - argumentos fixos, sem shell
        [executable, *args], capture_output=True, text=True, timeout=60, check=True
    )
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    if args[:2] == ["ps", "-a"]:
        return [json.loads(line) for line in lines]
    if args[:3] == ["inspect", "--type", "container"]:
        return [{"Image": json.loads(line)} for line in lines]
    if args[:2] == ["image", "inspect"]:
        images = []
        for line in lines:
            parts = line.split("|")
            if len(parts) != 3:
                raise ValueError("campos de inspeção inválidos")
            image_id, tags, digests = (json.loads(part) for part in parts)
            images.append({"Id": image_id, "RepoTags": tags, "RepoDigests": digests})
        return images
    raise ValueError("consulta Docker não permitida")


if __name__ == "__main__":
    raise SystemExit(main())

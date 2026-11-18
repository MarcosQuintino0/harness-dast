"""Inventário de imagens em ensaio, sem operação de alteração no Docker."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

ROOT = Path(__file__).resolve().parents[2]
ImageId = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
NonEmpty = Annotated[str, Field(min_length=1)]
IMAGE_DEFAULT = re.compile(
    r"\$\{HDAST_(?:ZAP|SCOPE_PROXY)_IMAGE:-([a-zA-Z0-9][a-zA-Z0-9._/:@-]*)\}"
)
OWN_IMAGE = re.compile(
    r"^(?:(?:harness|hdast)(?:[/-]|:|$)|ghcr\.io/marcosquintino0/hdast-(?:zap|scope-proxy)(?:[:@]|$))"
)


class Image(BaseModel):
    """Campos permitidos da inspeção de imagem."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    id: ImageId
    tags: list[NonEmpty] | None
    digests: list[NonEmpty] | None
    size: Annotated[int, Field(ge=0)]
    created: NonEmpty

    @field_validator("tags")
    @classmethod
    def validate_references(cls, value: list[str] | None) -> list[str] | None:
        """Recusa marcadores ou referências que não identificam uma imagem."""
        if value is not None and any(
            not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]*", ref) for ref in value
        ):
            raise ValueError("Referência de imagem inválida")
        return value

    @field_validator("digests")
    @classmethod
    def validate_digests(cls, value: list[str] | None) -> list[str] | None:
        """Exige referências de digest SHA-256 completas."""
        if value is not None and any(
            not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:-]*@sha256:[0-9a-f]{64}", ref)
            for ref in value
        ):
            raise ValueError("Digest de imagem inválido")
        return value


class Service(BaseModel):
    """Campos de serviço relevantes para imagens."""

    model_config = ConfigDict(extra="ignore", strict=True)
    image: NonEmpty | None = None
    build: str | dict[str, object] | None = None
    extends: str | dict[str, object] | None = None

    @field_validator("image", "build", mode="before")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        """Distingue chave ausente de valor explicitamente nulo."""
        if value is None:
            raise ValueError("Referência ou build ausente")
        return value


class Compose(BaseModel):
    """Campos relevantes de um arquivo Compose."""

    model_config = ConfigDict(extra="ignore", strict=True)
    name: NonEmpty | None = None
    services: dict[str, Service] = Field(default_factory=dict)
    include: list[str | dict[str, object]] = Field(default_factory=list)


def command(args: list[str]) -> str:
    """Executa uma consulta e recusa falhas sem incluir saída sensível no erro."""
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode:
        raise ValueError(
            f"Falhou a consulta {args[0]}; confira a disponibilidade e tente novamente"
        )
    return result.stdout


def compose_paths(root: Path) -> list[Path]:
    """Obtém todos os arquivos Compose versionados, inclusive anexos."""
    names = command(["git", "ls-files", "-z"]).split("\0")
    paths = [root / name for name in names if re.search(r"(?:^|/)[^/]*compose[^/]*\.ya?ml$", name)]
    if not paths:
        raise ValueError("Nenhum Compose versionado encontrado")
    return sorted(paths)


def compose_references(paths: list[Path]) -> set[str]:
    """Lê referências e padrões versionados sem consultar o ambiente."""
    references: set[str] = set()
    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        compose = Compose.model_validate(data)
        if compose.include or any(service.extends for service in compose.services.values()):
            raise ValueError(f"Compose com include/extends requer revisão: {path}")
        for name, service in compose.services.items():
            if service.image:
                references.add(_declared_image(service.image, path))
            elif service.build is not None:
                project = compose.name or path.parent.name
                if "$" in project or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project):
                    raise ValueError(f"Nome de projeto indeterminado em {path}")
                references.add(f"{project}-{name}:latest")
    return references


def _declared_image(expression: str, path: Path) -> str:
    default = IMAGE_DEFAULT.fullmatch(expression)
    if default:
        return default[1]
    if "$" in expression:
        raise ValueError(f"Imagem interpolada em {path}; não é possível classificá-la")
    return expression


def json_lines(text: str) -> list[object]:
    """Decodifica JSON por linha; saída vazia representa lista vazia."""
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def docker_inventory() -> tuple[list[Image], set[str]]:
    """Consulta somente IDs e os cinco campos permitidos, inclusive contêineres parados."""
    image_ids = TypeAdapter(list[ImageId]).validate_python(
        json_lines(
            command(["docker", "image", "ls", "-a", "--no-trunc", "--format", "{{json .ID}} "])
        )
    )
    image_ids = sorted(set(image_ids))
    images: list[Image] = []
    template = (
        "{{json .Id}}|{{json .RepoTags}}|{{json .RepoDigests}}|{{json .Size}}|{{json .Created}}"
    )
    for image_id in image_ids:
        fields = (
            command(["docker", "image", "inspect", "--format", template, image_id])
            .strip()
            .split("|")
        )
        if len(fields) != 5:
            raise ValueError("Inspeção de imagem incompleta")
        values = [json.loads(field) for field in fields]
        image = Image.model_validate(
            dict(zip(("id", "tags", "digests", "size", "created"), values, strict=True))
        )
        if image.id != image_id:
            raise ValueError("ID de imagem divergente")
        images.append(image)
    containers = TypeAdapter(
        list[Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]]
    ).validate_python(
        json_lines(command(["docker", "ps", "-a", "--no-trunc", "--format", "{{json .ID}} "]))
    )
    used: set[str] = set()
    for container in containers:
        value = json.loads(
            command(
                [
                    "docker",
                    "inspect",
                    "--type",
                    "container",
                    "--format",
                    "{{json .Image}}",
                    container,
                ]
            )
        )
        used.add(TypeAdapter(ImageId).validate_python(value))
    return images, used


def normalized(ref: str) -> str:
    """Normaliza a tag padrão, preservando referências por digest."""
    if "@" in ref or ref.startswith("sha256:"):
        return ref
    return ref if ":" in ref.rsplit("/", 1)[-1] else ref + ":latest"


def classify(images: list[Image], used: set[str], references: set[str]) -> list[dict[str, object]]:
    """Classifica apenas imagens próprias ou sem proveniência identificável."""
    refs = {normalized(ref) for ref in references}
    digests = {ref.split("@", 1)[1] for ref in refs if "@" in ref}
    rows: list[dict[str, object]] = []
    for image in images:
        names = (image.tags or []) + (image.digests or [])
        own = any(OWN_IMAGE.match(name) for name in names)
        if names and not own:
            continue
        matches = sorted(
            ref
            for ref in names
            if normalized(ref) in refs or ("@" in ref and ref.split("@", 1)[1] in digests)
        )
        if image.id in refs:
            matches.append(image.id)
        in_container = image.id in used
        category = (
            "nao_atribuivel"
            if not names
            else "em_uso"
            if matches or in_container
            else "fora_compose"
        )
        reason = (
            "sem tags ou digests"
            if not names
            else "; ".join(
                filter(
                    None,
                    [
                        "referência ou digest no Compose" if matches else "",
                        "usada por contêiner" if in_container else "",
                    ],
                )
            )
            or "namespace próprio sem referência Compose ou contêiner"
        )
        rows.append(
            {
                "id": image.id,
                "referencias": names,
                "compose": matches,
                "em_conteiner": in_container,
                "categoria": category,
                "razao": reason,
                "bytes": image.size,
                "tamanho": human_size(image.size),
                "criada": image.created,
            }
        )
    return rows


def human_size(size: int) -> str:
    """Apresenta bytes em unidades binárias sem perder o valor exato separado."""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    raise ValueError("Tamanho inválido")


def main() -> int:
    """Grava um relatório JSON de ensaio; não altera imagens."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Caminho do relatório JSON")
    args = parser.parse_args()
    try:
        refs = compose_references(compose_paths(ROOT))
        images, used = docker_inventory()
        report = {"modo": "ensaio", "imagens": classify(images, used, refs)}
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        sys.stderr.write(f"Inventário recusado: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fixa a tag e o commit publicados no marketplace do Claude Code."""

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, ValidationError

MARKETPLACE_PATH = Path(".claude-plugin/marketplace.json")
_TAG_PATTERN = r"^v[0-9](?:[A-Za-z0-9_-]|\.[A-Za-z0-9_-])*$"


class MarketplaceOwner(BaseModel, extra="forbid", frozen=True):
    """Identifica o projeto responsável pelo marketplace."""

    name: Literal["harness-dast"]


class MarketplaceSource(BaseModel, extra="forbid", frozen=True):
    """Localiza a pasta do plugin no commit publicado."""

    source: Literal["git-subdir"]
    url: HttpUrl
    path: Literal["plugin"]
    ref: Annotated[str, Field(pattern=_TAG_PATTERN, max_length=129)]
    sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")] | None = None


class MarketplacePlugin(BaseModel, extra="forbid", frozen=True):
    """Descreve a entrada do plugin hdast."""

    name: Literal["hdast"]
    source: MarketplaceSource


class Marketplace(BaseModel, extra="forbid", frozen=True):
    """Valida o manifesto distribuído por este repositório."""

    name: Literal["hdast"]
    owner: MarketplaceOwner
    plugins: tuple[MarketplacePlugin]


def main(argv: Sequence[str] | None = None) -> None:
    """Valida o manifesto e os argumentos antes de gravar a nova referência."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Tag publicada, com prefixo v.")
    parser.add_argument("sha", help="SHA de 40 caracteres hexadecimais do commit da tag.")
    default_path = Path(__file__).resolve().parents[1] / MARKETPLACE_PATH
    parser.add_argument("--path", type=Path, default=default_path, help="Arquivo do marketplace.")
    args = parser.parse_args(argv)
    path: Path = args.path
    try:
        marketplace = Marketplace.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError):
        parser.error("Confira se o marketplace.json existe e segue o formato esperado.")

    (plugin,) = marketplace.plugins
    try:
        source = MarketplaceSource(
            source=plugin.source.source,
            url=plugin.source.url,
            path=plugin.source.path,
            ref=args.tag,
            sha=args.sha,
        )
    except ValidationError:
        parser.error("Informe uma tag válida com prefixo v e o SHA do commit (40 hexadecimais).")

    updated = Marketplace(
        name=marketplace.name,
        owner=marketplace.owner,
        plugins=(MarketplacePlugin(name=plugin.name, source=source),),
    )
    try:
        path.write_text(updated.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except OSError:
        parser.error("Confira o caminho e as permissões para gravar marketplace.json.")


if __name__ == "__main__":
    main()

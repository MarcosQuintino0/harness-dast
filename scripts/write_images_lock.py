"""Grava os digests das imagens publicados pela CI, sem consultar o registro."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from harness_dast.domain.images_lock import ImagesLock

_DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1] / "src/harness_dast/adapters/docker/images.lock.json"
)
_SCHEMA_VERSION = 2
"""Esquema 2 (ADR 0122): o ZAP, o proxy de escopo e o Nuclei."""


def _image_data(reference: str, version: str) -> dict[str, str]:
    repository, _, digest = reference.partition("@")
    return {"repository": repository, "tag": version, "digest": digest}


def main(argv: Sequence[str] | None = None) -> None:
    """Valida a versão e as referências da publicação antes de gravar o arquivo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Versão da CLI e tag das três imagens.")
    parser.add_argument("zap", help="Imagem do ZAP como repositório@digest.")
    parser.add_argument("scope_proxy", help="Imagem do proxy como repositório@digest.")
    parser.add_argument("nuclei", help="Imagem do Nuclei como repositório@digest.")
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT, help="Arquivo de saída.")
    args = parser.parse_args(argv)
    try:
        lock = ImagesLock.model_validate(
            {
                "schema_version": _SCHEMA_VERSION,
                "version": args.version,
                "images": {
                    "zap": _image_data(args.zap, args.version),
                    "scope_proxy": _image_data(args.scope_proxy, args.version),
                    "nuclei": _image_data(args.nuclei, args.version),
                },
            }
        )
    except ValidationError:
        parser.error("Informe uma versão válida e três referências repositório@sha256:<64 hex>.")
    try:
        args.output.write_text(lock.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except OSError:
        parser.error("Não consegui gravar images.lock.json. Confira o caminho e as permissões.")


if __name__ == "__main__":
    main()

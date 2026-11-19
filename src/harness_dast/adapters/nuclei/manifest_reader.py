"""Leitura do manifesto dos modelos do Nuclei empacotado com a CLI (ADR 0122).

O que garante: ou devolve um `NucleiManifest` validado, da versão fixada em `nuclei_version.py`,
ou levanta `ConfigError` com o que fazer. A CLI decide sem Docker, só por este arquivo.
O que não faz: não gera o manifesto (isso é de `scripts/build_nuclei_manifest.py`) nem lê os
modelos do catálogo.
"""

import gzip
import zlib
from io import BytesIO
from pathlib import Path

from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.nuclei_manifest import NucleiManifest

__all__ = ["MANIFEST_PATH", "load_nuclei_manifest"]

MANIFEST_PATH = Path(__file__).with_name("data") / "nuclei-manifest.json.gz"
_MAX_PACKED_BYTES = 32 * 1024 * 1024
_MAX_UNPACKED_BYTES = 128 * 1024 * 1024
_RECOVERY = (
    "Reinstale a CLI com o pacote publicado ou gere o manifesto com build_nuclei_manifest.py."
)


def load_nuclei_manifest(path: Path = MANIFEST_PATH) -> NucleiManifest:
    """Lê e valida o manifesto empacotado.

    Args:
        path: Arquivo `.json.gz`; o padrão é o que vai no pacote.

    Raises:
        ConfigError: Arquivo ausente, grande demais, corrompido ou de outra versão do catálogo.
    """
    try:
        with path.open("rb") as source:
            packed = source.read(_MAX_PACKED_BYTES + 1)
    except FileNotFoundError:
        raise ConfigError(
            "O manifesto dos modelos do Nuclei não está no pacote.", hint=_RECOVERY
        ) from None
    except OSError:
        raise ConfigError(
            "Não consegui ler o manifesto dos modelos do Nuclei.", hint=_RECOVERY
        ) from None
    if len(packed) > _MAX_PACKED_BYTES:
        raise ConfigError("O manifesto dos modelos do Nuclei é grande demais.", hint=_RECOVERY)
    try:
        # Descompressão limitada: um arquivo adulterado não pode esgotar a memória.
        with gzip.GzipFile(fileobj=BytesIO(packed)) as unpacked:
            data = unpacked.read(_MAX_UNPACKED_BYTES + 1)
    except (OSError, EOFError, zlib.error):
        raise ConfigError(
            "O manifesto dos modelos do Nuclei está corrompido.", hint=_RECOVERY
        ) from None
    if len(data) > _MAX_UNPACKED_BYTES:
        raise ConfigError("O manifesto dos modelos do Nuclei é grande demais.", hint=_RECOVERY)
    try:
        return NucleiManifest.model_validate_json(data)
    except ValidationError:
        raise ConfigError(
            "O manifesto dos modelos do Nuclei é inválido ou de outra versão do catálogo.",
            hint=_RECOVERY,
        ) from None

"""Leitura dos digests empacotados e verificação dos contextos locais de build."""

from pathlib import Path

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.images_lock import IMAGES_LOCK_RECOVERY, ImagesLock

_LOCK_PATH = Path(__file__).with_name("images.lock.json")
_MAX_LOCK_BYTES = 4096


def load_images_lock(path: Path = _LOCK_PATH) -> ImagesLock | None:
    """Lê os digests da instalação. Só devolve None se o arquivo estiver ausente.

    Raises:
        ConfigError: Arquivo presente, ilegível ou inválido.
    """
    try:
        with path.open("rb") as source:
            data = source.read(_MAX_LOCK_BYTES + 1)
    except FileNotFoundError:
        if not path.is_symlink():
            return None
        raise ConfigError(
            "O arquivo images.lock.json aponta para um destino ausente.",
            hint=IMAGES_LOCK_RECOVERY,
        ) from None
    except OSError:
        raise ConfigError(
            "Não consegui ler o arquivo images.lock.json.", hint=IMAGES_LOCK_RECOVERY
        ) from None
    if len(data) > _MAX_LOCK_BYTES:
        raise ConfigError(
            "O arquivo images.lock.json excede o tamanho máximo.", hint=IMAGES_LOCK_RECOVERY
        )
    try:
        return ImagesLock.model_validate_json(data)
    except ValueError:
        raise ConfigError(
            "O arquivo images.lock.json é inválido.", hint=IMAGES_LOCK_RECOVERY
        ) from None


def has_build_contexts(root: Path) -> bool:
    """Verifica os três caminhos de build declarados no Compose da pilha."""
    return (
        (root / "docker/zap").is_dir()
        and (root / "docker/scope-proxy/Dockerfile").is_file()
        and (root / "docker/nuclei/Dockerfile").is_file()
    )

"""Repositório de perfis em arquivos: lê `<produtos>/<produto>/target.yml`.

Implementa a porta `ProfileRepository`. Traduz o mundo de arquivos em `ProductProfile` e toda
falha de I/O ou de YAML em `ConfigError`; não decide regra de negócio (quem valida o perfil é
`ProductProfile.from_data`, no domínio).
"""

from pathlib import Path

from harness_dast.adapters.storage.product_paths import product_dir_path
from harness_dast.adapters.storage.strict_yaml import MAX_PROFILE_BYTES, parse_profile_yaml
from harness_dast.application.common_ports import ReferencedFile
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile

PROFILE_FILE = "target.yml"
_INIT_HINT = "Crie o produto com: hdast init <produto>."


def read_profile_text(target: Path) -> str:
    """Lê o `target.yml` (UTF-8, com teto de tamanho); falha de leitura vira `ConfigError`."""
    try:
        with target.open("rb") as handle:
            raw = handle.read(MAX_PROFILE_BYTES + 1)
    except OSError:
        raise ConfigError(
            f"Não foi possível ler o {PROFILE_FILE}.",
            hint="Confira a permissão de leitura do arquivo.",
        ) from None
    if len(raw) > MAX_PROFILE_BYTES:
        raise ConfigError(
            f"O {PROFILE_FILE} é grande demais (máximo {MAX_PROFILE_BYTES // 1024} KiB).",
            hint="Um perfil legítimo é pequeno; confira se o arquivo é o correto.",
        )
    try:
        # utf-8-sig aceita (e remove) a marca BOM que editores do Windows costumam gravar.
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ConfigError(
            f"O {PROFILE_FILE} não está em UTF-8.", hint="Salve o arquivo como UTF-8."
        ) from None


def _references(profile: ProductProfile) -> list[ReferencedFile]:
    found = [ReferencedFile(field="openapi", path=profile.openapi)]
    if profile.cleanup is not None:
        found.append(ReferencedFile(field="cleanup.script", path=profile.cleanup.script))
    return found


def _resolve_inside(product_dir: Path, reference: ReferencedFile) -> Path:
    try:
        resolved = (product_dir / reference.path).resolve()
    except (OSError, RuntimeError):
        raise ConfigError(
            f"Não foi possível resolver o caminho de {reference.field}.",
            hint="Confira se há link simbólico quebrado ou circular.",
        ) from None
    if not resolved.is_relative_to(product_dir):
        raise ConfigError(
            f"O caminho de {reference.field} sai da pasta do produto.",
            hint="Mantenha os arquivos do produto dentro da pasta dele (sem links para fora).",
        )
    return resolved


class FileProfileRepository:
    """Lê perfis de produto do sistema de arquivos."""

    def __init__(self, products_dir: Path) -> None:
        """Cria o repositório.

        Args:
            products_dir: Pasta que contém uma subpasta por produto.
        """
        self._products_dir = products_dir

    def _product_dir(self, product: str) -> Path:
        directory = product_dir_path(self._products_dir, product)
        if not directory.is_dir():
            raise ConfigError(
                f"O produto {product} não existe em {self._products_dir}.", hint=_INIT_HINT
            )
        return directory

    def load(self, product: str) -> ProductProfile:
        """Carrega e valida o perfil (veja `ProfileRepository.load`)."""
        directory = self._product_dir(product)
        target = directory / PROFILE_FILE
        if not target.is_file():
            raise ConfigError(
                f"O produto {product} não tem {PROFILE_FILE}.",
                hint="Copie products/_template/target.yml ou recrie com hdast init.",
            )
        if not target.resolve().is_relative_to(directory):
            raise ConfigError(
                f"O {PROFILE_FILE} aponta para fora da pasta do produto.",
                hint="Remova o link simbólico; o perfil deve ser um arquivo da própria pasta.",
            )
        profile = ProductProfile.from_data(parse_profile_yaml(read_profile_text(target)))
        if profile.product != product:
            raise ConfigError(
                "O campo product do perfil não confere com o nome da pasta.",
                hint=f"Ajuste product para {product} (ou renomeie a pasta).",
            )
        for reference in _references(profile):
            _resolve_inside(directory, reference)
        return profile

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        """Lista os arquivos referenciados que não existem (veja `ProfileRepository`)."""
        directory = self._product_dir(product)
        return tuple(
            reference
            for reference in _references(profile)
            if not _resolve_inside(directory, reference).is_file()
        )

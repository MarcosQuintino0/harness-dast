"""Repositório de perfis em memória, com o comportamento da porta `ProfileRepository`."""

from harness_dast.application.common_ports import ReferencedFile
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile


class InMemoryProfileRepository:
    """Guarda perfis por nome e a lista de arquivos referenciados que existem."""

    def __init__(self) -> None:
        self._profiles: dict[str, ProductProfile] = {}
        self._existing_files: dict[str, set[str]] = {}

    def add(self, profile: ProductProfile, *, existing_files: set[str] | None = None) -> None:
        """Cadastra um perfil; `existing_files` são os caminhos que existem na pasta dele."""
        self._profiles[profile.product] = profile
        self._existing_files[profile.product] = set(existing_files or ())

    def load(self, product: str) -> ProductProfile:
        if product not in self._profiles:
            raise ConfigError(f"O produto {product} não existe.", hint="Crie com hdast init.")
        return self._profiles[product]

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        existing = self._existing_files.get(product, set())
        wanted = [ReferencedFile(field="openapi", path=profile.openapi)]
        if profile.cleanup is not None:
            wanted.append(ReferencedFile(field="cleanup.script", path=profile.cleanup.script))
        return tuple(item for item in wanted if item.path not in existing)

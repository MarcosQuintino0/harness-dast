"""Arquivos de regras do produto (`data-rules.yml`, `flows.yml`) e seus hashes.

Implementa `ProductDocuments`. Usa o leitor de YAML endurecido; limita tamanho e codificação;
recusa arquivo que, por link simbólico, saia da pasta do produto. Traduz toda falha de I/O ou
de YAML em `ConfigError` sem repetir o conteúdo do arquivo.
"""

import hashlib
from pathlib import Path

from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.adapters.storage.profile_repository import PROFILE_FILE
from harness_dast.adapters.storage.strict_yaml import MAX_PROFILE_BYTES, parse_yaml_document
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.probe_result import ArtifactHashes
from harness_dast.domain.profile import ProductProfile

DATA_RULES_FILE = "data-rules.yml"
FLOWS_FILE = "flows.yml"
_HASH_BLOCK = 1024 * 1024


def _read_text(path: Path, label: str) -> str:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_PROFILE_BYTES + 1)
    except OSError:
        raise ConfigError(
            f"Não foi possível ler o {label}.", hint="Confira a permissão de leitura do arquivo."
        ) from None
    if len(raw) > MAX_PROFILE_BYTES:
        raise ConfigError(
            f"O {label} é grande demais (máximo {MAX_PROFILE_BYTES // 1024} KiB).",
            hint="Um arquivo de regras legítimo é pequeno; confira se é o arquivo correto.",
        )
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ConfigError(
            f"O {label} não está em UTF-8.", hint="Salve o arquivo como UTF-8."
        ) from None


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while block := handle.read(_HASH_BLOCK):
                digest.update(block)
    except OSError:
        raise ConfigError(
            f"Não foi possível ler {path.name} para calcular o hash.",
            hint="Confira a permissão de leitura do arquivo.",
        ) from None
    return digest.hexdigest()


class FileProductDocuments:
    """Lê as regras do produto do sistema de arquivos."""

    def __init__(self, products_dir: Path) -> None:
        """Cria o leitor.

        Args:
            products_dir: Pasta que contém uma subpasta por produto.
        """
        self._products_dir = products_dir

    def _document(self, product: str, name: str) -> dict[str, object] | None:
        path = resolve_product_file(self._products_dir, product, name)
        if not path.is_file():
            return None
        return parse_yaml_document(_read_text(path, name), name)

    def load_data_rules(self, product: str) -> DataRules | None:
        """Lê e valida `data-rules.yml` (veja `ProductDocuments.load_data_rules`)."""
        data = self._document(product, DATA_RULES_FILE)
        return None if data is None else DataRules.from_data(data)

    def load_flows(self, product: str) -> FlowSpec | None:
        """Lê e valida `flows.yml` (veja `ProductDocuments.load_flows`)."""
        data = self._document(product, FLOWS_FILE)
        return None if data is None else FlowSpec.from_data(data)

    def hashes(self, product: str, profile: ProductProfile) -> ArtifactHashes:
        """Calcula o SHA-256 dos arquivos de entrada (veja `ProductDocuments.hashes`)."""

        def digest(name: str) -> str | None:
            return _sha256(resolve_product_file(self._products_dir, product, name))

        return ArtifactHashes(
            target_yml=digest(PROFILE_FILE),
            data_rules=digest(DATA_RULES_FILE),
            flows=digest(FLOWS_FILE),
            openapi=digest(profile.openapi),
        )

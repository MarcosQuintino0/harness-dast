"""Armazém local da estratégia; nunca lê ou grava aprovação nem credenciais."""

import re
from pathlib import Path

from harness_dast.adapters.storage.product_paths import product_dir_path, resolve_product_file
from harness_dast.adapters.storage.strict_yaml import MAX_PROFILE_BYTES, parse_yaml_document
from harness_dast.domain.errors import ConfigError

_COPY_NAME = re.compile(r"strategy\.[a-z0-9-]+\.yml\Z")
_MIGRATED = (
    "schema_version: 1\n"
    "references:\n  target: target.yml\n  data_rules: data-rules.yml\n  flows: flows.yml\n"
    "choices: []\n"
)


class FileStrategyRepository:
    """Lê estratégia confinada ao produto e cria cópia de migração sem substituir arquivo."""

    def __init__(self, products_dir: Path) -> None:
        """Recebe a pasta de produtos."""
        self._root = products_dir

    def read(self, product: str) -> dict[str, object] | None:
        """Devolve YAML validado estruturalmente, ou None quando estratégia não existe."""
        path = resolve_product_file(self._root, product, "strategy.yml")
        if not path.exists():
            return None
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_PROFILE_BYTES + 1)
            if len(raw) > MAX_PROFILE_BYTES:
                raise ConfigError("O strategy.yml é grande demais.")
            text = raw.decode("utf-8-sig")
        except (OSError, UnicodeError):
            raise ConfigError("Não foi possível ler strategy.yml em UTF-8.") from None
        return parse_yaml_document(text, "strategy.yml")

    def check_references(self, product: str) -> None:
        """Recusa referências que escapem da pasta do produto por links simbólicos."""
        for name in ("target.yml", "data-rules.yml", "flows.yml"):
            resolve_product_file(self._root, product, name)

    def migrate(self, product: str, output: str) -> str:
        """Cria uma cópia neutra com nome restrito, sem sobrescrever nenhum arquivo."""
        if not _COPY_NAME.fullmatch(output):
            raise ConfigError("Nome de destino inválido para a cópia da estratégia.")
        directory = product_dir_path(self._root, product)
        if not directory.is_dir():
            raise ConfigError("Produto inexistente.")
        self.check_references(product)
        try:
            with (directory / output).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(_MIGRATED)
        except OSError:
            raise ConfigError("Não foi possível criar a cópia; confira se já existe.") from None
        return output

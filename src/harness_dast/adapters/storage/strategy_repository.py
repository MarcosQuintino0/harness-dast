"""Armazém local da estratégia; nunca lê ou grava aprovação nem credenciais."""

import re
from pathlib import Path

import yaml

from harness_dast.adapters.storage.product_paths import product_dir_path, resolve_product_file
from harness_dast.adapters.storage.strict_yaml import MAX_PROFILE_BYTES, parse_yaml_document
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.strategy import Strategy, StrategyReferences

_COPY_NAME = re.compile(r"strategy\.[a-z0-9-]+\.yml\Z")
_MAX_DEPENDENCY_BYTES = 8 * 1024 * 1024
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

    def check_references(self, product: str, references: StrategyReferences) -> None:
        """Recusa referências que escapem da pasta do produto por links simbólicos."""
        for name in (references.target, references.data_rules, references.flows):
            resolve_product_file(self._root, product, name)

    def read_dependencies(
        self, product: str, profile: ProductProfile
    ) -> tuple[bytes, bytes | None, bytes | None]:
        """Lê apenas OpenAPI e os dois documentos locais, sem seguir links externos."""
        contract = self._dependency(product, profile.openapi, required=True)
        if contract is None:
            raise ConfigError("Contrato OpenAPI ausente.")
        return (
            contract,
            self._dependency(product, "data-rules.yml"),
            self._dependency(product, "flows.yml"),
        )

    def _dependency(self, product: str, name: str, *, required: bool = False) -> bytes | None:
        path = resolve_product_file(self._root, product, name)
        if any(part.startswith(".") for part in Path(name).parts):
            raise ConfigError("Caminho de documento incompatível com a estratégia.")
        if path.name.startswith(".") or path.suffix.lower() not in {".yml", ".yaml", ".json"}:
            raise ConfigError("Caminho de documento incompatível com a estratégia.")
        if not path.exists() and not required:
            return None
        try:
            with path.open("rb") as stream:
                data = stream.read(_MAX_DEPENDENCY_BYTES + 1)
        except OSError:
            raise ConfigError("Não foi possível ler documento da estratégia.") from None
        if len(data) > _MAX_DEPENDENCY_BYTES:
            raise ConfigError("Documento da estratégia excede o tamanho permitido.")
        return data

    def migrate(self, product: str, output: str) -> str:
        """Cria uma cópia neutra com nome restrito, sem sobrescrever nenhum arquivo."""
        self.check_references(
            product,
            StrategyReferences(target="target.yml", data_rules="data-rules.yml", flows="flows.yml"),
        )
        return self._write_copy(product, output, _MIGRATED)

    def write_capture(self, product: str, output: str, strategy: Strategy) -> str:
        """Grava estratégia capturada numa cópia exclusiva, nunca a ativa."""
        self.check_references(product, strategy.references)
        text = yaml.safe_dump(strategy.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
        return self._write_copy(product, output, text)

    def _write_copy(self, product: str, output: str, text: str) -> str:
        if not _COPY_NAME.fullmatch(output):
            raise ConfigError("Nome de destino inválido para a cópia da estratégia.")
        directory = product_dir_path(self._root, product)
        if not directory.is_dir():
            raise ConfigError("Produto inexistente.")
        path = directory / output
        created = False
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                created = True
                stream.write(text)
        except OSError:
            if created:
                try:
                    path.unlink()
                except OSError:
                    raise ConfigError(
                        "Falha ao gravar a cópia e ao remover o arquivo incompleto."
                    ) from None
            raise ConfigError("Não foi possível criar a cópia; confira se já existe.") from None
        return output

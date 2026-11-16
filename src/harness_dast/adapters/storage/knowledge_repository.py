"""Leitura estrita e captura separada do conhecimento do produto."""

from pathlib import Path

import yaml

from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.adapters.storage.strict_yaml import MAX_PROFILE_BYTES, parse_yaml_document
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge import Knowledge


class FileKnowledgeStore:
    """Lê conhecimento confinado ao produto e não substitui arquivos na captura."""

    def __init__(self, root: Path) -> None:
        """Recebe diretório de produtos."""
        self._root = root

    def read(self, product: str) -> dict[str, object] | None:
        """Lê YAML estrito; ausência não altera o comportamento legado."""
        path = resolve_product_file(self._root, product, "knowledge.yml")
        if not path.exists():
            return None
        try:
            with path.open("rb") as stream:
                data = stream.read(MAX_PROFILE_BYTES + 1)
            if len(data) > MAX_PROFILE_BYTES:
                raise ConfigError("knowledge.yml excede o tamanho permitido.")
            content = data.decode("utf-8-sig")
        except (OSError, UnicodeError):
            raise ConfigError("Não foi possível ler knowledge.yml.") from None
        return parse_yaml_document(content, "knowledge.yml")

    def write_capture(self, product: str, knowledge: object) -> str:
        """Cria cópia separada com modelo validado, sem ativação implícita."""
        model = Knowledge.from_data(knowledge)
        path = resolve_product_file(self._root, product, "knowledge.captured.yml")
        text = yaml.safe_dump(model.model_dump(mode="json"), sort_keys=False)
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
        except OSError:
            raise ConfigError("Não foi possível criar knowledge.captured.yml.") from None
        return path.name

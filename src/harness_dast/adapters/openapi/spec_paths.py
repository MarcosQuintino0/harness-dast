"""Leitor dos caminhos de um OpenAPI ao lado da carta (implementa a porta `SpecPathReader`).

Usado só pelo `hdast init --from-letter` no modo pedido mínimo (ADR 0120): o produto ainda não
existe, então o arquivo é procurado a partir da pasta da carta. Só abre arquivo dentro dessa
pasta (nada de caminho absoluto, `..` nem link simbólico para fora) e delega a leitura a
`load_spec`, que já limita tamanho e recusa `$ref` remota. Não envia nada a ninguém.
"""

from pathlib import Path

from harness_dast.adapters.openapi.loader import load_spec
from harness_dast.domain.errors import ConfigError


class FileSpecPaths:
    """Lê os modelos de caminho (`/users/{id}`) de um OpenAPI em arquivo."""

    def read_paths(self, base_dir: Path, relative: str) -> tuple[str, ...]:
        """Devolve os caminhos do OpenAPI, sem repetição, na ordem do documento.

        Raises:
            ConfigError: Caminho fora da pasta da carta, arquivo ausente, ilegível ou que não é
                um OpenAPI 3.x válido.
        """
        try:
            base = base_dir.resolve()
            target = (base / relative).resolve()
        except (OSError, RuntimeError):
            raise ConfigError(
                "Não foi possível resolver o caminho do OpenAPI.",
                hint="Confira se há link simbólico quebrado ou circular.",
            ) from None
        if not target.is_relative_to(base) or not target.is_file():
            raise ConfigError(
                "O OpenAPI do pedido mínimo precisa ser um arquivo ao lado da carta.",
                hint="Ponha o OpenAPI na pasta da carta e use em environment.openapi o caminho "
                "relativo a ela (o mesmo nome vale depois dentro da pasta do produto).",
            )
        spec = load_spec(target)
        return tuple(dict.fromkeys(operation.path for operation in spec.operations))

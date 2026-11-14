"""Leitor da carta estruturada (`carta.yml`) em arquivo.

Implementa a porta `LetterReader`. Usa o leitor de YAML endurecido (sem âncoras, aliases,
tags nem chaves repetidas), limita o tamanho e a codificação e traduz toda falha de I/O ou de
YAML em `ConfigError` sem repetir o conteúdo (o arquivo pode ter um segredo digitado por
engano).
"""

from collections.abc import Mapping
from pathlib import Path

from harness_dast.adapters.storage.strict_yaml import MAX_PROFILE_BYTES, parse_yaml_document
from harness_dast.domain.errors import ConfigError

LETTER_DOCUMENT = "carta.yml"
_LETTER_HINT = "Veja o formulário comentado em docs/guides/modelo-de-autorizacao.md."


class FileLetterReader:
    """Lê a carta do sistema de arquivos."""

    def read(self, path: Path) -> Mapping[str, object]:
        """Lê a carta como mapa (veja `LetterReader.read`)."""
        try:
            if not path.is_file():
                raise ConfigError(
                    f"A carta {path.name} não foi encontrada ou não é um arquivo.",
                    hint=_LETTER_HINT,
                )
            with path.open("rb") as handle:
                raw = handle.read(MAX_PROFILE_BYTES + 1)
        except OSError:
            raise ConfigError(
                f"Não foi possível ler a carta {path.name}.",
                hint="Confira o caminho e a permissão de leitura do arquivo.",
            ) from None
        if len(raw) > MAX_PROFILE_BYTES:
            raise ConfigError(
                f"A carta é grande demais (máximo {MAX_PROFILE_BYTES // 1024} KiB).",
                hint="Uma carta legítima é pequena; confira se o arquivo é o correto.",
            )
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ConfigError(
                "A carta não está em UTF-8.", hint="Salve o arquivo como UTF-8."
            ) from None
        return parse_yaml_document(text, LETTER_DOCUMENT)

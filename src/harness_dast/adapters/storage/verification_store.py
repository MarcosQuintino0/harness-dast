"""Leitura e escrita atômica do contrato de verificação."""

import os
import tempfile
from pathlib import Path

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.redaction import Masker, redact_body, redact_header_block
from harness_dast.domain.strict_json import parse_strict_json
from harness_dast.domain.verification import VerificationFile, parse_verification


class VerificationStore:
    """Armazena um envelope em caminho fornecido pelo chamador, sem resolver identidades."""

    def __init__(self, path: Path, mask: Masker) -> None:
        """Recebe caminho e máscara dos segredos registrados na execução."""
        self._path = path
        self._mask = mask

    def read(self) -> VerificationFile:
        """Lê e valida o arquivo; ausência, JSON malformado e erro de leitura falham fechados."""
        try:
            data = parse_strict_json(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ConfigError):
            raise ConfigError(
                "Não foi possível ler verification.json válido.",
                hint="Confira a existência e o formato do arquivo.",
            ) from None
        return parse_verification(data)

    def write(self, verification: VerificationFile) -> None:
        """Redige textos com a máscara fornecida e substitui o arquivo atomicamente."""
        entries = []
        for entry in verification.entries:
            values = entry.model_dump()
            for field in ("reason", "attack", "control"):
                value = values[field]
                if isinstance(value, str):
                    header, _ = redact_header_block(value, self._mask)
                    values[field] = redact_body(header, self._mask)[0]
            entries.append(values)
        data = verification.model_dump()
        data["entries"] = entries
        clean = parse_verification(data)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._path.parent, delete=False
            ) as handle:
                temporary = handle.name
                handle.write(clean.model_dump_json(indent=2) + "\n")
            os.replace(temporary, self._path)
        except OSError:
            raise ConfigError(
                "Não foi possível gravar verification.json.",
                hint="Confira a pasta e a permissão de escrita.",
            ) from None
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)

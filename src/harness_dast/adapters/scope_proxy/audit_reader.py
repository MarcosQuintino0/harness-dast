"""Leitura da trilha de auditoria do proxy de escopo (`audit.jsonl`, implementa `ProxyAudit`)."""

import json
from pathlib import Path

from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.traffic import ProxyRow


class FileProxyAudit:
    """Lê a trilha do proxy no sistema de arquivos."""

    def __init__(self, path: Path) -> None:
        """Cria a leitura.

        Args:
            path: Caminho do `audit.jsonl` do proxy.
        """
        self._path = path

    def rows(self) -> tuple[ProxyRow, ...]:
        """Linhas da trilha, em ordem; vazio se o arquivo não existe.

        Raises:
            ConfigError: O arquivo não pôde ser lido ou tem linha fora do formato.
        """
        if not self._path.exists():
            return ()
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
            return tuple(_row(line) for line in lines if line.strip())
        except (OSError, ValueError, KeyError, TypeError, ValidationError):
            raise ConfigError(
                "A trilha de auditoria do proxy está ilegível.",
                hint="Confira o arquivo indicado por hdast stack status.",
            ) from None


def _row(line: str) -> ProxyRow:
    raw = json.loads(line)
    return ProxyRow.model_validate(
        {
            "at": raw["ts"],
            "decision": raw["decision"],
            "reason": raw["reason"],
            "method": raw["method"],
        }
    )

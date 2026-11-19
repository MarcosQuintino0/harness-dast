"""Leitura do JSONL do Nuclei pela projeção por lista branca do domínio (ADR 0122).

O que garante: cada linha passa por `parse_nuclei_jsonl`, que só conserva os metadados permitidos
(`curl-command`, `request`, `response` e `extracted-results` nunca saem daqui; do valor extraído
ficam a contagem e o tamanho). Linha malformada, grande demais ou que não é UTF-8 vira contagem de
erro, sem derrubar a leitura. Nunca registra em log o conteúdo de uma linha: só totais.
O que não faz: não decide gravidade nem agrupa achados (isso é de `domain/nuclei_findings.py`).
"""

from pathlib import Path
from typing import BinaryIO, Final

import structlog

from harness_dast.application.nuclei_ports import NucleiParsedOutput
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.nuclei_findings import NucleiResultRecord, parse_nuclei_jsonl

__all__ = ["MAX_LINE_BYTES", "NucleiJsonlReader"]

MAX_LINE_BYTES: Final = 1024 * 1024
"""Maior linha aceita; uma resposta enorme embutida numa linha conta como malformada."""
_log = structlog.get_logger()


class NucleiJsonlReader:
    """Implementa `NucleiOutputReader` (veja o docstring do módulo)."""

    def read(self, raw_jsonl: Path) -> NucleiParsedOutput:
        """Lê o arquivo linha a linha e devolve os registros projetados e a contagem de erros.

        Raises:
            ExternalToolError: O arquivo não pôde ser aberto ou lido.
        """
        records: list[NucleiResultRecord] = []
        malformed = 0
        try:
            with raw_jsonl.open("rb") as handle:
                while True:
                    line = handle.readline(MAX_LINE_BYTES + 1)
                    if not line:
                        break
                    if len(line) > MAX_LINE_BYTES and not line.endswith(b"\n"):
                        _discard_rest_of_line(handle)
                        malformed += 1
                        continue
                    if not line.strip():
                        continue
                    record = _project(line)
                    if record is None:
                        malformed += 1
                    else:
                        records.append(record)
        except OSError:
            raise ExternalToolError(
                "Não consegui ler a saída do Nuclei.",
                hint="Rode de novo; a saída bruta é temporária e é descartada a cada execução.",
            ) from None
        _log.info("nuclei.jsonl.read", records=len(records), malformed=malformed)
        return NucleiParsedOutput(records=tuple(records), malformed=malformed)


def _discard_rest_of_line(handle: BinaryIO) -> None:
    while True:
        chunk = handle.readline(MAX_LINE_BYTES)
        if not chunk or chunk.endswith(b"\n"):
            return


def _project(line: bytes) -> NucleiResultRecord | None:
    try:
        text = line.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    try:
        return parse_nuclei_jsonl(text)
    except ExternalToolError:
        return None

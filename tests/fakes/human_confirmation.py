"""Cenário local para testes de confirmação humana."""

from datetime import UTC, datetime
from pathlib import Path

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.storage.human_confirmation_store import FileHumanConfirmationStore
from harness_dast.application.human_confirmation import AcknowledgeFinding
from harness_dast.domain.human_confirmation import HumanConfirmation, HumanConfirmations
from harness_dast.domain.report.model import FindingsReport
from tests.fakes.human_report import RUN_ID, findings_report


class Clock:
    def now(self) -> datetime:
        return datetime(2026, 11, 16, tzinfo=UTC)


class Prompt:
    def __init__(self, answer: tuple[str, str] | None) -> None:
        self.answer = answer

    def ask(self, fingerprint: str) -> tuple[str, str] | None:
        return self.answer


class MemoryConfirmations:
    """Armazém aditivo isolado por produto e execução."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], HumanConfirmations] = {}

    def read(self, product: str, run_id: str) -> HumanConfirmations | None:
        return self.records.get((product, run_id))

    def append(self, product: str, run_id: str, entry: HumanConfirmation) -> None:
        previous = self.read(product, run_id)
        entries = previous.entries if previous else ()
        self.records[product, run_id] = HumanConfirmations(
            schema_version=1, product=product, run_id=run_id, entries=(*entries, entry)
        )


class MemoryFindings:
    """Leitor de um relatório sintético imutável."""

    def __init__(self, report: FindingsReport) -> None:
        self.report = report

    def read_findings(self, run_id: str) -> FindingsReport:
        return self.report


def setup_memory(
    answer: tuple[str, str] | None,
) -> tuple[AcknowledgeFinding, MemoryConfirmations, FindingsReport]:
    report = findings_report()
    store = MemoryConfirmations()
    case = AcknowledgeFinding(
        store,
        MemoryFindings(report),
        Prompt(answer),
        Clock(),
        lambda text: text.replace("senha-conhecida", "***"),
    )
    return case, store, report


def setup_case(tmp_path: Path, answer: tuple[str, str] | None) -> tuple[AcknowledgeFinding, str]:
    folder = tmp_path / RUN_ID
    folder.mkdir()
    report = findings_report()
    (folder / "findings.json").write_text(report.model_dump_json(), encoding="utf-8")
    case = AcknowledgeFinding(
        FileHumanConfirmationStore(tmp_path),
        FileRunArtifacts(tmp_path),
        Prompt(answer),
        Clock(),
        lambda text: text.replace("senha-conhecida", "***"),
    )
    return case, report.findings[0].fingerprint

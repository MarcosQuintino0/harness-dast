"""Caso de uso de confirmação humana com colaboradores em memória."""

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding_confidence import confidence_step
from tests.fakes.human_confirmation import setup_memory
from tests.fakes.human_report import RUN_ID


def test_registra_sem_perder_anterior_e_redige_observacao() -> None:
    case, store, report = setup_memory(("Ana", "token=abc123 senha-conhecida"))
    fingerprint = report.findings[0].fingerprint
    original = report.model_dump()
    assert case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    assert case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    result = store.read("vampi", RUN_ID)
    assert result is not None
    assert len(result.entries) == 2
    assert result.entries[0].observation == "token=*** ***"
    assert (
        confidence_step(report.findings[0], confirmed_by_person=result.contains(fingerprint))
        == "confirmada"
    )
    assert report.model_dump() == original


def test_nao_grava_quando_cancelado() -> None:
    case, store, report = setup_memory(None)
    fingerprint = report.findings[0].fingerprint
    assert not case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    assert store.read("vampi", RUN_ID) is None


@pytest.mark.parametrize("answer", [("", "vi"), ("Ana", "  "), (" ", "vi")])
def test_recusa_declaracao_ausente(answer: tuple[str, str]) -> None:
    case, store, report = setup_memory(answer)
    fingerprint = report.findings[0].fingerprint
    with pytest.raises(ConfigError):
        case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    assert store.read("vampi", RUN_ID) is None


@pytest.mark.parametrize(
    ("product", "run_id", "fingerprint", "interactive"),
    [
        ("vampi", RUN_ID, "f" * 64, True),
        ("outro", RUN_ID, "f" * 64, True),
        ("vampi", "../invalido", "f" * 64, True),
        ("vampi", RUN_ID, "f" * 64, False),
    ],
)
def test_recusa_contexto_ou_terminal_invalido(
    product: str, run_id: str, fingerprint: str, interactive: bool
) -> None:
    case, store, _ = setup_memory(("Ana", "vi"))
    with pytest.raises(ConfigError):
        case.execute(product, run_id, fingerprint, interactive=interactive)
    assert store.read("vampi", RUN_ID) is None

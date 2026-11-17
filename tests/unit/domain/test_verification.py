"""Regras puras da verificação."""

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import Finding
from harness_dast.domain.verification import classify_finding, parse_verification
from tests.fakes.verification_data import FP, envelope, finding


def test_classifica_com_prova_guardada_sem_alterar_achado() -> None:
    item = finding()
    before = item.model_dump()
    assert classify_finding(item).level == "likely"
    assert item.model_dump() == before


@pytest.mark.parametrize("item", [finding(proof=""), finding(available=False), finding(false=True)])
def test_nao_inventa_prova_contraria_quando_falta_prova_ou_zap_suspeita(item: Finding) -> None:
    assert classify_finding(item).level == "not_verifiable"


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"schema_version": True},
        {"product": "outro"},
        {"run_id": "../segredo"},
        {"entries": [{"fingerprint": FP, "level": "likely"}]},
        {
            "entries": [
                {"fingerprint": FP, "level": "reproduced", "reason": "ok", "severity": "low"}
            ]
        },
        {"entries": [{"fingerprint": FP, "level": "likely", "reason": "ok"}] * 2},
        {"entries": [{"fingerprint": "segredo", "level": "likely", "reason": "ok"}]},
    ],
)
def test_envelope_invalido_falha_sem_expor_valores(change: dict[str, object]) -> None:
    data = envelope() | change
    with pytest.raises(ConfigError) as error:
        parse_verification(data)
    assert "segredo" not in str(error.value)


def test_campo_ausente_falha_fechado() -> None:
    data = envelope()
    del data["entries"]
    with pytest.raises(ConfigError):
        parse_verification(data)

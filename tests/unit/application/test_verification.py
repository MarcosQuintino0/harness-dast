"""Caso de uso da verificação offline."""

from harness_dast.application.verification import verify_offline
from tests.fakes.verification_data import RUN, finding


def test_caso_de_uso_gera_envelope_sem_reproducao() -> None:
    result = verify_offline("produto", RUN, [finding()])
    assert result.schema_version == 1
    assert result.entries[0].level == "likely"

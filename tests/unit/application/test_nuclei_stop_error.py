"""`nuclei_stop_error`: cada parada do estágio vira o código de saída certo; achado não é erro."""

import pytest

from harness_dast.application.run_support import KILL_SWITCH_MESSAGE
from harness_dast.application.stage_errors import nuclei_stop_error
from harness_dast.domain.errors import ExitCode
from harness_dast.domain.nuclei_result import NucleiStatus
from tests.fakes.nuclei import nuclei_finding, nuclei_result


def test_estagio_completo_nao_tem_erro_mesmo_com_achados() -> None:
    result = nuclei_result(findings=(nuclei_finding(severity="high"),))

    assert nuclei_stop_error(result) is None


@pytest.mark.parametrize("status", ["stopped_window", "stopped_deadline"])
def test_janela_e_prazo_sao_escopo_com_a_mensagem_da_parada(status: NucleiStatus) -> None:
    error = nuclei_stop_error(nuclei_result(status, message="parou aqui"))

    assert error is not None
    assert error.exit_code == ExitCode.SCOPE
    assert error.message == "parou aqui"
    assert error.hint is not None
    assert "nuclei.json" in error.hint


def test_trava_de_emergencia_e_escopo_com_a_mensagem_padrao_da_trava() -> None:
    error = nuclei_stop_error(nuclei_result("stopped_kill", message="Contêiner derrubado."))

    assert error is not None
    assert error.exit_code == ExitCode.SCOPE
    assert error.message == KILL_SWITCH_MESSAGE

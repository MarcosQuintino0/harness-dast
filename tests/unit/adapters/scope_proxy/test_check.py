import json
from pathlib import Path

import pytest

from harness_dast.adapters.scope_proxy.check import main
from harness_dast.domain.errors import ExitCode
from tests.unit.adapters.scope_proxy.helpers import policy_data


def test_check_recusa_politica_ausente_mesmo_com_outra_politica_valida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "policy.json").write_text(json.dumps(policy_data()), encoding="utf-8")

    result = main([str(tmp_path / "secondary.json")])

    assert result == ExitCode.SCOPE
    assert "RECUSANDO INICIAR" in capsys.readouterr().err


def test_check_recusa_politica_sem_permissoes_em_vez_de_assumir_um_escopo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(policy_data(scope={"allow": []})), encoding="utf-8")

    result = main([str(policy)])

    assert result == ExitCode.SCOPE
    assert "scope.allow" in capsys.readouterr().err

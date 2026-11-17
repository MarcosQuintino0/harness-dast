"""Contrato da CLI de confirmação com portas locais e armazenamento temporário."""

import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ExitCode
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.confirmation_rig import ConfirmationRig, confirmation_target


class LocalNetwork:
    """Ciclo de vida local sem conexões."""

    def close(self) -> None:
        """Não há conexões a fechar."""


@pytest.mark.parametrize("interrupt", [False, True])
def test_cli_preserva_codigo_e_arquivo_parcial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    interrupt: bool,
) -> None:
    import harness_dast.cli.commands.confirm as command

    def handle(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if interrupt and request.operation_id.startswith("confirm:"):
            raise KeyboardInterrupt
        return confirmation_target(request, jar)

    rig = ConfirmationRig(tmp_path, stopped=not interrupt, handler=handle)
    monkeypatch.setattr(command, "hold_stack", lambda *args: nullcontext())
    monkeypatch.setattr(command, "open_network", lambda *args: LocalNetwork())
    monkeypatch.setattr(command, "build_confirmation", lambda *args: rig.service())
    code = run_app(build_app(), ["--json", "confirm", "agenda", "--run", rig.run_id])
    output = json.loads(capsys.readouterr().out)
    assert code == (ExitCode.INTERRUPTED if interrupt else ExitCode.SCOPE)
    assert output["ok"] is False
    assert rig.store.read().entries[0].level == "inconclusive"

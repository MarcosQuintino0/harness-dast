"""Contrato da CLI de confirmação sem terminal, Docker ou rede real."""

import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.commands import confirm
from harness_dast.domain.scan_binding import bind_scan_seed
from tests.fakes.confirmation_rig import ConfirmationRig


class NetworkStub:
    """Recurso de rede cujo fechamento é observável sem rede."""

    def close(self) -> None:
        """Não há conexão a encerrar."""


def test_confirm_emite_envelope_e_grava_verificacao_sem_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rig = ConfirmationRig(tmp_path)
    service = rig.service()
    monkeypatch.setattr(confirm, "hold_stack", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(confirm, "open_network", lambda *args: NetworkStub())
    monkeypatch.setattr(confirm, "build_confirmation", lambda *args: service)
    code = run_app(build_app(), ["--json", "confirm", "agenda", "--run", rig.run_id, "--max", "1"])
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["data"]["verification"]["entries"][0]["level"] == "reproduced"
    assert result["data"]["recipe_requests"] == 5
    assert result["data"]["session_requests"] >= 1


@pytest.mark.parametrize("mode", ["max", "fingerprint", "stop", "product", "scope"])
def test_confirm_recusa_sem_terminal_e_sem_pedido_indevido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], mode: str
) -> None:
    rig = ConfirmationRig(tmp_path, stopped=mode == "stop")
    if mode == "product":
        report = rig.rig.artifacts.findings[rig.run_id]
        rig.rig.artifacts.findings[rig.run_id] = report.model_copy(update={"product": "outro"})
    if mode == "scope":
        log = rig.rig.store.exchanges[rig.run_id]
        seed = log.exchanges[0].model_copy(update={"path": "/fora", "target": "/fora?q=x"})
        rig.rig.store.exchanges[rig.run_id] = log.model_copy(update={"exchanges": (seed,)})
        scan = rig.rig.artifacts.scans[rig.run_id]
        base = rig.rig.profiles.load("agenda").environment.base_url
        binding = bind_scan_seed("listar", "GET", base + "/fora?q=x", "user_a")
        rig.rig.artifacts.scans[rig.run_id] = scan.model_copy(
            update={
                "entries": (
                    scan.entries[0].model_copy(update={"path": "/fora", "seed_binding": binding}),
                )
            }
        )
        report = rig.rig.artifacts.findings[rig.run_id]
        rig.rig.artifacts.findings[rig.run_id] = report.model_copy(
            update={"findings": (report.findings[0].model_copy(update={"path_template": "/fora"}),)}
        )
    monkeypatch.setattr(confirm, "hold_stack", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(confirm, "open_network", lambda *args: NetworkStub())
    monkeypatch.setattr(confirm, "build_confirmation", lambda *args: rig.service())
    options = ["--max", "31"] if mode == "max" else []
    if mode == "fingerprint":
        options = ["--finding", "a" * 63]
    before = len(rig.rig.target.requests)
    code = run_app(build_app(), ["--json", "confirm", "agenda", "--run", rig.run_id, *options])
    output = json.loads(capsys.readouterr().out)
    assert code != 0
    assert output["ok"] is False
    assert len(rig.rig.target.requests) == before

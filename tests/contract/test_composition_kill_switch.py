"""A montagem real liga a MESMA trava de emergência ao preflight, ao probe, ao scan e ao run.

Os testes de contrato do `run` trocam a montagem por um falso; sem este teste, remover
`kill_switch=...` da composição não quebraria a suíte rápida (só a integração com o lab pegaria).
Aqui a montagem é a de produção, sobre uma pasta de política temporária: ao criar o arquivo
`KILL` (o que `hdast stop` faz), todas as etapas e o encadeamento enxergam a trava.
"""

from pathlib import Path
from typing import Any

import pytest

from harness_dast.cli.scan_composition import build_run_pipeline, open_scan_network
from harness_dast.observability.logging import SecretRegistry
from tests.contract.test_cli_probe_commands import (
    _env,  # noqa: F401 - fixture autouse do módulo do probe
    environment,
)


def test_build_run_pipeline_wires_the_same_kill_switch_into_every_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    policy = tmp_path / "politica"
    policy.mkdir()
    monkeypatch.setenv("HDAST_SCOPE_POLICY_DIR", str(policy))
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path / "estado"))
    with environment(monkeypatch, tmp_path) as (_, products):
        secrets = SecretRegistry()
        net = open_scan_network("demo", products, secrets)
        try:
            pipeline = build_run_pipeline("demo", products, secrets, net)
            # Os atributos privados são lidos de propósito: a ligação é o que se quer provar.
            stages: list[Any] = list(pipeline._stages)[:3]  # preflight, probe e scan
            switches = [pipeline._kill, *(stage._kill_switch for stage in stages)]
            assert [switch.engaged() for switch in switches] == [False] * 4

            (policy / "KILL").touch()

            assert [switch.engaged() for switch in switches] == [True] * 4
        finally:
            net.network.close()

"""V1.9.1: pilha desatualizada depois de editar o perfil (ADR 0081), contra a pilha real.

Cenário das rodadas cegas da V1.9: a pilha sobe com `auth.request_encoding: form` (o alvo só
aceita JSON), o agente corrige o campo livre com a pilha de pé e, sem a conferência, tudo
virava 403 `approval_changed` sem explicação. Aqui a conferência recusa antes de qualquer pedido,
a recriação da pilha cura e o `preflight` passa. Exige Docker e a trava do laboratório.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from tests.integration.lab_support import PILOT_PROFILE, LabCli, proxy_audit, require_docker
from tests.integration.run_support import throwaway_pilot_env

pytestmark = pytest.mark.integration

PRODUCT = "clinica-piloto"
STACK_STALE_EXIT = 4


def _set_encoding(cli: LabCli, value: str) -> None:
    target = cli.products / PRODUCT / "target.yml"
    profile = yaml.safe_load(target.read_text(encoding="utf-8"))
    profile["auth"]["request_encoding"] = value
    target.write_text(
        yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


@pytest.fixture
def cli(tmp_path: Path) -> Iterator[LabCli]:
    require_docker()
    lab = LabCli(tmp_path, throwaway_pilot_env())
    lab.install_product(PRODUCT, PILOT_PROFILE)
    _set_encoding(lab, "form")
    try:
        yield lab
    finally:
        lab.stack_down()


def test_editar_campo_livre_com_a_pilha_de_pe_falha_antes_do_primeiro_pedido_e_recriar_cura(
    cli: LabCli,
) -> None:
    up = cli.stack_up(PRODUCT, timeout=600)
    assert up.code == 0, up.stdout[-500:]
    fresh = cli.run("stack", "status")
    assert fresh.data["binding"] == "fresh"
    audit_before = len(proxy_audit(cli))

    _set_encoding(cli, "json")  # campo livre: a aprovação não muda
    approval = cli.run("profile", "approval", PRODUCT)
    assert approval.data["state"] == "approved"
    assert approval.data["changed_blocks"] == []

    stale = cli.run("stack", "status")
    assert stale.data["binding"] == "stale"
    assert stale.data["stale_parts"] == ["profile"]
    refused = cli.run("preflight", PRODUCT)

    assert refused.code == STACK_STALE_EXIT, refused.stdout[-500:]
    assert refused.envelope["ok"] is False
    error = refused.envelope["error"]
    assert error["code"] == "STACK_STALE"
    assert "hdast stack down" in error["hint"]
    assert f"hdast stack up {PRODUCT}" in error["hint"]
    assert len(proxy_audit(cli)) == audit_before, "a conferência não pode gerar tráfego ao alvo"
    assert not any(cli.runs.iterdir()), "nada foi tentado: nenhuma execução foi aberta"

    assert cli.run("stack", "down", timeout=240).code == 0
    assert cli.stack_up(PRODUCT, timeout=600).code == 0
    assert cli.run("stack", "status").data["binding"] == "fresh"
    ready = cli.run("preflight", PRODUCT)

    assert ready.code == 0, ready.stdout[-800:]
    assert ready.data["ready"] is True

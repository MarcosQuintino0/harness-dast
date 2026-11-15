"""Prova dirigida da declaração de papéis compartilhados na Clínica Piloto descartável."""

import json
from collections.abc import Iterator
from typing import Any

import pytest

from tests.integration.lab_support import PILOT_PROFILE, LabCli, require_docker
from tests.integration.run_support import throwaway_pilot_env

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]


@pytest.fixture(scope="module", params=("secure", "vulnerable"))
def shared_roles_qa(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Executa probe e authz nos dois modos, com perfil e aprovação descartáveis."""
    require_docker()
    mode = str(request.param)
    cli = LabCli(tmp_path_factory.mktemp(f"shared-roles-{mode}"), throwaway_pilot_env())
    profile = cli.install_product("clinica-piloto", PILOT_PROFILE) / "target.yml"
    original = profile.read_text(encoding="utf-8")
    marker = "  role_order: [paciente, medico, admin]"
    assert marker in original
    profile.write_text(
        original.replace(marker, marker + "\n  allow_writes: true\n  shared_roles: [medico]"),
        encoding="utf-8",
    )
    try:
        flags = ["--build", "--secure"] if mode == "secure" else ["--build"]
        assert cli.run("stack", "up", "clinica-piloto", *flags, timeout=600).code == 0
        assert cli.run("preflight", "clinica-piloto").code == 0
        probe = cli.run("probe", "clinica-piloto", timeout=900)
        assert probe.code == 0, probe.stdout[-500:]
        run_id = str(probe.envelope["run_id"])
        result = cli.run("authz", "clinica-piloto", "--run", run_id, timeout=1500)
        assert result.code == 0, result.stdout[-800:]
        authz = json.loads((cli.runs / run_id / "authz.json").read_text(encoding="utf-8"))
        yield mode, authz
    finally:
        cli.stack_down()


def test_medicos_compartilhados_nao_produzem_achados_horizontais(
    shared_roles_qa: tuple[str, dict[str, Any]],
) -> None:
    _, authz = shared_roles_qa
    assert not [
        finding
        for finding in authz["findings"]
        if finding["technique"] in {"authz_horizontal", "authz_horizontal_write"}
        and finding["actor_role"] == finding["owner_role"] == "medico"
    ]


@pytest.mark.parametrize(
    ("check", "operation"),
    [("horizontal", "buscarPaciente"), ("horizontal_write", "atualizarPaciente")],
)
def test_operacao_de_medico_registra_motivo_compartilhado(
    shared_roles_qa: tuple[str, dict[str, Any]], check: str, operation: str
) -> None:
    _, authz = shared_roles_qa
    assert any(
        note["check"] == check
        and note["operation_id"] == operation
        and note["reason"] == "shared_role"
        for note in authz["not_tested"]
    )


def test_bola_entre_pacientes_permanece_detectavel_no_modo_vulneravel(
    shared_roles_qa: tuple[str, dict[str, Any]],
) -> None:
    mode, authz = shared_roles_qa
    if mode != "vulnerable":
        pytest.skip("o controle positivo exige o modo vulnerável")
    assert any(
        finding["technique"] == "authz_horizontal"
        and finding["operation_id"] == "buscarConsulta"
        and finding["actor_role"] == finding["owner_role"] == "paciente"
        and finding["actor_account"] != finding["owner_account"]
        for finding in authz["findings"]
    )

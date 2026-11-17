"""Cenários adversos da criação automática de pares."""

from harness_dast.domain.profile import ProductProfile
from tests.fakes.authz.rig import clinic_profile_data
from tests.unit.application.authz.test_created_pair import execute, make_rig


def test_cerca_recusa_leitura_criada_em_caminho_negado() -> None:
    rig = make_rig("api/widgets", exposed=True)
    data = clinic_profile_data(allow_writes=True)
    data["scope"]["deny_paths"].append("/api/widgets/*")
    rig.profile = ProductProfile.from_data(data)
    rig.profiles.add(rig.profile, existing_files={rig.profile.openapi})

    result = execute(rig, "api/widgets")

    assert not any(r.operation_id.startswith("authz:pair:") for r in rig.target.requests)
    assert not result.findings
    assert any(n.reason == "scope_denied" for n in result.not_tested)

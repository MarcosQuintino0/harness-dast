"""Regressoes independentes da aprovacao de papeis compartilhados."""

import pytest

from harness_dast.domain.errors import ScopeNotApproved
from tests.fakes.approvals import approve_profile
from tests.fakes.profile_data import valid_profile, valid_profile_data
from tests.unit.application.test_scope_approval import Rig


def test_alteracao_de_papel_compartilhado_invalida_aprovacao() -> None:
    rig = Rig()
    approve_profile(rig.store, valid_profile())
    role = valid_profile_data()["auth"]["accounts"][0]["role"]
    rig.edit_profile(lambda data: data.update(authz={"shared_roles": [role]}))

    with pytest.raises(ScopeNotApproved) as caught:
        rig.guarded.load("demo")

    assert caught.value.state == "changed"
    assert caught.value.changed_blocks == ("authz",)


def test_resumo_mostra_papel_compartilhado_antes_da_aprovacao() -> None:
    rig = Rig()
    role = valid_profile_data()["auth"]["accounts"][0]["role"]
    rig.edit_profile(lambda data: data.update(authz={"shared_roles": [role]}))

    rig.use_case.approve("demo", interactive=True)

    summary = rig.prompt.shown[0][1]
    assert any("compartilhados" in line and role in line for line in summary)

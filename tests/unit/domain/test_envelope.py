"""O envelope reflete o perfil e nunca substitui a aprovação."""

import pytest

from harness_dast.domain.envelope import describe_envelope, require_approved_envelope
from harness_dast.domain.errors import ScopeNotApproved
from tests.fakes.approvals import approval_for
from tests.fakes.profile_data import valid_profile


def test_envelope_reflete_perfil_e_aprovacao() -> None:
    profile = valid_profile()
    approval = approval_for(profile)

    envelope = require_approved_envelope(profile, approval)

    assert envelope.approval_digest == approval.digest
    assert envelope.requests_per_second == profile.limits.requests_per_second


def test_previa_nao_concede_aprovacao() -> None:
    profile = valid_profile()

    assert describe_envelope(profile).product == profile.product
    with pytest.raises(ScopeNotApproved):
        require_approved_envelope(profile, None)


def test_aprovacao_de_outro_produto_nao_autoriza_envelope() -> None:
    with pytest.raises(ScopeNotApproved):
        require_approved_envelope(valid_profile(), approval_for(valid_profile("outro")))

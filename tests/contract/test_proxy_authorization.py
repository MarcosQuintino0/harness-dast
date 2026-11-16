"""Compatibilidade da aprovação anterior com a escolha de ritmo."""

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_approval import check_approval
from tests.fakes.approvals import approval_for
from tests.fakes.profile_data import valid_profile_data


def test_aprovacao_legada_nao_autoriza_ritmo_proxy() -> None:
    data = valid_profile_data()
    legacy = ProductProfile.from_data(data)
    approval = approval_for(legacy)

    data.setdefault("scan", {})["pacing"] = "proxy"
    proxy = ProductProfile.from_data(data)

    assert legacy.scan.pacing == "legacy"
    assert check_approval(legacy, approval).state == "approved"
    assert check_approval(proxy, approval).state == "changed"
    assert check_approval(proxy, approval_for(proxy)).state == "approved"

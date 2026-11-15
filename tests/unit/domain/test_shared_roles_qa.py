"""Regressoes independentes da aprovacao de papeis compartilhados."""

import copy

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_fingerprint import block_digests
from tests.fakes.profile_data import valid_profile_data


def test_reordenacao_dos_papeis_nao_invalida_aprovacao() -> None:
    data = valid_profile_data()
    account = copy.deepcopy(data["auth"]["accounts"][0])
    account["alias"] = "outro"
    account["role"] = "outro"
    data["auth"]["accounts"].append(account)
    original_role = data["auth"]["accounts"][0]["role"]
    data["authz"] = {"shared_roles": [original_role, "outro"]}
    first = block_digests(ProductProfile.from_data(data))
    data["authz"]["shared_roles"].reverse()
    assert block_digests(ProductProfile.from_data(data)) == first

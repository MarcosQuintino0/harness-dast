"""Contrato entre `products/_template/target.yml` e os modelos de `domain/profile.py`.

Existe para que o modelo de perfil e o domínio nunca mais divirjam em silêncio (QA A-02).
"""

from pathlib import Path

import pytest
import yaml

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile

pytestmark = pytest.mark.contract

TEMPLATE = Path(__file__).parents[2] / "products" / "_template" / "target.yml"


def _load_template() -> dict[str, object]:
    loaded = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_template_target_yml_is_accepted_by_the_domain_model_when_loaded_as_is() -> None:
    profile = ProductProfile.from_data(_load_template())

    assert profile.auth.type == "login_password"


def test_template_api_key_variant_is_accepted_by_the_domain_model() -> None:
    data = _load_template()
    data["auth"] = {
        "type": "api_key",
        "header_name": "X-API-Key",
        "accounts": [
            {
                "alias": "svc_a",
                "role": "servico",
                "api_key": {"secret_ref": "env:MEU_PRODUTO_SVC_A_CHAVE"},
            }
        ],
    }

    assert ProductProfile.from_data(data).auth.type == "api_key"


def test_template_is_rejected_when_the_old_auth_type_name_is_used() -> None:
    data = _load_template()
    auth = data["auth"]
    assert isinstance(auth, dict)
    auth["type"] = "oauth2_password"

    with pytest.raises(ConfigError):
        ProductProfile.from_data(data)

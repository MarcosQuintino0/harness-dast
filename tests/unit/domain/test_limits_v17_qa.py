"""Bordas adversariais do ritmo temporário e das declarações consultivas."""

from datetime import UTC, datetime

import pytest

from harness_dast.adapters.scope_proxy.ratelimit import RateLimiter
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.retry_after import retry_after_seconds
from harness_dast.domain.scan_policy import build_policy
from harness_dast.domain.scope_fingerprint import block_digests
from tests.fakes.profile_data import valid_profile_data


@pytest.mark.parametrize("value", ["61", "9999", "+1", "1.0", "NaN", "1\n2", "\uff11", "9" * 101])
def test_retry_after_invalido_nao_cria_recuo(value: str) -> None:
    assert retry_after_seconds(value, datetime(2026, 1, 1, tzinfo=UTC)) is None


def test_retry_after_limite_superior_aceito_e_posterior_recusado() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert retry_after_seconds("60", now) == 60
    assert retry_after_seconds("61", now) is None


def test_recuo_nao_reduz_recuo_anterior_nem_aumenta_taxa() -> None:
    clock = [100.0]
    limiter = RateLimiter(requests_per_second=2, max_queued=3, monotonic=lambda: clock[0])
    limiter.defer(60)
    limiter.defer(1)
    assert limiter.delay_until_grant() == 60
    clock[0] = 160
    limiter.grant()
    assert limiter.delay_until_grant() == 0.5


def test_tecnologia_declarada_nunca_exclui_regra_da_politica() -> None:
    data = valid_profile_data()
    baseline = ProductProfile.from_data(data)
    data["technologies"] = {"value": ["oracle"], "source": "carta", "quote": "Banco Oracle."}
    declared = ProductProfile.from_data(data)
    assert build_policy(declared.scan) == build_policy(baseline.scan)


def test_ordem_das_tecnologias_nao_altera_impressao() -> None:
    data = valid_profile_data()
    data["technologies"] = {
        "value": ["postgresql", "nginx"],
        "source": "carta",
        "quote": "Tecnologias declaradas.",
    }
    first = ProductProfile.from_data(data)
    data["technologies"]["value"] = ["nginx", "postgresql"]
    second = ProductProfile.from_data(data)
    assert block_digests(first) == block_digests(second)


@pytest.mark.parametrize("value", [["oracle", "oracle"], ["ora\ncle"], ["a" * 65], [""]])
def test_perfil_recusa_nomes_de_tecnologia_malformados(value: list[str]) -> None:
    data = valid_profile_data()
    data["technologies"] = {"value": value, "source": "carta", "quote": "Banco declarado."}
    with pytest.raises(ConfigError):
        ProductProfile.from_data(data)

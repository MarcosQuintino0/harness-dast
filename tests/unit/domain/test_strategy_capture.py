"""A captura depende de aprovação e fontes atuais e só propõe cobertura neutra."""

from datetime import UTC, datetime

import pytest

from harness_dast.domain.errors import ConfigError, ScopeNotApproved, ScopeViolation
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.strategy_basis import digest_strategy_document, make_strategy_basis
from harness_dast.domain.strategy_capture import capture_strategy
from tests.fakes.approvals import approval_for
from tests.fakes.profile_data import valid_profile, valid_profile_data

_NOW = datetime(2026, 11, 16, tzinfo=UTC)
_DOC = digest_strategy_document(b"documento")
_SOURCES = dict(
    openapi_sha256=_DOC, data_rules_sha256=_DOC, flows_sha256=_DOC, engine_version="2.17"
)


def test_captura_cria_escolha_neutra_vinculada() -> None:
    profile = valid_profile()
    strategy = capture_strategy(profile, approval_for(profile), _NOW, **_SOURCES)
    choice = strategy.choices[0]
    assert (choice.name, choice.value, choice.source, choice.state) == (
        "coverage",
        "preserve",
        "observation",
        "validated",
    )
    assert choice.valid_until == profile.scope.authorization.valid_until
    strategy.ensure_compilable(_NOW, make_strategy_basis(profile, **_SOURCES))


def test_captura_recusa_sem_aprovacao() -> None:
    with pytest.raises(ScopeNotApproved):
        capture_strategy(valid_profile(), None, _NOW, **_SOURCES)


def test_captura_recusa_autorizacao_vencida() -> None:
    data = valid_profile_data()
    data["scope"]["authorization"]["valid_until"] = "2026-11-15"
    profile = ProductProfile.from_data(data)
    with pytest.raises(ScopeViolation):
        capture_strategy(profile, approval_for(profile), _NOW, **_SOURCES)


@pytest.mark.parametrize("version", [None, "", "a\nsegredo", "a" * 101])
def test_captura_recusa_motor_indisponivel_sem_eco(version: str | None) -> None:
    profile = valid_profile()
    with pytest.raises(ConfigError) as error:
        capture_strategy(
            profile,
            approval_for(profile),
            _NOW,
            openapi_sha256=_DOC,
            data_rules_sha256=_DOC,
            flows_sha256=_DOC,
            engine_version=version,
        )
    assert "segredo" not in str(error.value)


def test_captura_recusa_digest_invalido_sem_eco() -> None:
    profile = valid_profile()
    with pytest.raises(ConfigError) as error:
        capture_strategy(
            profile, approval_for(profile), _NOW, **{**_SOURCES, "openapi_sha256": "segredo"}
        )
    assert "segredo" not in str(error.value)

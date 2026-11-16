"""A estratégia não executa escolha sem vínculo verificável do motor."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.application.strategy import StrategyProfiles
from harness_dast.domain.errors import ConfigError
from tests.fakes.clock import FixedClock
from tests.fakes.profile_data import dump_yaml, valid_profile_data

_HEADER = """schema_version: 1
references:
  target: target.yml
  data_rules: data-rules.yml
  flows: flows.yml
"""


def _profiles(tmp_path: Path, choices: str) -> StrategyProfiles:
    product = tmp_path / "demo"
    product.mkdir()
    (product / "target.yml").write_text(dump_yaml(valid_profile_data()), encoding="utf-8")
    (product / "strategy.yml").write_text(_HEADER + choices, encoding="utf-8")
    return StrategyProfiles(
        FileProfileRepository(tmp_path),
        FileStrategyRepository(tmp_path),
        FixedClock(datetime(2026, 11, 16, tzinfo=UTC)),
    )


def test_perfil_sem_escolhas_nao_exige_ler_contrato(tmp_path: Path) -> None:
    profiles = _profiles(tmp_path, "choices: []\n")

    assert profiles.load("demo").product == "demo"


def test_escolha_sem_motor_comprovado_e_recusada(tmp_path: Path) -> None:
    profiles = _profiles(
        tmp_path,
        """choices:
  - name: coverage
    value: preserve
    source: owner
    reason: preserve_baseline
    valid_until: '2030-01-01'
    state: validated
""",
    )
    (tmp_path / "demo" / "openapi.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ConfigError):
        profiles.load("demo")

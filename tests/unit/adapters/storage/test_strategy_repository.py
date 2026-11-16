"""Contratos de armazenamento local de estratégias."""

from pathlib import Path

import pytest

from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.strategy import Strategy


def test_migracao_cria_copia_neutra_sem_sobrescrever(tmp_path: Path) -> None:
    product = tmp_path / "produto"
    product.mkdir()
    target = product / "target.yml"
    target.write_text("original", encoding="utf-8")
    store = FileStrategyRepository(tmp_path)

    store.migrate("produto", "strategy.migrated.yml")

    assert target.read_text(encoding="utf-8") == "original"
    (product / "strategy.migrated.yml").rename(product / "strategy.yml")
    strategy = Strategy.from_data(store.read("produto"))
    assert strategy.choices == ()


def test_migracao_recusa_destino_existente(tmp_path: Path) -> None:
    product = tmp_path / "produto"
    product.mkdir()
    destination = product / "strategy.migrated.yml"
    destination.write_text("original", encoding="utf-8")
    store = FileStrategyRepository(tmp_path)

    with pytest.raises(ConfigError):
        store.migrate("produto", destination.name)

    assert destination.read_text(encoding="utf-8") == "original"


@pytest.mark.parametrize("name", ["target.yml", "../strategy.copia.yml", "strategy.yml"])
def test_migracao_recusa_destino_inseguro(tmp_path: Path, name: str) -> None:
    (tmp_path / "produto").mkdir()

    with pytest.raises(ConfigError):
        FileStrategyRepository(tmp_path).migrate("produto", name)


def test_leitura_recusa_yaml_com_chave_repetida(tmp_path: Path) -> None:
    product = tmp_path / "produto"
    product.mkdir()
    (product / "strategy.yml").write_text("schema_version: 1\nschema_version: 1\n")

    with pytest.raises(ConfigError):
        FileStrategyRepository(tmp_path).read("produto")

"""Leitura estrita de knowledge.yml, sem eco de conteúdo externo."""

from pathlib import Path

import pytest

from harness_dast.adapters.storage.knowledge_repository import FileKnowledgeStore
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge import Knowledge


def test_ausente_nao_muda_perfil(tmp_path: Path) -> None:
    (tmp_path / "agenda").mkdir()
    assert FileKnowledgeStore(tmp_path).read("agenda") is None


@pytest.mark.parametrize("contents", ["", "[", "entries: []\nentries: [1]\n"])
def test_yaml_malformado_ou_duplicado_recusado(tmp_path: Path, contents: str) -> None:
    folder = tmp_path / "agenda"
    folder.mkdir()
    (folder / "knowledge.yml").write_text(contents, encoding="utf-8")
    with pytest.raises(ConfigError):
        FileKnowledgeStore(tmp_path).read("agenda")


def test_schema_invalido_nao_expoe_valor(tmp_path: Path) -> None:
    folder = tmp_path / "agenda"
    folder.mkdir()
    (folder / "knowledge.yml").write_text("conteudo: sentinela\n", encoding="utf-8")
    with pytest.raises(ConfigError) as error:
        Knowledge.from_data(FileKnowledgeStore(tmp_path).read("agenda"))
    assert "sentinela" not in str(error.value)

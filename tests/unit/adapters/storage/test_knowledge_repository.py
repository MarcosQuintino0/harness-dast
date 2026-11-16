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


def _write_run(root: Path) -> str:
    from harness_dast.application.probe import ProbeRequest
    from tests.fakes.rig import Rig

    rig = Rig()
    result = rig.probe().execute(ProbeRequest(product="agenda", only=("listar",)))
    directory = root / result.run_id
    directory.mkdir()
    (directory / "probe.json").write_text(result.model_dump_json(), encoding="utf-8")
    (directory / "manifest.json").write_text(
        rig.store.manifests[result.run_id][-1].model_dump_json(), encoding="utf-8"
    )
    return result.run_id


def test_run_evidence_le_artefatos_validos_com_hashes(tmp_path: Path) -> None:
    from harness_dast.adapters.storage.knowledge_repository import FileKnowledgeRunStore

    run_id = _write_run(tmp_path)
    evidence = FileKnowledgeRunStore(tmp_path).read(run_id)
    assert evidence.manifest.run_id == evidence.probe.run_id == run_id
    assert len(evidence.provenance.manifest_sha256) == 64
    assert evidence.provenance.authz_sha256 is None


def test_run_evidence_recusa_ausente_ou_malformado(tmp_path: Path) -> None:
    from harness_dast.adapters.storage.knowledge_repository import FileKnowledgeRunStore

    run_id = _write_run(tmp_path)
    reader = FileKnowledgeRunStore(tmp_path)
    (tmp_path / run_id / "probe.json").write_text("{", encoding="utf-8")
    with pytest.raises(ConfigError):
        reader.read(run_id)
    (tmp_path / run_id / "probe.json").unlink()
    with pytest.raises(ConfigError):
        reader.read(run_id)


def test_run_evidence_recusa_identificador_com_travessia(tmp_path: Path) -> None:
    from harness_dast.adapters.storage.knowledge_repository import FileKnowledgeRunStore

    with pytest.raises(ConfigError):
        FileKnowledgeRunStore(tmp_path).read("../fora")

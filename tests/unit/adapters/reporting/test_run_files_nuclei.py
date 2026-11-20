"""`FileRunArtifacts` e o `nuclei.json`: gravação atômica, leitura e arquivo conhecido."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.domain.errors import ConfigError
from tests.fakes.nuclei import RUN_ID, nuclei_finding, nuclei_result


def test_grava_e_le_o_resultado_limpo(tmp_path: Path) -> None:
    store = FileRunArtifacts(tmp_path)
    result = nuclei_result(findings=(nuclei_finding(),))

    store.write_nuclei(RUN_ID, result)

    assert store.read_nuclei(RUN_ID) == result
    assert not list((tmp_path / RUN_ID).glob(".*.tmp"))


def test_le_none_quando_o_estagio_nao_rodou(tmp_path: Path) -> None:
    assert FileRunArtifacts(tmp_path).read_nuclei(RUN_ID) is None


def test_arquivo_gravado_aparece_entre_os_artefatos_da_execucao(tmp_path: Path) -> None:
    store = FileRunArtifacts(tmp_path)

    store.write_nuclei(RUN_ID, nuclei_result())

    assert store.existing_files(RUN_ID)["nuclei.json"] == "nuclei.json"


def test_arquivo_gravado_nao_tem_conteudo_bruto(tmp_path: Path) -> None:
    store = FileRunArtifacts(tmp_path)

    store.write_nuclei(RUN_ID, nuclei_result(findings=(nuclei_finding(),)))

    text = (tmp_path / RUN_ID / "nuclei.json").read_text(encoding="utf-8")
    assert "SEGREDO" not in text
    assert "curl" not in text


def test_arquivo_corrompido_levanta_erro_com_o_comando_a_refazer(tmp_path: Path) -> None:
    directory = tmp_path / RUN_ID
    directory.mkdir()
    (directory / "nuclei.json").write_text(json.dumps({"run_id": 1}), encoding="utf-8")

    with pytest.raises(ConfigError, match=r"nuclei.json"):
        FileRunArtifacts(tmp_path).read_nuclei(RUN_ID)


def test_run_id_invalido_e_recusado(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        FileRunArtifacts(tmp_path).write_nuclei("../fora", nuclei_result())

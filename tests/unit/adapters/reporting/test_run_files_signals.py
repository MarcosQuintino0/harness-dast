"""`error-signals.json` no armazém de artefatos: ida e volta, leitura estrita e conteúdo."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.signal_result import ProxySignals, SignalFinding, SignalWindow
from tests.unit.domain.report_helpers import RUN_ID


@pytest.fixture
def store(tmp_path: Path) -> FileRunArtifacts:
    return FileRunArtifacts(tmp_path)


def run_dir(tmp_path: Path) -> Path:
    directory = tmp_path / RUN_ID
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def signals() -> ProxySignals:
    finding = SignalFinding(
        finding_id="S-0a1b2c3d",
        fingerprint="0a1b2c3d" + "0" * 56,
        category="sql_error",
        title="Possível erro de banco de dados",
        proposed_severity="medium",
        proposed_confidence="medium",
        cwe=209,
        method="GET",
        path_template="/x/{}",
        occurrences=2,
        statuses=(500,),
    )
    return ProxySignals(
        enabled=True,
        window=SignalWindow(start="2026-11-14T12:00:00+00:00", end="2026-11-14T12:10:00+00:00"),
        responses_examined=5,
        responses_skipped={"type": 1},
        responses_with_signal=2,
        counts={"sql_error": 2},
        findings=(finding,),
    )


def test_ida_e_volta_e_o_arquivo_aparece_como_artefato_conhecido(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    store.write_signals(RUN_ID, signals())

    assert store.read_signals(RUN_ID) == signals()
    assert "error-signals.json" in store.existing_files(RUN_ID)
    assert sorted(p.name for p in run_dir(tmp_path).iterdir()) == ["error-signals.json"]


def test_arquivo_ausente_significa_que_o_report_ainda_nao_o_gravou(store: FileRunArtifacts) -> None:
    run_dir(store._runs_dir)

    assert store.read_signals(RUN_ID) is None


@pytest.mark.parametrize(
    "content",
    ["{", "[]", '{"enabled": "talvez"}', '{"enabled": true, "findings": "x"}', '{"extra": 1}'],
)
def test_arquivo_ilegivel_ou_fora_do_formato_vira_config_error(
    tmp_path: Path, store: FileRunArtifacts, content: str
) -> None:
    (run_dir(tmp_path) / "error-signals.json").write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError, match=r"error-signals\.json"):
        store.read_signals(RUN_ID)


def test_arquivo_gravado_so_tem_categorias_e_nomes_nunca_texto_de_corpo(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    store.write_signals(RUN_ID, signals())

    data = json.loads((run_dir(tmp_path) / "error-signals.json").read_text(encoding="utf-8"))

    assert data["findings"][0]["category"] == "sql_error"
    assert "ORA-" not in json.dumps(data)
    assert set(data["findings"][0]) <= set(SignalFinding.model_fields)

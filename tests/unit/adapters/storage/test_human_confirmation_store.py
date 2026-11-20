"""Persistência de confirmação humana em arquivos locais."""

from pathlib import Path

import pytest

from harness_dast.domain.errors import ConfigError
from tests.fakes.human_confirmation import setup_case
from tests.fakes.human_report import RUN_ID


@pytest.mark.parametrize(
    "contents",
    [
        "{",
        "{}",
        "null",
        '{"schema_version":1,"schema_version":1}',
        '{"schema_version":true,"product":"vampi","run_id":"' + RUN_ID + '","entries":[]}',
        '{"schema_version":2}',
        '{"schema_version":1,"product":"outro","run_id":"' + RUN_ID + '","entries":[]}',
    ],
)
def test_recusa_arquivo_malformado_sem_apagar(tmp_path: Path, contents: str) -> None:
    case, fingerprint = setup_case(tmp_path, ("Ana", "vi"))
    path = tmp_path / RUN_ID / "human-confirmations.json"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ConfigError) as error:
        case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    assert contents not in str(error.value)
    assert path.read_text(encoding="utf-8") == contents


def test_trava_concorrente_preserva_registros(tmp_path: Path) -> None:
    case, fingerprint = setup_case(tmp_path, ("Ana", "vi"))
    original = (tmp_path / RUN_ID / "findings.json").read_bytes()
    assert case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    folder = tmp_path / RUN_ID
    before = (folder / "human-confirmations.json").read_bytes()
    (folder / ".human-confirmations.lock").touch()
    with pytest.raises(ConfigError):
        case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    assert (folder / "human-confirmations.json").read_bytes() == before
    assert (folder / "findings.json").read_bytes() == original

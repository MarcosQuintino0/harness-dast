"""Armazenamento da verificação."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.storage.verification_store import VerificationStore
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.verification import parse_verification
from tests.fakes.verification_data import FP, envelope


def test_arquivo_ausente_ou_malformado_falha_fechado(tmp_path: Path) -> None:
    path = tmp_path / "verification.json"
    store = VerificationStore(path, lambda text: text)
    with pytest.raises(ConfigError):
        store.read()
    path.write_text('{"token": "segredo"', encoding="utf-8")
    with pytest.raises(ConfigError) as error:
        store.read()
    assert "segredo" not in str(error.value)


def test_grava_e_le_redigindo_segredo_e_cabecalho(tmp_path: Path) -> None:
    path = tmp_path / "verification.json"
    store = VerificationStore(path, lambda text: text.replace("valorprivado", "***"))
    data = envelope() | {
        "entries": [
            {
                "fingerprint": FP,
                "level": "inconclusive",
                "reason": "revisar valorprivado",
                "attack": "Authorization: Bearer abcdefghijklmnop",
                "control": '{"password":"valorprivado"}',
            }
        ]
    }
    store.write(parse_verification(data))
    raw = path.read_text(encoding="utf-8")
    assert "valorprivado" not in raw
    assert "abcdefghijklmnop" not in raw
    assert json.loads(raw)["entries"][0]["level"] == "inconclusive"
    assert store.read().entries[0].fingerprint == FP


@pytest.mark.parametrize(
    ("original", "ambiguous"),
    [
        ('"schema_version": 1', '"schema_version": 2, "schema_version": 1'),
        ('"level": "likely"', '"level": "segredo", "level": "likely"'),
    ],
)
def test_recusa_chave_duplicada_quando_envelope_ambiguo(
    tmp_path: Path, original: str, ambiguous: str
) -> None:
    path = tmp_path / "verification.json"
    data = envelope() | {
        "entries": [{"fingerprint": FP, "level": "likely", "reason": "trecho observado"}]
    }
    raw = json.dumps(data)
    assert original in raw
    raw = raw.replace(original, ambiguous)
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(ConfigError) as error:
        VerificationStore(path, lambda text: text).read()

    assert "segredo" not in str(error.value)
    assert path.read_text(encoding="utf-8") == raw

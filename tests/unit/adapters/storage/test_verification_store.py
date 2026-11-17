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

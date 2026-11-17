"""Contrato offline de verificação e armazenamento redigido."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.storage.verification_store import VerificationStore
from harness_dast.application.verification import verify_offline
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import Classification, Finding, FindingEvidence
from harness_dast.domain.verification import classify_finding, parse_verification

RUN = "2026-11-16T12-00-00Z-produto-abcd"
FP = "a" * 64


def finding(*, proof: str = "trecho", available: bool = True, false: bool = False) -> Finding:
    return Finding(
        finding_id="F-aaaaaaaa",
        fingerprint=FP,
        title="alerta",
        plugin_id="1",
        alert_ref="1",
        classification=Classification(),
        proposed_severity="high",
        proposed_confidence="false_positive" if false else "high",
        method="GET",
        path_template="/x",
        attribution="scan",
        occurrences=1,
        evidence=FindingEvidence(zap_evidence=proof, available=available),
    )


def envelope() -> dict[str, object]:
    return {"schema_version": 1, "product": "produto", "run_id": RUN, "entries": []}


def test_classifica_com_prova_guardada_sem_alterar_achado() -> None:
    item = finding()
    before = item.model_dump()
    assert classify_finding(item).level == "likely"
    assert item.model_dump() == before


@pytest.mark.parametrize("item", [finding(proof=""), finding(available=False), finding(false=True)])
def test_nao_inventa_prova_contraria_quando_falta_prova_ou_zap_suspeita(item: Finding) -> None:
    assert classify_finding(item).level == "not_verifiable"


def test_caso_de_uso_gera_envelope_sem_reproducao() -> None:
    result = verify_offline("produto", RUN, [finding()])
    assert result.schema_version == 1
    assert result.entries[0].level == "likely"


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"product": "outro"},
        {"run_id": "../segredo"},
        {"entries": [{"fingerprint": FP, "level": "likely"}]},
        {
            "entries": [
                {"fingerprint": FP, "level": "reproduced", "reason": "ok", "severity": "low"}
            ]
        },
        {"entries": [{"fingerprint": FP, "level": "likely", "reason": "ok"}] * 2},
        {"entries": [{"fingerprint": "segredo", "level": "likely", "reason": "ok"}]},
    ],
)
def test_envelope_invalido_falha_sem_expor_valores(change: dict[str, object]) -> None:
    data = envelope() | change
    with pytest.raises(ConfigError) as error:
        parse_verification(data)
    assert "segredo" not in str(error.value)


def test_campo_ausente_falha_fechado() -> None:
    data = envelope()
    del data["entries"]
    with pytest.raises(ConfigError):
        parse_verification(data)


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

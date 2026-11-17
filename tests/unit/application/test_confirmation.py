"""Fluxo de confirmação com cliente em memória e artefatos temporários reais."""

from pathlib import Path

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.verification import VerificationFile
from tests.fakes.confirmation_rig import ConfirmationRig


def test_confirma_e_persiste_quando_controle_booleano_diverge(tmp_path: Path) -> None:
    rig = ConfirmationRig(tmp_path)
    result = rig.execute()
    assert isinstance(result, VerificationFile)
    assert result.entries[0].level == "reproduced"
    assert rig.store.read() == result
    requests = [r for r in rig.rig.target.requests if r.operation_id.startswith("confirm:")]
    assert len(requests) == 5
    assert all(r.method == "GET" for r in requests)
    assert "false" not in rig.path.read_text(encoding="utf-8")


def test_trava_impede_envio_quando_acionada(tmp_path: Path) -> None:
    rig = ConfirmationRig(tmp_path, stopped=True)
    before = len(rig.rig.target.requests)
    with pytest.raises(ConfigError, match="interrompida"):
        rig.execute()
    assert rig.store.read().entries[0].level == "inconclusive"
    assert len(rig.rig.target.requests) == before


@pytest.mark.parametrize("maximum", [0, 31, -1])
def test_recusa_limite_quando_fora_do_intervalo(tmp_path: Path, maximum: int) -> None:
    rig = ConfirmationRig(tmp_path)
    before = len(rig.rig.target.requests)
    with pytest.raises(ConfigError):
        rig.execute(maximum=maximum)
    assert len(rig.rig.target.requests) == before


def test_recusa_produto_divergente_antes_de_enviar(tmp_path: Path) -> None:
    rig = ConfirmationRig(tmp_path)
    report = rig.rig.artifacts.findings[rig.run_id]
    rig.rig.artifacts.findings[rig.run_id] = report.model_copy(update={"product": "outro"})
    before = len(rig.rig.target.requests)
    with pytest.raises(ConfigError):
        rig.execute()
    assert len(rig.rig.target.requests) == before


def test_escopo_negado_nao_abre_sessao_quando_semente_esta_fora(tmp_path: Path) -> None:
    rig = ConfirmationRig(tmp_path)
    log = rig.rig.store.exchanges[rig.run_id]
    exchange = log.exchanges[0].model_copy(update={"path": "/fora", "target": "/fora?q=ok"})
    rig.rig.store.exchanges[rig.run_id] = log.model_copy(update={"exchanges": (exchange,)})
    scan = rig.rig.artifacts.scans[rig.run_id]
    entry = scan.entries[0].model_copy(update={"path": "/fora"})
    rig.rig.artifacts.scans[rig.run_id] = scan.model_copy(update={"entries": (entry,)})
    report = rig.rig.artifacts.findings[rig.run_id]
    finding = report.findings[0].model_copy(update={"path_template": "/fora"})
    rig.rig.artifacts.findings[rig.run_id] = report.model_copy(update={"findings": (finding,)})
    before = len(rig.rig.target.requests)
    with pytest.raises(ConfigError, match="interrompida"):
        rig.execute()
    assert rig.store.read().entries[0].level == "inconclusive"
    assert len(rig.rig.target.requests) == before


def test_preserva_entrada_nao_selecionada_quando_ja_existe(tmp_path: Path) -> None:
    from harness_dast.domain.verification import VerificationEntry

    rig = ConfirmationRig(tmp_path)
    old = VerificationEntry(fingerprint="b" * 64, level="likely", reason="Evidência anterior.")
    rig.store.write(
        VerificationFile(schema_version=1, product="agenda", run_id=rig.run_id, entries=(old,))
    )
    result = rig.execute(finding="a" * 64)
    assert isinstance(result, VerificationFile)
    assert old in result.entries
    assert len(result.entries) == 2


@pytest.mark.parametrize(
    ("plugin", "mode", "requests"),
    [("40022", "time", 6), ("40012", "xss", 4), ("90022", "error", 4)],
)
def test_receita_com_trafego_falso_reproduz_efeito_e_controle(
    tmp_path: Path, plugin: str, mode: str, requests: int
) -> None:
    from tests.fakes.confirmation_rig import recipe_target

    rig = ConfirmationRig(tmp_path, plugin=plugin, handler=recipe_target(mode))
    result = rig.execute()
    assert isinstance(result, VerificationFile)
    assert result.entries[0].level == "reproduced"
    assert (
        len([r for r in rig.rig.target.requests if r.operation_id.startswith("confirm:")])
        == requests
    )
    assert "synthetic error" not in rig.path.read_text(encoding="utf-8")


def test_pilha_desatualizada_para_antes_do_login(tmp_path: Path) -> None:
    from harness_dast.application.confirmation import ConfirmationRequest
    from tests.fakes.confirmation_rig import StaleProfiles

    rig = ConfirmationRig(tmp_path)
    service = rig.service(profiles=StaleProfiles(rig.rig.profiles))
    before = len(rig.rig.target.requests)
    with pytest.raises(ConfigError, match="interrompida"):
        service.execute(ConfirmationRequest(product="agenda", run_id=rig.run_id))
    assert len(rig.rig.target.requests) == before
    assert rig.store.read().entries[0].level == "inconclusive"

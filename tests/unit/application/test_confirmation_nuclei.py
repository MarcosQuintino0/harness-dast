"""`confirm` de achado do Nuclei: reprodução do mesmo modelo, nunca confirmação independente."""

from pathlib import Path

import pytest

from harness_dast.domain.errors import ConfigError, ScopeViolation
from harness_dast.domain.nuclei_findings import NucleiFinding
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.verification import VerificationEntry, VerificationFile
from tests.fakes.confirmation_rig import ConfirmationRig
from tests.fakes.nuclei import (
    FakeNucleiReproducer,
    nuclei_finding,
    nuclei_profile_data,
    nuclei_result,
)

SECRETS = ("EXTRAIDO-SEGREDO", "CURL-SEGREDO", "/actuator/env")


def scenario(tmp_path: Path, *, enabled: bool = True) -> tuple[ConfirmationRig, NucleiFinding]:
    profile = ProductProfile.from_data(nuclei_profile_data()) if enabled else None
    rig = ConfirmationRig(tmp_path, profile=profile)
    finding = nuclei_finding(severity="high")
    report = rig.rig.artifacts.findings[rig.run_id]
    stored = nuclei_result(findings=(finding,), run_id=rig.run_id, product="agenda")
    rig.rig.artifacts.findings[rig.run_id] = report.model_copy(update={"nuclei": stored})
    return rig, finding


def entry_of(result: object, finding: NucleiFinding) -> VerificationEntry:
    assert isinstance(result, VerificationFile)
    return next(item for item in result.entries if item.fingerprint == finding.fingerprint)


def rerun(finding: NucleiFinding, *, found: bool, **changes: object) -> NucleiResult:
    return nuclei_result(findings=(finding,) if found else (), run_id="outra", **changes)  # type: ignore[arg-type]  # dict heterogêneo de teste


def test_reproduz_o_mesmo_modelo_e_registra_reproduced_sem_enviar_http(tmp_path: Path) -> None:
    rig, finding = scenario(tmp_path)
    nuclei = FakeNucleiReproducer(rerun(finding, found=True))
    before = len(rig.rig.target.requests)

    result = rig.execute(finding=finding.fingerprint, nuclei=nuclei)

    entry = entry_of(result, finding)
    assert entry.level == "reproduced"
    assert entry.recipe == "nuclei_template"
    assert "não uma confirmação independente" in entry.reason
    assert entry.control is not None
    assert "não é confirmação independente" in entry.control
    assert len(rig.rig.target.requests) == before
    (request,) = nuclei.requests
    assert request.only_templates == (finding.record.template_path,)
    assert request.persist is False
    assert request.product == "agenda"
    assert request.run_id == rig.run_id


def test_o_modelo_que_nao_voltou_vira_inconclusive_e_nunca_falso_positivo(tmp_path: Path) -> None:
    rig, finding = scenario(tmp_path)
    nuclei = FakeNucleiReproducer(rerun(finding, found=False))

    entry = entry_of(rig.execute(finding=finding.fingerprint, nuclei=nuclei), finding)

    assert entry.level == "inconclusive"
    assert "não prova correção" in entry.reason
    assert "não prova falso positivo" in entry.reason


def test_a_repeticao_parada_antes_do_fim_e_inconclusive_com_o_motivo(tmp_path: Path) -> None:
    rig, finding = scenario(tmp_path)
    stopped = rerun(finding, found=False, status="stopped_window", message="janela fechou")
    nuclei = FakeNucleiReproducer(stopped)

    entry = entry_of(rig.execute(finding=finding.fingerprint, nuclei=nuclei), finding)

    assert entry.level == "inconclusive"
    assert "parou antes do fim" in entry.reason


def test_a_verificacao_nao_guarda_caminho_nem_valor_extraido(tmp_path: Path) -> None:
    rig, finding = scenario(tmp_path)
    rig.execute(
        finding=finding.fingerprint, nuclei=FakeNucleiReproducer(rerun(finding, found=True))
    )

    saved = rig.path.read_text(encoding="utf-8")

    for marker in SECRETS:
        assert marker not in saved
    assert finding.record.template_id in saved


def test_sem_o_nuclei_montado_o_achado_fica_not_verifiable(tmp_path: Path) -> None:
    rig, finding = scenario(tmp_path)

    entry = entry_of(rig.execute(finding=finding.fingerprint), finding)

    assert entry.level == "not_verifiable"
    assert "extra_checks.nuclei" in entry.reason


def test_perfil_sem_a_chave_do_nuclei_nao_roda_o_motor(tmp_path: Path) -> None:
    rig, finding = scenario(tmp_path, enabled=False)
    nuclei = FakeNucleiReproducer(rerun(finding, found=True))

    entry = entry_of(rig.execute(finding=finding.fingerprint, nuclei=nuclei), finding)

    assert entry.level == "not_verifiable"
    assert nuclei.requests == []


def test_erro_de_configuracao_do_nuclei_vira_not_verifiable_sem_derrubar_o_confirm(
    tmp_path: Path,
) -> None:
    rig, finding = scenario(tmp_path)
    nuclei = FakeNucleiReproducer(error=ConfigError("Sem imagem do Nuclei.", hint="Reinstale."))

    entry = entry_of(rig.execute(finding=finding.fingerprint, nuclei=nuclei), finding)

    assert entry.level == "not_verifiable"
    assert "CONFIG_ERROR" in entry.reason
    assert "Sem imagem" not in entry.reason


def test_parada_de_escopo_grava_inconclusive_e_propaga_o_erro(tmp_path: Path) -> None:
    rig, finding = scenario(tmp_path)
    nuclei = FakeNucleiReproducer(error=ScopeViolation("janela com texto do alvo: SEGREDO-ALVO"))

    with pytest.raises(ScopeViolation) as raised:
        rig.execute(finding=finding.fingerprint, nuclei=nuclei)

    assert "SEGREDO-ALVO" not in str(raised.value)
    saved = rig.store.read()
    assert saved.entries[0].level == "inconclusive"
    assert saved.entries[0].fingerprint == finding.fingerprint


def test_o_nuclei_json_de_outra_execucao_e_recusado_antes_de_repetir(tmp_path: Path) -> None:
    rig, finding = scenario(tmp_path)
    report = rig.rig.artifacts.findings[rig.run_id]
    other = nuclei_result(findings=(finding,), run_id="outra", product="agenda")
    rig.rig.artifacts.findings[rig.run_id] = report.model_copy(update={"nuclei": other})
    nuclei = FakeNucleiReproducer(rerun(finding, found=True))

    with pytest.raises(ConfigError, match="Nuclei"):
        rig.execute(finding=finding.fingerprint, nuclei=nuclei)

    assert nuclei.requests == []

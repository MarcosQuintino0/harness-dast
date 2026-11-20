"""O Nuclei (ADR 0122) no painel: contagem, falha grave e o cartão da aba Falhas, sem conteúdo."""

from harness_dast.domain.nuclei_findings import NucleiFinding
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.panel.model import PanelView
from harness_dast.domain.panel.pages import render_panel
from tests.fakes.nuclei import nuclei_finding, nuclei_result
from tests.unit.domain.panel.helpers import findings_report, view

SECRETS = ("CURL-SEGREDO", "REQ-SEGREDO", "RESP-SEGREDO", "EXTRAIDO-SEGREDO")


def _with_nuclei(*findings: NucleiFinding, **changes: object) -> PanelView:
    result: NucleiResult = nuclei_result(findings=findings, **changes)  # type: ignore[arg-type]  # dict heterogêneo de teste
    return view(findings=findings_report().model_copy(update={"nuclei": result}))


def test_sem_o_estagio_o_painel_nao_mostra_o_nuclei() -> None:
    panel_view = view()

    assert panel_view.nuclei is None
    assert "Nuclei" not in render_panel(panel_view)["findings.html"]
    assert all(item.origin != "nuclei" for item in panel_view.severe)


def test_a_contagem_do_nuclei_entra_nas_severidades_e_no_resumo_do_estagio() -> None:
    base = view().counts
    panel_view = _with_nuclei(
        nuclei_finding("a", severity="high"), nuclei_finding("b", severity="low")
    )

    assert base is not None
    assert panel_view.counts is not None
    assert panel_view.counts.high == base.high + 1
    assert panel_view.counts.low == base.low + 1
    assert panel_view.nuclei is not None
    assert (panel_view.nuclei.findings, panel_view.nuclei.severe) == (2, 1)
    assert panel_view.nuclei.technologies == 0


def test_o_achado_grave_do_nuclei_vira_falha_com_a_origem_e_a_prova_mais_fraca() -> None:
    panel_view = _with_nuclei(nuclei_finding("springboot-env", severity="critical"))

    (item,) = [found for found in panel_view.severe if found.origin == "nuclei"]
    assert item.title == "springboot-env"
    assert item.severity == "high"
    assert item.confidence == 1
    assert item.fingerprint is not None
    assert item.nuclei_evidence is not None
    assert "1 valor(es) extraído(s)" in item.nuclei_evidence


def test_a_aba_falhas_mostra_o_cartao_a_falha_e_nunca_o_conteudo_do_alvo() -> None:
    panel_view = _with_nuclei(nuclei_finding("springboot-env", severity="high"))

    page = render_panel(panel_view)["findings.html"]

    assert "Nuclei · 1" in page
    assert "tecnologia não é achado" in page
    assert "Um modelo conhecido do Nuclei casou" in page
    assert "reprodução, não confirmação independente" in page
    for marker in SECRETS:
        assert marker not in page


def test_o_estagio_parado_avisa_na_aba() -> None:
    panel_view = _with_nuclei(status="stopped_kill", message="KILL")

    page = render_panel(panel_view)["findings.html"]

    assert "O Nuclei parou antes do fim" in page

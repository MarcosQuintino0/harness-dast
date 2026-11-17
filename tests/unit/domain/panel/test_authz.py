"""Lacunas horizontais continuam visíveis depois do limite geral das apresentações."""

from harness_dast.domain.authz.result import AuthzNotTested, CheckSummary
from harness_dast.domain.panel.authz import render_authz
from harness_dast.domain.panel.build import build_panel_view
from harness_dast.domain.report.authz import authz_lines
from harness_dast.domain.report.html_authz import authz_result_section
from tests.unit.application.test_report_authz import authz_result
from tests.unit.domain.panel.helpers import sources


def test_painel_quando_sem_estagio_explicita_ausencia_de_conclusao() -> None:
    assert "não há conclusão" in render_authz(build_panel_view(sources()))


def test_lacuna_quando_depois_de_centenas_de_notas_nao_some_em_nenhuma_apresentacao() -> None:
    unrelated = AuthzNotTested(check="vertical", reason="other", message="Outra lacuna.")
    gaps = tuple(
        AuthzNotTested(
            check="horizontal",
            operation_id=f"get{i}",
            method="GET",
            path=f"/api/resource{i}/{{id}}",
            reason="owner_collection_missing",
            message="Não há coleção da conta; declare a fonte na carta.",
        )
        for i in range(105)
    )
    result = authz_result(findings=False).model_copy(
        update={
            "not_tested": (*([unrelated] * 110), *gaps),
            "checks": (
                CheckSummary(
                    check="horizontal", status="skipped", message="Leitura de dono: zero objetos."
                ),
            ),
        }
    )
    view = build_panel_view(sources(authz=result))
    outputs = ["\n".join(authz_lines(result)), authz_result_section(result), render_authz(view)]
    for text in outputs:
        assert "/api/resource104/" in text
        assert "owner_collection_missing" in text
        assert "declare a fonte" in text
        assert "Leitura de dono: zero objetos" in text


def test_texto_quando_vem_de_operacao_e_escapado() -> None:
    note = AuthzNotTested(
        check="horizontal",
        operation_id="external",
        method="GET",
        path="/<script>alert(1)</script>/{id}",
        reason="owner_collection_empty",
        message="<img src=x onerror=alert(1)> informe recursos sintéticos.",
    )
    result = authz_result(findings=False).model_copy(update={"not_tested": (note,)})
    text = render_authz(build_panel_view(sources(authz=result)))
    assert "<script>" not in text
    assert "<img src=x" not in text
    assert "owner_collection_empty" in text

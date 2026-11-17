"""`proxy_signals` no relatório: modelo, `report.md` e `report.html` (ADR 0049)."""

import json

from harness_dast.domain.report.build import assemble_report
from harness_dast.domain.report.html import render_html
from harness_dast.domain.report.markdown import render_markdown
from harness_dast.domain.report.model import FindingsReport, build_digest
from harness_dast.domain.signal_result import (
    DISABLED_MESSAGE,
    ProxySignals,
    SignalFinding,
    SignalWindow,
    disabled_signals,
)
from tests.unit.domain.report.helpers import entry, operation, probe_result, scan_result

HOSTILE = "<script>alert(1)</script> `x` | [l](http://evil.example)"


def finding(**changes: object) -> SignalFinding:
    data: dict[str, object] = {
        "finding_id": "S-0a1b2c3d",
        "fingerprint": "0a1b2c3d" + "0" * 56,
        "category": "sql_error",
        "title": "Possível erro de banco de dados",
        "proposed_severity": "medium",
        "proposed_confidence": "medium",
        "cwe": 209,
        "operation_id": "obter",
        "method": "GET",
        "path_template": "/users/v1/{}",
        "occurrences": 3,
        "statuses": (500, 400),
        "query_params": ("q",),
    }
    data.update(changes)
    return SignalFinding.model_validate(data)


def enabled(*findings: SignalFinding, **changes: object) -> ProxySignals:
    data: dict[str, object] = {
        "enabled": True,
        "window": SignalWindow(start="2026-11-13T05:15:32+00:00", end="2026-11-13T05:20:00+00:00"),
        "responses_examined": 40,
        "responses_skipped": {"type": 5, "encoding": 2},
        "responses_with_signal": 3,
        "counts": {"sql_error": 3, "stack_trace_java": 0},
        "findings": findings,
    }
    data.update(changes)
    return ProxySignals.model_validate(data)


def report(signals: ProxySignals | None) -> FindingsReport:
    ops = [operation("obter", "GET", "/users/v1/{username}")]
    return assemble_report(
        probe=probe_result(ops),
        scan=scan_result([entry("obter", "GET", "/users/v1/{username}", 4)]),
        raw_alerts=[],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="2026-11-13T06:00:00+00:00",
        harness_version="0.0-test",
        auth_header=("Authorization", "Bearer $TOKEN"),
        csrf_header=None,
        proxy_signals=signals,
    )


def test_relatorio_antigo_sem_proxy_signals_continua_valido_e_sem_a_secao() -> None:
    data = report(None).model_dump(mode="json")
    del data["proxy_signals"]
    del data["summary"]["signal_by_severity"]

    loaded = FindingsReport.model_validate(data)

    assert loaded.proxy_signals is None
    assert loaded.summary.signal_by_severity == {}
    assert "Sinais vistos pela cerca" not in render_markdown(loaded)
    assert "Sinais vistos pela cerca" not in render_html(loaded)


def test_desligado_mostra_a_mensagem_e_nao_afirma_ausencia_de_erros() -> None:
    built = report(disabled_signals())

    markdown, html = render_markdown(built), render_html(built)

    for text in (markdown, html):
        assert "Sinais vistos pela cerca" in text
        assert DISABLED_MESSAGE in text
        assert "não prova ausência de erros" in text
    assert built.summary.signal_by_severity == {}


def test_ligado_mostra_a_base_de_respostas_o_motivo_dos_pulos_e_o_achado() -> None:
    built = report(enabled(finding()))

    for text in (render_markdown(built), render_html(built)):
        assert "lidas: 40" in text
        assert "não lidas: 7" in text
        assert "S-0a1b2c3d" in text
        assert "proxy_error_signal" in text
        assert "CWE-209" in text
        assert "sql_error" in text
        assert "Application Error Disclosure" in text


def test_resumo_separa_os_achados_de_sinal_dos_do_zap() -> None:
    built = report(
        enabled(
            finding(),
            finding(
                finding_id="S-1",
                fingerprint="1" * 64,
                category="debug_page",
                proposed_severity="low",
            ),
        )
    )

    assert built.summary.total == 0
    assert built.summary.by_severity["medium"] == 0
    assert built.summary.signal_by_severity == {
        "high": 0,
        "medium": 1,
        "low": 1,
        "informational": 0,
        "unknown": 0,
    }
    assert "Sinais de erro interno vistos pela cerca" in render_markdown(built)


def test_secao_de_0045_so_ganha_a_linha_explicativa_quando_a_cerca_leu() -> None:
    off = report(None)
    on = report(enabled())
    note = "subconjunto das respostas"

    assert note not in render_markdown(off)
    assert note not in render_html(off)
    assert note in render_markdown(on)
    assert note in render_html(on)
    assert note not in render_markdown(report(disabled_signals()))


def test_contagem_do_adr_0045_em_findings_json_nao_muda_com_proxy_signals() -> None:
    before = report(None).internal_error_signals
    after = report(enabled(finding())).internal_error_signals

    assert before == after


def test_conteudo_hostil_em_nome_de_parametro_e_caminho_e_escapado() -> None:
    built = report(enabled(finding(query_params=(HOSTILE,), path_template="/x/" + HOSTILE)))

    markdown, html = render_markdown(built), render_html(built)

    # No Markdown o texto do alvo só aparece dentro de trecho de código com crases suficientes
    # (a crase do próprio texto não fecha o trecho); no HTML ele é escapado.
    for line in markdown.splitlines():
        if "<script>" in line:
            assert line.count("``") >= 2
            assert line.index("``") < line.index("<script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_findings_json_traz_os_campos_novos_e_nenhum_valor_de_resposta() -> None:
    built = report(enabled(finding()))

    data = json.loads(built.model_dump_json())

    assert data["proxy_signals"]["findings"][0]["origin"] == "proxy"
    assert data["proxy_signals"]["findings"][0]["technique"] == "proxy_error_signal"
    assert data["proxy_signals"]["findings"][0]["status"] == "needs_triage"
    assert "signal_by_severity" in data["summary"]


def test_digest_do_envelope_leva_proxy_signals() -> None:
    built = report(enabled(finding()))

    digest = build_digest(built, ("findings.json",), "none", exceeds=False)

    assert digest.proxy_signals == built.proxy_signals


def test_achados_omitidos_aparecem_no_texto() -> None:
    built = report(enabled(finding(), findings_omitted=4))

    assert "4 achado(s) de menor gravidade" in render_markdown(built)
    assert "4 achado(s) de menor gravidade" in render_html(built)


def test_modelo_recusa_campo_desconhecido_e_categoria_fora_do_catalogo() -> None:
    import pytest

    with pytest.raises(ValueError, match="extra"):
        finding(body="ORA-00933")
    with pytest.raises(ValueError, match="category"):
        finding(category="senha_vazada")

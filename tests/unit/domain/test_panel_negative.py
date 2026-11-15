"""O estágio `negative` (ADR 0051) no painel: etapas, contagem, o que ficou de fora, falha grave."""

from harness_dast.domain.panel_model import PanelStage, PanelView
from harness_dast.domain.panel_pages import render_panel
from harness_dast.domain.run_metrics import stage_seconds
from harness_dast.domain.run_summary import StageRecord
from tests.unit.domain.negative_samples import accepted, negative_result
from tests.unit.domain.panel_helpers import run_summary, sources, view


def _stage(panel_view: PanelView, key: str) -> PanelStage:
    return next(item for item in panel_view.stages if item.key == key)


def _with_negative(**changes: object) -> PanelView:
    stages = tuple(
        StageRecord(name="negative", status="ok", duration_seconds=12.0)
        if item.name == "negative"
        else item
        for item in run_summary().stages
    )
    return view(summary=run_summary(stages=stages), negative=negative_result(), **changes)


def test_the_stage_shows_in_the_etapas_tab_with_time_and_a_sentence_with_the_numbers() -> None:
    panel_view = _with_negative()

    stage = _stage(panel_view, "negative")
    assert stage.state == "done"
    assert stage.label == "Valores proibidos"
    assert stage.seconds == 12.0
    assert "2 pedidos" in stage.summary
    assert "2 falhas encontradas" in stage.summary
    assert "1 item não testado" in stage.summary
    page = render_panel(panel_view)["stages.html"]
    assert "As 6 etapas" in page
    assert "Valores proibidos: testou o que o contrato não aceita" in page


def test_a_skipped_stage_says_how_to_turn_it_back_on_not_that_it_was_not_asked_for() -> None:
    stage = _stage(view(), "negative")

    assert stage.state == "skipped"
    assert "--no-negative" in stage.summary
    assert "--skip-scan" in stage.summary


def test_a_run_json_from_before_the_stage_does_not_make_it_look_cut() -> None:
    old = tuple(item for item in run_summary().stages if item.name != "negative")

    panel_view = view(summary=run_summary(stages=old))

    assert _stage(panel_view, "negative").state == "skipped"
    assert panel_view.verdict.kind == "finished"
    assert panel_view.verdict.stopped_stage is None


def test_without_run_json_the_state_comes_from_the_files() -> None:
    ran = view(summary=None, negative=negative_result())
    cut = view(summary=None, negative=negative_result(status="stopped_deadline"))
    never = view(summary=None)

    assert _stage(ran, "negative").state == "done"
    assert _stage(cut, "negative").state == "cut"
    assert _stage(cut, "negative").message == "parou"
    assert _stage(never, "negative").state == "skipped"


def test_a_dry_run_result_is_shown_as_skipped_not_as_a_test_that_sent_something() -> None:
    plan = negative_result().model_copy(update={"dry_run": True})

    panel_view = view(summary=None, negative=plan)

    stage = _stage(panel_view, "negative")
    assert stage.state == "skipped"
    assert "simulação" in (stage.message or "")


def test_the_counts_include_the_negative_findings_next_to_the_zap_and_authz_ones() -> None:
    plain = view()
    with_negative = _with_negative()

    assert plain.counts is not None
    assert with_negative.counts is not None
    assert with_negative.counts.low == plain.counts.low + 2


def test_a_high_negative_finding_goes_to_the_failures_without_a_hand_repro_and_to_confirm() -> None:
    high = accepted(severity="high", title="PUT /api/produtos/1: valor aceito")

    panel_view = view(negative=negative_result(findings=(high,)))

    (item,) = [found for found in panel_view.severe if found.origin == "negative"]
    assert item.confidence == 1
    assert item.negative_evidence is not None
    assert item.parameter == "limite"
    assert item.input_vector == "query"
    page = render_panel(panel_view)["findings.html"]
    assert "N-1a2b3c4d" in page
    assert "teste de valores que o contrato proíbe" in page
    assert "passo a passo" in page
    assert "mandou o valor que o contrato proíbe" in page


def test_the_left_out_list_says_when_the_stage_did_not_run_was_skipped_or_was_cut() -> None:
    skipped = view()
    cut = _with_negative().model_copy()
    stopped = view(negative=negative_result(status="stopped_window"))

    text_skipped = " ".join(item.text for item in skipped.left_out if item.kind == "negative")
    text_stopped = [item.text for item in stopped.left_out if item.kind == "negative"]
    text_cut = [item.text for item in cut.left_out if item.kind == "negative"]

    assert "foi pulado a pedido" in text_skipped
    assert any("parou antes do fim" in text for text in text_stopped)
    assert any("1 item" in text and "não puderam" in text for text in text_cut)


def test_the_never_run_case_is_told_apart_from_the_skipped_by_choice() -> None:
    panel_view = view(summary=None, scan=None)

    text = " ".join(item.text for item in panel_view.left_out if item.kind == "negative")

    assert "não rodou" in text


def test_the_coverage_page_shows_the_negative_row_with_the_risk() -> None:
    page = render_panel(view())["coverage.html"]

    assert "Valores que o contrato proíbe." in page
    assert "campo sem validação" in page


def test_stage_seconds_reads_the_negative_file_when_there_is_no_run_json() -> None:
    seconds = stage_seconds(
        probe=None,
        scan=None,
        authz=None,
        negative=negative_result(),
        report_seconds=None,
        stages=None,
    )

    assert seconds.negative == 600.0
    assert seconds.authz is None


def test_the_sources_carry_the_negative_result_to_the_identity_end_time() -> None:
    panel_view = view(summary=None, negative=negative_result())

    assert panel_view.identity.duration_seconds is not None
    assert sources().negative is None

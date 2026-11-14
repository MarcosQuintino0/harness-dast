"""Caso de uso `panel`: lê os arquivos que existem, monta a visão e grava as páginas."""

from collections.abc import Mapping
from datetime import UTC

import pytest

from harness_dast.application.panel import Panel, PanelRequest
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.panel_model import PanelCommand, PanelExplanation, PanelJournal
from harness_dast.domain.probe_result import RunManifest
from harness_dast.domain.report_model import FindingsReport
from tests.fakes.panel_ports import FakePanelFiles, FakeSpecLoader
from tests.fakes.profile_data import valid_profile
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.unit.domain.panel_helpers import PRODUCT, sources, spec_operations
from tests.unit.domain.panel_measure_helpers import agent_metrics
from tests.unit.domain.report_helpers import RUN_ID

OTHER_RUN = "2026-11-12T05-15-32Z-vampi-cd34"


class Hooks:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def commands(self, product: str, run_id: str) -> PanelJournal | None:
        self.asked.append(f"commands:{product}:{run_id}")
        command = PanelCommand(command="hdast probe vampi", translation="Tentou as funções.")
        return PanelJournal(commands=(command,), skipped_lines=2)

    def explanations(
        self, report: FindingsReport | None, authz: AuthzResult | None
    ) -> Mapping[str, PanelExplanation]:
        assert report is not None
        return {report.findings[0].finding_id: PanelExplanation(title="Comando no banco")}


def stocked() -> FakePanelFiles:
    src = sources()
    files = FakePanelFiles()
    files.runs = [RUN_ID, OTHER_RUN]
    assert src.summary is not None
    assert src.probe is not None
    assert src.scan is not None
    assert src.findings is not None
    files.summary[RUN_ID] = src.summary
    files.probe[RUN_ID] = src.probe
    files.scan[RUN_ID] = src.scan
    files.findings[RUN_ID] = src.findings
    return files


def panel(
    files: FakePanelFiles,
    *,
    with_profile: bool = True,
    specs: FakeSpecLoader | None = None,
    hooks: Hooks | None = None,
) -> Panel:
    profiles = InMemoryProfileRepository()
    if with_profile:
        profiles.add(valid_profile(PRODUCT))
    return Panel(
        profiles=profiles,
        specs=specs or FakeSpecLoader(spec_operations()),
        files=files,
        timezone=UTC,
        hooks=hooks,
    )


def test_execute_writes_the_six_pages_and_reports_what_it_read_and_what_is_missing() -> None:
    files = stocked()

    outcome = panel(files).execute(PanelRequest(product=PRODUCT, run_id=RUN_ID))

    assert tuple(files.written[RUN_ID]) == (
        "summary.html", "stages.html", "findings.html", "coverage.html", "terminal.html",
        "time-and-tokens.html",
    )  # fmt: skip
    assert outcome.entry == "panel/summary.html"
    assert outcome.directory == "panel"
    assert len(outcome.files) == 6
    assert outcome.verdict == "finished"
    assert outcome.severe_findings == 1
    assert outcome.sources == ("run.json", "probe.json", "scan.json", "findings.json")
    assert outcome.missing == ("manifest.json", "authz.json", "metrics.json")


def test_the_openapi_summary_and_the_profile_mode_reach_the_page() -> None:
    files = stocked()

    panel(files).execute(PanelRequest(product=PRODUCT, run_id=RUN_ID))

    page = files.written[RUN_ID]["summary.html"]
    assert "Ver usuário" in page
    assert "Cerca: modo estrito" in page


def test_the_agent_tokens_reach_the_time_and_tokens_page() -> None:
    files = stocked()
    files.agent_metrics[RUN_ID] = agent_metrics()

    panel(files).execute(PanelRequest(product=PRODUCT, run_id=RUN_ID))

    page = files.written[RUN_ID]["time-and-tokens.html"]
    assert "tokens (trabalho do agente de IA)" in page
    assert "claude-sonnet-5-5" in page


def test_without_agent_metrics_the_tokens_are_not_measured() -> None:
    files = stocked()

    panel(files).execute(PanelRequest(product=PRODUCT, run_id=RUN_ID))

    page = files.written[RUN_ID]["time-and-tokens.html"]
    assert "tokens · não medido" in page
    assert "tokens (trabalho do agente de IA)" not in page


def test_without_a_run_the_latest_one_of_the_product_is_used() -> None:
    files = stocked()

    outcome = panel(files).execute(PanelRequest(product=PRODUCT))

    assert outcome.run_id == RUN_ID  # "2026-11-13" é mais recente que "2026-11-12"


def test_a_product_with_no_run_says_what_to_do() -> None:
    files = FakePanelFiles()

    with pytest.raises(ConfigError, match="nenhuma execução"):
        panel(files).execute(PanelRequest(product=PRODUCT))


@pytest.mark.parametrize("run_id", ["../x", "2026", "", "a/b"])
def test_an_invalid_run_id_is_refused_without_echoing_it(run_id: str) -> None:
    with pytest.raises(ConfigError) as caught:
        panel(stocked()).execute(PanelRequest(product=PRODUCT, run_id=run_id))

    assert run_id not in caught.value.message or run_id == ""


def test_a_run_with_no_known_file_is_refused() -> None:
    with pytest.raises(ConfigError, match="nenhum arquivo"):
        panel(FakePanelFiles()).execute(PanelRequest(product=PRODUCT, run_id=OTHER_RUN))


def test_a_run_of_another_product_is_refused() -> None:
    files = stocked()
    files.manifest[OTHER_RUN] = RunManifest.model_validate(
        {
            "run_id": OTHER_RUN,
            "command": "probe",
            "product": "outro",
            "harness_version": "1",
            "hashes": {},
            "limits": {
                "requests_per_second": 1,
                "max_duration_minutes": 1,
                "zap_threads_per_host": 1,
            },
            "seed": 1,
            "started_at": "2026-11-12T05:15:32+00:00",
        }
    )

    with pytest.raises(ConfigError, match="outro produto"):
        panel(files).execute(PanelRequest(product=PRODUCT, run_id=OTHER_RUN))

    assert OTHER_RUN not in files.written


def test_an_unreadable_file_is_treated_as_missing_and_the_panel_still_comes_out() -> None:
    files = stocked()
    files.unreadable.add("findings.json")

    outcome = panel(files).execute(PanelRequest(product=PRODUCT, run_id=RUN_ID))

    assert "findings.json" in outcome.missing
    assert outcome.severe_findings is None
    assert "não tem <b>findings.json</b>" in files.written[RUN_ID]["summary.html"]


def test_without_a_profile_or_with_a_broken_openapi_the_names_fall_back() -> None:
    no_profile = stocked()
    broken = stocked()

    panel(no_profile, with_profile=False).execute(PanelRequest(product=PRODUCT, run_id=RUN_ID))
    panel(broken, specs=FakeSpecLoader(fails=True)).execute(
        PanelRequest(product=PRODUCT, run_id=RUN_ID)
    )

    assert "Cerca:" not in no_profile.written[RUN_ID]["summary.html"]
    assert "Ver usuário" not in no_profile.written[RUN_ID]["summary.html"]
    assert "Ver usuário" not in broken.written[RUN_ID]["summary.html"]
    assert "Cerca: modo estrito" in broken.written[RUN_ID]["summary.html"]


def test_the_hooks_are_asked_and_their_answers_reach_the_page() -> None:
    files = stocked()
    hooks = Hooks()

    panel(files, hooks=hooks).execute(PanelRequest(product=PRODUCT, run_id=RUN_ID))

    page = files.written[RUN_ID]["summary.html"]
    assert hooks.asked == [f"commands:{PRODUCT}:{RUN_ID}"]
    assert "1 comando, todos visíveis" in page
    assert "Comando no banco" in page


class BrokenJournalHooks(Hooks):
    def commands(self, product: str, run_id: str) -> PanelJournal | None:
        raise ConfigError("Não foi possível ler o diário de comandos.")


def test_an_unreadable_diary_does_not_stop_the_panel_and_shows_the_empty_state() -> None:
    files = stocked()

    panel(files, hooks=BrokenJournalHooks()).execute(PanelRequest(product=PRODUCT, run_id=RUN_ID))

    assert "Sem diário de comandos para este teste." in files.written[RUN_ID]["terminal.html"]


def test_skipped_diary_lines_reach_the_terminal_page() -> None:
    files = stocked()

    panel(files, hooks=Hooks()).execute(PanelRequest(product=PRODUCT, run_id=RUN_ID))

    assert "2 linhas do diário estavam corrompidas" in files.written[RUN_ID]["terminal.html"]


def test_execute_propagates_a_write_failure_to_the_person() -> None:
    files = stocked()
    files.write_error = ConfigError("Não foi possível gravar as páginas do painel.")

    with pytest.raises(ConfigError, match="gravar"):
        panel(files).execute(PanelRequest(product=PRODUCT, run_id=RUN_ID))


def test_refresh_returns_the_entry_page() -> None:
    assert panel(stocked()).refresh(PRODUCT, RUN_ID) == "panel/summary.html"


def test_refresh_never_raises_a_harness_error() -> None:
    failing = stocked()
    failing.write_error = ConfigError("disco cheio")

    assert panel(failing).refresh(PRODUCT, RUN_ID) is None
    assert panel(FakePanelFiles()).refresh(PRODUCT, RUN_ID) is None
    assert panel(stocked()).refresh(PRODUCT, "inválido") is None
    assert panel(stocked()).refresh("outro", RUN_ID) is None

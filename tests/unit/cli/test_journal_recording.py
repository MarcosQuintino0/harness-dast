import json
import os
from datetime import UTC, datetime
from pathlib import Path

import typer
from typer.core import TyperGroup

from harness_dast.adapters.storage.command_journal import FileCommandJournalStore
from harness_dast.application.command_journal import load_journal_for_run
from harness_dast.application.common_ports import CommandJournalStore
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.journal_recording import describe_invocation, record_invocation
from harness_dast.cli.output import CliState, build_failure, build_success
from harness_dast.domain.command_journal import JournalEntry, JournalLoad
from harness_dast.domain.command_translation import translated_commands
from harness_dast.domain.errors import ConfigError
from tests.fakes.clock import FixedClock


class _MemoryJournal:
    def __init__(self) -> None:
        self.saved: list[tuple[str | None, JournalEntry]] = []

    def append(self, product: str | None, entry: JournalEntry) -> None:
        self.saved.append((product, entry))

    def load(self, product: str | None) -> JournalLoad:
        return JournalLoad(entries=tuple(e for _, e in self.saved), skipped_lines=0)


class _BrokenJournal:
    def append(self, product: str | None, entry: JournalEntry) -> None:
        raise ConfigError("sem espaço")

    def load(self, product: str | None) -> JournalLoad:
        raise ConfigError("sem espaço")


def _leaf_commands(group: TyperGroup, prefix: tuple[str, ...] = ()) -> list[str]:
    names: list[str] = []
    for name, child in group.commands.items():
        if isinstance(child, TyperGroup):
            names.extend(_leaf_commands(child, (*prefix, name)))
        else:
            names.append(" ".join((*prefix, name)))
    return names


def test_todo_comando_da_cli_tem_traducao() -> None:
    root = typer.main.get_command(build_app())
    assert isinstance(root, TyperGroup)

    missing = sorted(set(_leaf_commands(root)) - translated_commands())

    assert missing == [], f"comandos sem tradução em domain/command_translation.py: {missing}"


def test_run_app_registra_o_comando_no_diario_com_hora_do_relogio() -> None:
    journal = _MemoryJournal()
    clock = FixedClock(datetime(2026, 11, 14, 10, 0, tzinfo=UTC))

    code = run_app(build_app(), ["version", "--json"], clock=clock, journal=journal)

    assert code == 0
    ((product, entry),) = journal.saved
    assert product is None
    assert (entry.command, entry.exit_code, entry.state) == ("version", 0, "ok")
    assert entry.started_at == datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
    assert entry.summary.get("version")


def test_run_app_com_erro_de_uso_registra_comando_com_estado_erro() -> None:
    journal = _MemoryJournal()

    code = run_app(build_app(), ["probe"], journal=journal)

    assert code == 2
    ((_, entry),) = journal.saved
    assert (entry.command, entry.state, entry.exit_code) == ("probe", "erro", 2)
    assert entry.error_code == "CONFIG_ERROR"


def test_run_app_com_produto_inexistente_registra_produto_e_flags(tmp_path: Path) -> None:
    journal = _MemoryJournal()

    code = run_app(
        build_app(),
        ["probe", "meu-produto", "--dry-run", "--seed", "7", "--products-dir", str(tmp_path)],
        journal=journal,
    )

    assert code != 0
    ((product, entry),) = journal.saved
    assert product == "meu-produto"
    assert {f.name for f in entry.flags} == {"--seed", "--dry-run", "--products-dir"}
    assert ("--seed", "7") in [(f.name, f.value) for f in entry.flags]


def test_run_app_nao_muda_o_codigo_de_saida_quando_o_diario_falha() -> None:
    assert run_app(build_app(), ["version"], journal=_BrokenJournal()) == 0


def test_run_app_sem_diario_injetado_grava_so_na_pasta_de_estado_isolada(tmp_path: Path) -> None:
    code = run_app(build_app(), ["version"])

    assert code == 0
    state_dir = Path(os.environ["HDAST_STATE_DIR"])
    assert state_dir.is_relative_to(tmp_path)
    lines = (state_dir / "journal" / "_sem-produto.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["command"] == "version"


def test_run_app_com_ajuda_nao_registra() -> None:
    journal = _MemoryJournal()

    run_app(build_app(), ["probe", "--help"], journal=journal)

    assert journal.saved == []


def test_run_app_com_comando_desconhecido_nao_registra() -> None:
    journal = _MemoryJournal()

    assert run_app(build_app(), ["naoexiste"], journal=journal) == 2
    assert journal.saved == []


def test_describe_invocation_separa_produto_flags_e_repeticoes() -> None:
    got = describe_invocation(
        build_app(),
        ["probe", "clinica", "--only", "a", "--only", "b", "--include-delete", "--seed", "3"],
    )

    assert got is not None
    assert (got.command, got.product, got.args) == ("probe", "clinica", ())
    assert set(got.flags) == {
        ("--only", "a"),
        ("--only", "b"),
        ("--include-delete", None),
        ("--seed", "3"),
    }


def test_describe_invocation_de_subcomando_aninhado_usa_o_nome_por_extenso() -> None:
    got = describe_invocation(build_app(), ["stack", "up", "clinica", "--build"])

    assert got is not None
    assert (got.command, got.product) == ("stack up", "clinica")
    assert ("--build", None) in got.flags


def test_describe_invocation_de_secret_set_traz_o_nome_como_argumento() -> None:
    got = describe_invocation(build_app(), ["secret", "set", "MINHA_CHAVE"])

    assert got is not None
    assert (got.command, got.product, got.args) == ("secret set", None, ("MINHA_CHAVE",))


def test_diario_de_um_teste_atravessa_o_adaptador_e_o_recorte(tmp_path: Path) -> None:
    store: CommandJournalStore = FileCommandJournalStore(tmp_path)
    run_id = "2026-11-14T10-00-00Z-clinica-aaaa"
    clock = FixedClock(datetime(2026, 11, 14, 10, 0, tzinfo=UTC))
    run_app(
        build_app(),
        ["profile", "validate", "clinica", "--products-dir", str(tmp_path)],
        clock=clock,
        journal=store,
    )
    entry = JournalEntry(
        started_at=datetime(2026, 11, 14, 10, 5, tzinfo=UTC),
        finished_at=datetime(2026, 11, 14, 10, 6, tzinfo=UTC),
        command="probe",
        product="clinica",
        run_id=run_id,
        exit_code=0,
        state="ok",
    )
    store.append("clinica", entry)

    got = load_journal_for_run(store, "clinica", run_id)

    assert [e.command for e in got.entries] == ["profile validate", "probe"]


class _Panels:
    """Fábrica de painel falsa: guarda o que lhe pediram."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Path | None]] = []
        self.journals: list[CommandJournalStore | None] = []
        self._products_dir: Path | None = None

    def __call__(self, products_dir: Path | None, journal: CommandJournalStore | None) -> "_Panels":
        self._products_dir = products_dir
        self.journals.append(journal)
        return self

    def refresh(self, product: str, run_id: str) -> str | None:
        self.calls.append((product, run_id, self._products_dir))
        return "panel/summary.html"


def _record(
    argv: list[str], envelope_run_id: str | None, exit_code: int, panels: _Panels
) -> _MemoryJournal:
    journal = _MemoryJournal()
    envelope = (
        build_success({"ok": True}, envelope_run_id)
        if exit_code in (0, 1)
        else build_failure(ConfigError("falhou"))
    )
    now = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
    record_invocation(
        store=journal,
        app=build_app(),
        argv=argv,
        state=CliState(json_mode=True),
        envelopes=[envelope],
        exit_code=exit_code,
        started_at=now,
        finished_at=now,
        panels=panels,
    )
    return journal


def test_depois_de_gravar_o_run_o_painel_e_refeito_para_incluir_o_proprio_comando(
    tmp_path: Path,
) -> None:
    panels = _Panels()
    run_id = "2026-11-14T10-00-00Z-clinica-aaaa"

    journal = _record(["run", "clinica", "--products-dir", str(tmp_path)], run_id, 0, panels)

    assert panels.calls == [("clinica", run_id, tmp_path)]
    assert panels.journals == [journal]


def test_report_e_panel_com_sucesso_tambem_refazem_o_painel() -> None:
    panels = _Panels()
    run_id = "2026-11-14T10-00-00Z-clinica-aaaa"

    _record(["report", "clinica", "--run", run_id], run_id, 0, panels)
    _record(["panel", "clinica", "--run", run_id], run_id, 0, panels)

    assert [call[:2] for call in panels.calls] == [("clinica", run_id)] * 2


def test_comando_que_nao_gera_painel_ou_falhou_nao_refaz_nada() -> None:
    panels = _Panels()
    run_id = "2026-11-14T10-00-00Z-clinica-aaaa"

    _record(["probe", "clinica"], run_id, 0, panels)
    _record(["report", "clinica", "--run", run_id], None, 3, panels)
    _record(["panel", "--index"], None, 0, panels)

    assert panels.calls == []


def test_falha_ao_refazer_o_painel_nunca_derruba_o_comando() -> None:
    def broken(products_dir: Path | None, journal: CommandJournalStore | None) -> _Panels:
        raise ConfigError("sem fuso")

    journal = _MemoryJournal()
    now = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
    run_id = "2026-11-14T10-00-00Z-clinica-aaaa"

    record_invocation(
        store=journal,
        app=build_app(),
        argv=["run", "clinica"],
        state=CliState(json_mode=True),
        envelopes=[build_success({}, run_id)],
        exit_code=0,
        started_at=now,
        finished_at=now,
        panels=broken,
    )

    assert len(journal.saved) == 1

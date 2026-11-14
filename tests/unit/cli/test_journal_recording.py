import json
import os
from datetime import UTC, datetime
from pathlib import Path

import typer
from typer.core import TyperGroup

from harness_dast.adapters.storage.command_journal import FileCommandJournalStore
from harness_dast.application.command_journal import load_journal_for_run
from harness_dast.application.ports import CommandJournalStore
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.journal_recording import describe_invocation
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

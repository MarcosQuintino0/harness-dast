"""Do diário de comandos para o painel: etapa por regra fixa, comando cru, resposta resumida."""

from datetime import UTC, datetime, timedelta

import pytest

from harness_dast.domain.command_journal import JournalEntry, JournalFlag
from harness_dast.domain.command_translation import translate_command, translated_commands
from harness_dast.domain.panel_journal import (
    build_journal,
    command_line,
    response_text,
    stage_of_command,
    to_panel_command,
)

T0 = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)


def entry(command: str = "probe", **changes: object) -> JournalEntry:
    base: dict[str, object] = {
        "started_at": T0,
        "finished_at": T0 + timedelta(seconds=21),
        "command": command,
        "product": "clinica",
        "exit_code": 0,
        "state": "ok",
    }
    base.update(changes)
    return JournalEntry.model_validate(base)


@pytest.mark.parametrize(
    ("command", "stage"),
    [
        ("preflight", "preflight"),
        ("probe", "probe"),
        ("scan", "scan"),
        ("run", "scan"),
        ("authz", "authz"),
        ("report", "report"),
        ("panel", "report"),
        ("doctor", None),
        ("init", None),
        ("profile validate", None),
        ("spec inspect", None),
        ("stack up", None),
        ("secret list", None),
    ],
)
def test_stage_of_command_follows_the_fixed_table(command: str, stage: str | None) -> None:
    assert stage_of_command(command) == stage


def test_every_translated_command_has_a_stage_rule_or_is_preparation() -> None:
    # Garante que um comando novo na tabela de tradução passe pela decisão de etapa: o que não
    # está na tabela de etapas é preparação, e isso é dito aqui, em um lugar só.
    staged = {name for name in translated_commands() if stage_of_command(name) is not None}

    assert staged == {"preflight", "probe", "scan", "run", "authz", "report", "panel"}


def test_command_line_is_the_command_as_typed() -> None:
    line = command_line(
        entry(
            "probe",
            args=("a b",),
            flags=(JournalFlag(name="--seed", value="7"), JournalFlag(name="--dry-run")),
        )
    )

    assert line == 'hdast probe clinica "a b" --seed 7 --dry-run'


def test_command_line_without_product_has_no_gap() -> None:
    assert command_line(entry("stack up", product=None)) == "hdast stack up"


def test_the_flag_value_that_the_diary_masked_stays_masked() -> None:
    line = command_line(entry("secret set", flags=(JournalFlag(name="--value", value="***"),)))

    assert "--value ***" in line


def test_response_text_has_the_exit_code_and_the_summary_lines() -> None:
    text = response_text(entry(summary={"status": "completed", "successes": 24, "ok": True}))

    assert text.splitlines() == [
        "código de saída: 0",
        'status: "completed"',
        "successes: 24",
        "ok: true",
    ]


def test_response_text_explains_the_error_code_in_plain_words() -> None:
    text = response_text(
        entry("preflight", exit_code=3, state="erro", error_code="PREFLIGHT_FAILED")
    )

    assert "erro: PREFLIGHT_FAILED" in text
    assert "As contas de teste não conseguiram entrar." in text


def test_an_unknown_error_code_is_said_honestly() -> None:
    text = response_text(entry(exit_code=9, state="erro", error_code="NOVO_ERRO"))

    assert "erro: NOVO_ERRO" in text
    assert "Erro sem explicação cadastrada" in text


def test_to_panel_command_fills_every_field_from_the_entry() -> None:
    command = to_panel_command(entry("probe", state="parcial", exit_code=2, error_code="X"))

    assert command.at == T0
    assert command.stage == "probe"
    assert command.command == "hdast probe clinica"
    assert command.translation == translate_command("probe")
    assert command.status == "partial"
    assert command.seconds == 21.0
    assert command.tokens is None
    assert command.output.startswith("código de saída: 2")


@pytest.mark.parametrize(
    ("state", "status"), [("ok", "ok"), ("parcial", "partial"), ("erro", "error")]
)
def test_the_state_words_map_to_the_panel_statuses(state: str, status: str) -> None:
    assert to_panel_command(entry(state=state)).status == status


def test_build_journal_keeps_the_order_and_the_skipped_count() -> None:
    journal = build_journal((entry("doctor"), entry("probe")), 3)

    assert journal is not None
    assert [item.stage for item in journal.commands] == [None, "probe"]
    assert journal.skipped_lines == 3


def test_build_journal_is_none_without_commands() -> None:
    assert build_journal((), 5) is None

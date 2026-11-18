"""Contrato dos painéis da ajuda principal do hdast."""

import re

from typer.core import TyperCommand, TyperGroup
from typer.main import get_command
from typer.testing import CliRunner

from harness_dast.cli.app import (
    ADVANCED_PANEL,
    REGISTRATION_AND_SCOPE_PANEL,
    RESULTS_AND_RETEST_PANEL,
    START_HERE_PANEL,
    TEST_STAGES_PANEL,
    build_app,
)

EXPECTED_COMMANDS = frozenset(
    {
        "authz",
        "cleanup",
        "confirm",
        "doctor",
        "finding",
        "init",
        "knowledge",
        "mutation",
        "negative",
        "panel",
        "plan",
        "preflight",
        "probe",
        "profile",
        "report",
        "run",
        "scan",
        "secret",
        "spec",
        "stack",
        "stop",
        "strategy",
        "version",
        "wait",
    }
)


def test_every_root_command_has_a_help_panel() -> None:
    root = get_command(build_app())
    assert isinstance(root, TyperGroup)
    expected_panels = {
        START_HERE_PANEL,
        REGISTRATION_AND_SCOPE_PANEL,
        TEST_STAGES_PANEL,
        RESULTS_AND_RETEST_PANEL,
        ADVANCED_PANEL,
    }

    for name, command in root.commands.items():
        assert isinstance(command, (TyperCommand, TyperGroup))
        assert command.rich_help_panel in expected_panels, name


def test_start_here_is_the_first_command_panel_in_help() -> None:
    result = CliRunner().invoke(build_app(), ["--help"])

    assert result.exit_code == 0, result.output
    panels = re.findall(r"^[┌╭+][─-]+ (.+?) [─-]+", result.output, re.MULTILINE)
    command_panels = [panel for panel in panels if panel != "Options"]
    assert command_panels[:1] == ["Comece por aqui"]


def test_root_command_names_match_the_fixed_contract() -> None:
    root = get_command(build_app())

    assert isinstance(root, TyperGroup)
    assert root.commands.keys() == EXPECTED_COMMANDS

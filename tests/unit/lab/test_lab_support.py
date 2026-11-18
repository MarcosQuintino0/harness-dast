"""Exercita a coleta e a recriação da pilha com estado e comandos fictícios."""

import json
import warnings
from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.integration.lab_support import CliResult, LabCli, ProxyWatchLatch, stack_suffix
from tests.integration.proxy_watch_log import WatchResult, extract_categories

PROJECT = "hdast-teste"
LATCH = '{"event":"gate_watch_latch","category":"hash","detail":"valor bruto do log"}'


class FakeStackCommand:
    """Registra os comandos da CLI e remove o estado quando a pilha desce."""

    def __init__(self, root: Path) -> None:
        self.state_path = root / "state" / "stack.json"
        self.commands: list[tuple[tuple[str, ...], int]] = []
        self.up_result = CliResult(0, {"data": {"run_id": "nova-pilha"}}, "", "")

    def __call__(self, *args: str, timeout: int) -> CliResult:
        self.commands.append((args, timeout))
        if args == ("stack", "down"):
            self.state_path.unlink(missing_ok=True)
            return CliResult(0, {}, "", "")
        assert args[:2] == ("stack", "up")
        return self.up_result


class FakeWatchReader:
    """Aplica o extrator real aos logs sintéticos de cada projeto."""

    def __init__(self, logs_by_project: Mapping[str, str]) -> None:
        self.logs_by_project = logs_by_project

    def __call__(self, env: Mapping[str, str], project: str) -> WatchResult:
        return {"status": "ok", "categories": extract_categories(self.logs_by_project[project])}


def write_stack_state(cli: LabCli, run_id: str) -> None:
    (cli.state / "stack.json").write_text(
        json.dumps({"run_id": run_id, "projects": [{"name": PROJECT}]}),
        encoding="utf-8",
    )


def test_skips_record_quando_estado_ausente(tmp_path: Path) -> None:
    cli = LabCli(
        tmp_path, {}, watch_reader=FakeWatchReader({}), stack_command=FakeStackCommand(tmp_path)
    )

    cli.stack_down()

    assert not (tmp_path / "proxy-watch.jsonl").exists()


@pytest.mark.parametrize(
    "state",
    ['{"projects":', "[]", '{"projects":[]}', '{"projects":[{"name":[]}],"run_id":"pilha"}'],
    ids=["json", "objeto", "lista_vazia", "nome_invalido"],
)
def test_skips_record_quando_estado_malformado(tmp_path: Path, state: str) -> None:
    cli = LabCli(
        tmp_path, {}, watch_reader=FakeWatchReader({}), stack_command=FakeStackCommand(tmp_path)
    )
    (cli.state / "stack.json").write_text(state, encoding="utf-8")

    cli.stack_down()

    assert not (tmp_path / "proxy-watch.jsonl").exists()


def test_records_one_line_per_stack_quando_duas_pilhas_descem(tmp_path: Path) -> None:
    cli = LabCli(
        tmp_path,
        {},
        watch_reader=FakeWatchReader({PROJECT: ""}),
        stack_command=FakeStackCommand(tmp_path),
    )

    write_stack_state(cli, "primeira")
    cli.stack_down()
    write_stack_state(cli, "segunda")
    cli.stack_down()

    lines = (tmp_path / "proxy-watch.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [
        {"stack_run_id": "primeira", "status": "ok", "categories": []},
        {"stack_run_id": "segunda", "status": "ok", "categories": []},
    ]


def test_warns_quando_existe_categoria(tmp_path: Path) -> None:
    cli = LabCli(
        tmp_path,
        {},
        watch_reader=FakeWatchReader({PROJECT: LATCH}),
        stack_command=FakeStackCommand(tmp_path),
    )
    write_stack_state(cli, "pilha")

    with pytest.warns(ProxyWatchLatch, match="pilha: hash"):
        cli.stack_down()


def test_does_not_warn_quando_categoria_ausente(tmp_path: Path) -> None:
    cli = LabCli(
        tmp_path,
        {},
        watch_reader=FakeWatchReader({PROJECT: ""}),
        stack_command=FakeStackCommand(tmp_path),
    )
    write_stack_state(cli, "pilha")

    with warnings.catch_warnings():
        warnings.simplefilter("error", ProxyWatchLatch)
        cli.stack_down()


def test_still_removes_stack_quando_aviso_vira_erro(tmp_path: Path) -> None:
    command = FakeStackCommand(tmp_path)
    cli = LabCli(
        tmp_path, {}, watch_reader=FakeWatchReader({PROJECT: LATCH}), stack_command=command
    )
    write_stack_state(cli, "pilha")

    with warnings.catch_warnings():
        warnings.simplefilter("error", ProxyWatchLatch)
        with pytest.raises(ProxyWatchLatch):
            cli.stack_down()

    assert not command.state_path.exists()


def test_records_only_sanitized_fields_quando_log_contem_dados_brutos(tmp_path: Path) -> None:
    cli = LabCli(
        tmp_path,
        {},
        watch_reader=FakeWatchReader({PROJECT: LATCH}),
        stack_command=FakeStackCommand(tmp_path),
    )
    write_stack_state(cli, "pilha")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProxyWatchLatch)
        cli.stack_down()

    assert json.loads((tmp_path / "proxy-watch.jsonl").read_text(encoding="utf-8")) == {
        "stack_run_id": "pilha",
        "status": "ok",
        "categories": ["hash"],
    }


def test_runs_down_before_up_quando_pilha_recriada(tmp_path: Path) -> None:
    command = FakeStackCommand(tmp_path)
    cli = LabCli(tmp_path, {}, watch_reader=FakeWatchReader({}), stack_command=command)

    cli.restack("vampi", "--secure", timeout=600)

    assert command.commands == [
        (("stack", "down"), 240),
        (("stack", "up", "vampi", "--secure"), 600),
    ]


def test_returns_up_result_quando_pilha_recriada(tmp_path: Path) -> None:
    command = FakeStackCommand(tmp_path)
    cli = LabCli(tmp_path, {}, watch_reader=FakeWatchReader({}), stack_command=command)

    result = cli.restack("vampi")

    assert result == command.up_result


def test_returns_empty_suffix_quando_variavel_ausente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HDAST_IT_STACK_SUFFIX", raising=False)

    assert stack_suffix() == ""


def test_returns_configured_suffix_quando_variavel_definida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HDAST_IT_STACK_SUFFIX", "-t3")

    assert stack_suffix() == "-t3"

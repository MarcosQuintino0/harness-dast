import importlib.util
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[2] / ".github" / "scripts" / "lab_summary.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lab_summary", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _piece(
    artifacts: Path,
    name: str,
    cases: str | None,
    watch: Sequence[Mapping[str, object]] | None = None,
) -> None:
    directory = artifacts / f"lab-{name}"
    directory.mkdir(parents=True)
    if cases is not None:
        (directory / "junit.xml").write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")
    if watch is not None:
        (directory / "vigia").mkdir()
        lines = "\n".join(json.dumps(record) for record in watch)
        (directory / "vigia" / "0.jsonl").write_text(lines + "\n", encoding="utf-8")


def _run(tmp_path: Path, names: list[str]) -> tuple[int, str]:
    planned = tmp_path / "pedacos.json"
    planned.write_text(json.dumps([{"name": name} for name in names]), encoding="utf-8")
    summary = tmp_path / "summary.md"
    code = _load().main(
        ["--artefatos", str(tmp_path / "art"), "--pedacos", str(planned), "--saida", str(summary)]
    )
    return code, summary.read_text(encoding="utf-8")


def test_resume_aprovados_quando_todos_os_pedacos_passam(tmp_path: Path) -> None:
    art = tmp_path / "art"
    _piece(art, "a", '<testcase classname="x" name="um" time="1.5"/>')
    _piece(art, "b", '<testcase name="dois" time="0.5"/>')

    code, report = _run(tmp_path, ["a", "b"])

    assert code == 0
    assert "2 aprovados · 0 falharam · 0 pulados · 2 pedaços" in report
    assert report.index("1.50 s") < report.index("0.50 s")


def test_falha_quando_ha_teste_com_erro_ou_falha(tmp_path: Path) -> None:
    art = tmp_path / "art"
    _piece(
        art,
        "a",
        '<testcase name="ok" time="1"/><testcase name="ruim" time="2"><error/></testcase>'
        '<testcase name="pulou"><skipped/></testcase>',
    )

    code, report = _run(tmp_path, ["a"])

    assert code == 1
    assert "1 aprovados · 1 falharam · 1 pulados" in report
    assert "falhou" in report


def test_conta_como_falha_quando_pedaco_nao_tem_junit(tmp_path: Path) -> None:
    art = tmp_path / "art"
    _piece(art, "a", '<testcase name="ok" time="1"/>')
    _piece(art, "b", None)

    code, report = _run(tmp_path, ["a", "b", "c"])

    assert code == 1
    assert "Pedaços sem resultado" in report
    assert "<code>b</code>" in report
    assert "<code>c</code>" in report
    assert "sem resultado" in report


def test_falha_quando_nenhum_teste_passou(tmp_path: Path) -> None:
    art = tmp_path / "art"
    _piece(art, "a", '<testcase name="pulou"><skipped/></testcase>')

    code, report = _run(tmp_path, ["a"])

    assert code == 1
    assert "só pulados" in report


def test_lista_so_os_quinze_mais_lentos_quando_ha_mais_testes(tmp_path: Path) -> None:
    art = tmp_path / "art"
    cases = "".join(f'<testcase name="t{i}" time="{i}"/>' for i in range(1, 21))
    _piece(art, "a", cases)

    _, report = _run(tmp_path, ["a"])

    slow = report.split("mais lentos")[1].split("###")[0]
    assert slow.count("<code>") == 15
    assert "t20" in slow
    assert "t5<" not in slow


def test_registra_travas_da_vigia_quando_ha_categorias_ou_status_ruim(tmp_path: Path) -> None:
    art = tmp_path / "art"
    watch = [
        {"stack_run_id": "s1", "categories": ["profile_changed"], "status": "ok"},
        {"stack_run_id": "s2", "categories": [], "status": "stale"},
        {"stack_run_id": "s3", "categories": [], "status": "ok"},
    ]
    _piece(art, "a", '<testcase name="ok" time="1"/>', watch)

    _, report = _run(tmp_path, ["a"])

    assert "pilha <code>s1</code> · <code>profile_changed</code>" in report
    assert "pilha <code>s2</code> · <code>stale</code>" in report
    assert "s3" not in report
    assert "3 registros da vigia coletados, 2 com trava ou aviso" in report


def test_ignora_junit_malformado_quando_arquivo_esta_quebrado(tmp_path: Path) -> None:
    art = tmp_path / "art"
    directory = art / "lab-a"
    directory.mkdir(parents=True)
    (directory / "junit.xml").write_text("<testsuite", encoding="utf-8")

    code, report = _run(tmp_path, ["a"])

    assert code == 1
    assert "Pedaços sem resultado" in report


def test_recusa_lista_de_pedacos_quando_json_esta_invalido(tmp_path: Path) -> None:
    planned = tmp_path / "pedacos.json"
    planned.write_text("{", encoding="utf-8")

    code = _load().main(["--artefatos", str(tmp_path), "--pedacos", str(planned)])

    assert code == 2


@pytest.mark.parametrize("body", ['[{"nome": "a"}]', '["a"]'])
def test_recusa_lista_de_pedacos_quando_falta_o_nome(tmp_path: Path, body: str) -> None:
    planned = tmp_path / "pedacos.json"
    planned.write_text(body, encoding="utf-8")

    assert _load().main(["--artefatos", str(tmp_path), "--pedacos", str(planned)]) == 2

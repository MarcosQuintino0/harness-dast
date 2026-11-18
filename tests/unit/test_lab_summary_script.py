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
    state: str | None = "success",
) -> None:
    directory = artifacts / f"lab-{name}"
    directory.mkdir(parents=True)
    if cases is not None:
        (directory / "junit.xml").write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")
    if state is not None:
        (directory / "estado.json").write_text(json.dumps({"status": state}), encoding="utf-8")
    if watch is not None:
        (directory / "vigia").mkdir()
        lines = "\n".join(json.dumps(record) for record in watch)
        (directory / "vigia" / "0.jsonl").write_text(lines + "\n", encoding="utf-8")


def _run(tmp_path: Path, names: list[str], job_result: str | None = None) -> tuple[int, str]:
    planned = tmp_path / "pedacos.json"
    planned.write_text(json.dumps([{"name": name} for name in names]), encoding="utf-8")
    summary = tmp_path / "summary.md"
    argv = [
        "--artefatos",
        str(tmp_path / "art"),
        "--pedacos",
        str(planned),
        "--saida",
        str(summary),
    ]
    if job_result is not None:
        argv += ["--resultado-pedaco", job_result]
    code = _load().main(argv)
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
    assert "1 testes falharam" in report


def test_conta_como_falha_quando_pedaco_nao_tem_junit(tmp_path: Path) -> None:
    art = tmp_path / "art"
    _piece(art, "a", '<testcase name="ok" time="1"/>')
    _piece(art, "b", None)

    code, report = _run(tmp_path, ["a", "b", "c"])

    assert code == 1
    assert "Pedaços com falha" in report
    assert "<code>b</code>: sem junit" in report
    assert "<code>c</code>: sem artefato" in report


def test_falha_quando_nenhum_teste_passou(tmp_path: Path) -> None:
    art = tmp_path / "art"
    _piece(art, "a", '<testcase name="pulou"><skipped/></testcase>')

    code, report = _run(tmp_path, ["a"])

    assert code == 1
    assert "nenhum teste aprovado (1 pulados)" in report


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
    assert "sem junit" in report


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


def test_falha_quando_job_do_pedaco_nao_terminou_com_sucesso(tmp_path: Path) -> None:
    art = tmp_path / "art"
    _piece(art, "a", '<testcase name="ok" time="1"/>', state="failure")

    code, report = _run(tmp_path, ["a"])

    assert code == 1
    assert "job terminou como failure" in report


def test_falha_quando_estado_nao_foi_gravado(tmp_path: Path) -> None:
    art = tmp_path / "art"
    _piece(art, "a", '<testcase name="ok" time="1"/>', state=None)

    code, report = _run(tmp_path, ["a"])

    assert code == 1
    assert "sem estado.json" in report


def test_falha_quando_um_pedaco_so_tem_pulados_e_outro_passou(tmp_path: Path) -> None:
    art = tmp_path / "art"
    _piece(art, "a", '<testcase name="ok" time="1"/>')
    _piece(
        art,
        "b",
        '<testcase name="p1"><skipped/></testcase><testcase name="p2"><skipped/></testcase>',
    )

    code, report = _run(tmp_path, ["a", "b"])

    assert code == 1
    assert "<code>b</code>: nenhum teste aprovado (2 pulados)" in report


@pytest.mark.parametrize("job_result", ["failure", "cancelled", "skipped"])
def test_falha_quando_resultado_do_job_pedaco_nao_e_sucesso(
    tmp_path: Path, job_result: str
) -> None:
    art = tmp_path / "art"
    _piece(art, "a", '<testcase name="ok" time="1"/>')

    code, report = _run(tmp_path, ["a"], job_result)

    assert code == 1
    assert job_result in report


def test_aprova_quando_job_pedaco_teve_sucesso(tmp_path: Path) -> None:
    art = tmp_path / "art"
    _piece(art, "a", '<testcase name="ok" time="1"/>')

    code, _ = _run(tmp_path, ["a"], "success")

    assert code == 0


def test_grava_estado_com_status_e_contagens_quando_pedaco_termina(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuite><testcase name="a"/><testcase name="b"><failure/></testcase>'
        '<testcase name="c"><skipped/></testcase></testsuite>',
        encoding="utf-8",
    )
    estado = tmp_path / "saida" / "estado.json"

    code = _load().main(
        [
            "--gravar-estado",
            str(estado),
            "--nome",
            "p1",
            "--status",
            "failure",
            "--junit",
            str(junit),
        ]
    )

    assert code == 0
    assert json.loads(estado.read_text(encoding="utf-8")) == {
        "nome": "p1",
        "status": "failure",
        "passed": 1,
        "failed": 1,
        "skipped": 1,
    }


def test_grava_estado_zerado_quando_nao_ha_junit(tmp_path: Path) -> None:
    estado = tmp_path / "estado.json"

    code = _load().main(
        [
            "--gravar-estado",
            str(estado),
            "--nome",
            "p",
            "--status",
            "cancelled",
            "--junit",
            str(tmp_path / "nada.xml"),
        ]
    )

    assert code == 0
    assert json.loads(estado.read_text(encoding="utf-8"))["passed"] == 0


def test_recusa_gravar_estado_quando_faltam_argumentos(tmp_path: Path) -> None:
    assert _load().main(["--gravar-estado", str(tmp_path / "e.json")]) == 2
    assert _load().main([]) == 2

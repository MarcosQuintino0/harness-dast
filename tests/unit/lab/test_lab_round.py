"""Valida a seleção e a trava da rodada com arquivos temporários e sem Docker."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from textwrap import dedent
from uuid import UUID

import pytest

from harness_dast.domain.errors import ConfigError, ExitCode
from tests.integration import lab_round
from tests.integration.lab_round import (
    INTEGRATION,
    MAP,
    AreaMap,
    LabBusy,
    Selection,
    _run_pytest,
    build_command,
    lab_lock,
    load_map,
    main,
    select_changed,
    select_level,
)


@pytest.fixture
def areas(tmp_path: Path) -> AreaMap:
    mapping = tmp_path / "areas.toml"
    mapping.write_text(
        dedent("""\
            shared = ["tests/integration/lab_support.py"]

            [areas.scope]
            name = "Cerca"
            paths = ["src/scope/**"]
            fast = ["test_scope.py"]
            prova = ["test_scope_proof.py"]

            [areas.scan]
            name = "Scan"
            paths = ["src/scan.py", "src/scope/shared.py"]
            fast = ["test_scope.py", "test_scan.py"]
            prova = ["test_scan_proof.py"]
        """),
        encoding="utf-8",
    )
    return load_map(mapping)


@pytest.mark.parametrize(
    "content",
    [None, b"[areas", b"\xff", b"areas = []", b"shared = []\n[areas]\n"],
    ids=["ausente", "sintaxe", "codificacao", "tipo", "sem-areas"],
)
def test_rejeita_mapa_quando_ausente_ou_invalido(tmp_path: Path, content: bytes | None) -> None:
    path = tmp_path / "areas.toml"
    if content is not None:
        path.write_bytes(content)

    with pytest.raises(ConfigError, match="Não foi possível ler o mapa"):
        load_map(path)


@pytest.mark.parametrize("path", ["src/sem_area.py", "tests/integration/lab_support.py"])
def test_seleciona_nucleo_quando_mudanca_sem_area_ou_compartilhada(
    areas: AreaMap, path: str
) -> None:
    assert select_changed(areas, [path]) == Selection(
        "lab_fast", ("tests/integration/test_scan.py", "tests/integration/test_scope.py")
    )


def test_soma_areas_sem_repetir_arquivos_quando_o_caminho_afeta_mais_de_uma(areas: AreaMap) -> None:
    changes = ["src/scope/shared.py", "docs/desenvolver/testing.md"]

    assert select_changed(areas, changes) == Selection(
        "lab_fast or lab_prova",
        (
            "tests/integration/test_scan.py",
            "tests/integration/test_scan_proof.py",
            "tests/integration/test_scope.py",
            "tests/integration/test_scope_proof.py",
        ),
    )


def test_preserva_prova_da_area_quando_outra_mudanca_cai_no_nucleo(areas: AreaMap) -> None:
    assert select_changed(areas, ["src/scope/guard.py", "src/sem_area.py"]) == Selection(
        "lab_fast or lab_prova",
        (
            "tests/integration/test_scan.py",
            "tests/integration/test_scope.py",
            "tests/integration/test_scope_proof.py",
        ),
    )


@pytest.mark.parametrize(
    ("path", "proof_areas"),
    [
        ("tests/integration/lab_proof_support.py", ("authz", "negative", "crapi", "extra")),
        ("src/harness_dast/adapters/docker/compose.py", ("stack",)),
        ("compose.yaml", ("stack",)),
        ("src/harness_dast/adapters/scope_proxy/policy.py", ("scope",)),
        ("lab/crapi/compose.oast.yaml", ("crapi", "oast", "stack")),
        ("docker/zap/Dockerfile", ("scan", "stack")),
    ],
)
def test_seleciona_nucleo_e_provas_quando_muda_apoio_compartilhado(
    path: str, proof_areas: tuple[str, ...]
) -> None:
    mapping = load_map(MAP)
    files = set(mapping.files("fast"))
    for area in proof_areas:
        files.update(mapping.areas[area].prova)

    assert select_changed(mapping, [path]) == Selection(
        "lab_fast or lab_prova", tuple(f"{INTEGRATION}/{name}" for name in sorted(files))
    )


def test_seleciona_so_a_area_quando_muda_o_caso_de_uso_de_valores_proibidos() -> None:
    mapping = load_map(MAP)
    negative = mapping.areas["negative"]

    assert select_changed(mapping, ["src/harness_dast/application/negative.py"]) == Selection(
        "lab_fast or lab_prova",
        tuple(f"{INTEGRATION}/{name}" for name in sorted(set((*negative.fast, *negative.prova)))),
    )


def test_seleciona_todas_as_provas_quando_muda_apoio_geral() -> None:
    mapping = load_map(MAP)
    files = sorted(set(mapping.files("fast")).union(mapping.files("prova")))

    assert select_changed(mapping, ["tests/integration/lab_support.py"]) == Selection(
        "lab_fast or lab_prova", tuple(f"{INTEGRATION}/{name}" for name in files)
    )


def test_seleciona_area_quando_muda_um_teste_do_mapa(areas: AreaMap) -> None:
    assert select_changed(areas, ["tests/integration/test_scope_proof.py"]) == Selection(
        "lab_fast or lab_prova",
        ("tests/integration/test_scope.py", "tests/integration/test_scope_proof.py"),
    )


def test_pula_laboratorio_quando_so_mudou_documentacao(areas: AreaMap) -> None:
    docs = ["docs/desenvolver/testing.md", "docs/desenvolver/design/preview.html", "CHANGELOG.md"]

    assert select_changed(areas, docs) is None


def test_recusa_trava_existente_quando_lab_esta_ocupado(tmp_path: Path) -> None:
    path = tmp_path / "lab.lock"
    original = "dono: coordenação\n"
    path.write_text(original, encoding="utf-8")

    with (
        pytest.raises(LabBusy, match="coordenação"),
        lab_lock(path, "T4", datetime(2026, 11, 18, tzinfo=UTC), "fast"),
    ):
        pytest.fail("Entrou no laboratório com uma trava existente")
    assert path.read_text(encoding="utf-8") == original


def test_registra_metadados_quando_aquisicao_da_trava_funciona(tmp_path: Path) -> None:
    path = tmp_path / "lab.lock"
    started = datetime(2026, 11, 18, tzinfo=UTC)

    with lab_lock(path, "T4", started, "prova"):
        line, _, metadata = path.read_text(encoding="utf-8").partition("\n")
        assert line.startswith("token: ")
        assert UUID(line.removeprefix("token: ")).version == 4
        assert metadata == "dono: T4\nUTC: 2026-11-18T00:00:00+00:00\nnível: prova\n"
    assert not path.exists()


def test_libera_trava_propria_quando_rodada_falha(tmp_path: Path) -> None:
    path = tmp_path / "lab.lock"
    started = datetime(2026, 11, 18, tzinfo=UTC)

    with (
        pytest.raises(RuntimeError, match="falha sintética"),
        lab_lock(path, "T4", started, "prova"),
    ):
        raise RuntimeError("falha sintética")

    assert not path.exists()


def test_preserva_trava_quando_token_mudou(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "lab.lock"
    foreign = "token: outra rodada\n"
    with lab_lock(path, "T4", datetime(2026, 11, 18, tzinfo=UTC), "fast"):
        path.write_text(foreign, encoding="utf-8")

    assert path.read_text(encoding="utf-8") == foreign
    assert "mudou de identidade ou token" in capsys.readouterr().err


def test_avisa_quando_a_trava_sumiu(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "lab.lock"

    def missing(_path: Path) -> os.stat_result:
        raise FileNotFoundError(path)

    with lab_lock(path, "T4", datetime(2026, 11, 18, tzinfo=UTC), "fast"):
        # No Windows a remoção real é recusada enquanto o arquivo está aberto.
        monkeypatch.setattr(Path, "lstat", missing)

    assert "sumiu durante a rodada" in capsys.readouterr().err


def test_libera_so_a_propria_trava_quando_a_escrita_dos_metadados_falha(tmp_path: Path) -> None:
    path = tmp_path / "lab.lock"
    other = tmp_path / "outra.lock"
    other.write_text("dono: outra rodada", encoding="utf-8")

    with (
        pytest.raises(UnicodeEncodeError),
        lab_lock(path, "\ud800", datetime(2026, 11, 18, tzinfo=UTC), "fast"),
    ):
        pytest.fail("Entrou no laboratório sem gravar os metadados da trava")

    assert not path.exists()
    assert other.read_text(encoding="utf-8") == "dono: outra rodada"


@pytest.mark.skipif(os.name == "nt", reason="Windows bloqueia a renomeação da trava aberta")
def test_preserva_trava_de_terceiro_quando_a_original_ja_saiu(tmp_path: Path) -> None:
    path = tmp_path / "lab.lock"
    moved = tmp_path / "lab-antigo.lock"
    with lab_lock(path, "T4", datetime(2026, 11, 18, tzinfo=UTC), "fast"):
        path.rename(moved)
        path.write_text("dono: outra rodada\n", encoding="utf-8")

    assert path.read_text(encoding="utf-8") == "dono: outra rodada\n"


@pytest.mark.skipif(os.name != "nt", reason="O Windows bloqueia a remoção de arquivos abertos")
def test_windows_bloqueia_remocao_enquanto_a_rodada_mantem_a_trava_aberta(tmp_path: Path) -> None:
    path = tmp_path / "lab.lock"
    with (
        lab_lock(path, "T4", datetime(2026, 11, 18, tzinfo=UTC), "fast"),
        pytest.raises(PermissionError),
    ):
        path.unlink()

    assert not path.exists()


def test_monta_comando_quando_recebe_selecao_e_diretorio(tmp_path: Path) -> None:
    selection = Selection("lab_fast or lab_prova", ("tests/integration/test_scan.py",))

    assert build_command(selection, tmp_path / "com espaço") == (
        sys.executable,
        "-m",
        "pytest",
        *selection.paths,
        "-m",
        selection.marker,
        f"--junitxml={tmp_path / 'com espaço' / 'junit.xml'}",
        "--durations=30",
        "-rfE",
    )


def test_grava_log_e_metricas_quando_processo_de_teste_falha(tmp_path: Path) -> None:
    output = tmp_path / "rodada com espaço"
    command = (
        sys.executable,
        "-c",
        "import os, sys\n"
        "print(os.environ['HDAST_IT_STACK_SUFFIX'])\n"
        "print(os.environ['HDAST_IT_METRICS_DIR'])\n"
        "print('erro do filho', file=sys.stderr)\n"
        "sys.exit(7)\n",
    )

    assert _run_pytest(command, output, "-t4") == 7
    lines = (output / "pytest.log").read_text(encoding="utf-8").splitlines()
    assert set(lines) == {"-t4", str(output / "metricas"), "erro do filho"}
    assert (output / "metricas").is_dir()


def test_dry_run_quando_saida_e_trava_sao_temporarias(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output, lock = tmp_path / "rodada", tmp_path / "lab.lock"

    result = main(["--nivel", "fast", "--dry-run", "--saida", str(output), "--trava", str(lock)])

    assert result == ExitCode.OK
    assert "test_lab_fast.py" in capsys.readouterr().out
    assert not output.exists()
    assert not lock.exists()


def test_dry_run_quando_seleciona_arquivo_e_modo(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(
        [
            "--nivel",
            "fast",
            "--arquivo",
            "test_lab_multipart.py",
            "--k",
            "[secure]",
            "--dry-run",
        ]
    )

    assert result == ExitCode.OK
    command, _, selected = capsys.readouterr().out.splitlines()
    assert "-m lab_fast -k" in command
    assert "[secure]" in command
    assert selected.strip() == "tests/integration/test_lab_multipart.py"


def test_rejects_file_quando_pertence_a_outro_nivel(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(["--nivel", "fast", "--arquivo", "test_stack_stale_profile.py", "--dry-run"])

    assert result == ExitCode.USAGE
    assert "não pertence à seleção" in capsys.readouterr().err


def _ids(file: str, *params: str, function: str = "test_x") -> list[str]:
    return [f"{INTEGRATION}/{file}::{function}[{param}]" for param in params]


def test_planeja_um_pedaco_por_arquivo_quando_ha_poucos_testes(areas: AreaMap) -> None:
    ids = [*_ids("test_scope.py", "vulnerable", "secure"), *_ids("test_scan.py", "a")]

    pieces = lab_round.plan_pieces("fast", areas, lambda _selection: ids)

    assert [(p.file, p.keyword, p.name) for p in pieces] == [
        ("test_scan.py", None, "fast-scan"),
        ("test_scope.py", None, "fast-scope"),
    ]
    assert [p.index for p in pieces] == [0, 1]


def test_planeja_pedacos_por_modo_quando_arquivo_e_grande(areas: AreaMap) -> None:
    params = [f"{mode}-caso{n}" for mode in ("vulnerable", "secure") for n in range(5)]
    ids = _ids("test_scope.py", *params, function="test_in_secure_mode_x")

    pieces = lab_round.plan_pieces("fast", areas, lambda _selection: ids)

    assert [p.name for p in pieces] == ["fast-scope-vulnerable", "fast-scope-secure"]
    # As agulhas casam só no identificador de parâmetro, nunca no nome da função.
    assert pieces[0].keyword == "([vulnerable or -vulnerable- or -vulnerable])"
    assert "secure" not in (pieces[0].keyword or "")


def test_planeja_resto_quando_ha_testes_sem_modo(areas: AreaMap) -> None:
    ids = [
        *_ids("test_scope.py", *[f"{m}-{n}" for m in ("vulnerable", "secure") for n in range(5)]),
        f"{INTEGRATION}/test_scope.py::test_sem_parametro",
    ]

    pieces = lab_round.plan_pieces("fast", areas, lambda _selection: ids)

    assert [p.name for p in pieces] == [
        "fast-scope-vulnerable",
        "fast-scope-secure",
        "fast-scope-resto",
    ]
    assert (pieces[2].keyword or "").startswith("(not (")


def test_nao_parte_arquivo_quando_teste_casa_dois_valores(areas: AreaMap) -> None:
    ids = _ids("test_scope.py", *[f"vulnerable-secure-{n}" for n in range(10)])

    pieces = lab_round.plan_pieces("fast", areas, lambda _selection: ids)

    assert [(p.name, p.keyword) for p in pieces] == [("fast-scope", None)]


def test_planeja_os_quatro_niveis_quando_pedido_e_tudo(areas: AreaMap) -> None:
    seen: list[str] = []

    def collect(selection: Selection) -> list[str]:
        seen.append(selection.marker)
        return [
            f"{INTEGRATION}/test_scope.py::test_a",
            f"{INTEGRATION}/test_scan_performance_matrix.py::test_b",
        ]

    pieces = lab_round.plan_pieces("tudo", areas, collect)

    assert seen == ["lab_fast", "lab_prova", "regressao_dirigida", "integration or e2e"]
    assert [(p.level, p.file) for p in pieces] == [
        ("fast", "test_scope.py"),
        ("prova", "test_scope.py"),
        ("regressao", "test_scope.py"),
        ("carga", "test_scan_performance_matrix.py"),
        ("carga", "test_scope.py"),
    ]
    assert [p.index for p in pieces] == list(range(len(pieces)))
    # A carga roda a matriz inteira; a prova não a repete.
    assert [p.level for p in pieces if p.file == "test_scan_performance_matrix.py"] == ["carga"]


def test_recusa_pedacos_quando_nivel_e_changed(areas: AreaMap) -> None:
    with pytest.raises(ConfigError, match="changed"):
        lab_round.plan_pieces("changed", areas, lambda _selection: [])


def test_recusa_pedacos_quando_coleta_vem_vazia(areas: AreaMap) -> None:
    with pytest.raises(ConfigError, match="não achou testes"):
        lab_round.plan_pieces("fast", areas, lambda _selection: [])


def test_seleciona_benchmark_e_matriz_quando_nivel_e_carga(areas: AreaMap) -> None:
    selection = select_level("carga", areas)

    assert selection is not None
    assert selection.marker == "integration or e2e"
    assert selection.paths == (
        f"{INTEGRATION}/test_guard_benchmark.py",
        f"{INTEGRATION}/test_scan_performance_matrix.py",
    )


def test_imprime_pedacos_em_json_quando_pedido(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        lab_round,
        "collect_node_ids",
        lambda _selection: [f"{INTEGRATION}/test_lab_fast.py::test_a"],
    )

    result = main(["--nivel", "fast", "--pedacos-json"])

    assert result == ExitCode.OK
    pieces = json.loads(capsys.readouterr().out)
    assert pieces == [
        {
            "index": 0,
            "level": "fast",
            "file": "test_lab_fast.py",
            "keyword": None,
            "name": "fast-lab_fast",
        }
    ]


def test_coleta_so_linhas_de_teste_quando_pytest_responde(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Done:
        returncode = 0
        stdout = "tests/integration/test_a.py::test_x[1]\n\n1 test collected in 0.1s\n"

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: Done())

    ids = lab_round.collect_node_ids(Selection("lab_fast", ("tests/integration",)))

    assert ids == ("tests/integration/test_a.py::test_x[1]",)


def test_recusa_coleta_quando_pytest_falha(monkeypatch: pytest.MonkeyPatch) -> None:
    class Failed:
        returncode = 2
        stdout = "erro de importação"

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: Failed())

    with pytest.raises(ConfigError, match="coleta do pytest falhou"):
        lab_round.collect_node_ids(Selection("lab_fast", ("tests/integration",)))

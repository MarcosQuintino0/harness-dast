"""Valida a seleção e a trava da rodada com arquivos temporários e sem Docker."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from textwrap import dedent

import pytest

from harness_dast.domain.errors import ConfigError, ExitCode
from tests.integration.lab_round import (
    AreaMap,
    LabBusy,
    Selection,
    _run_pytest,
    build_command,
    lab_lock,
    load_map,
    main,
    select_changed,
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
        assert path.read_text(encoding="utf-8") == (
            "dono: T4\nUTC: 2026-11-18T00:00:00+00:00\nnível: prova\n"
        )


def test_libera_trava_propria_quando_rodada_falha(tmp_path: Path) -> None:
    path = tmp_path / "lab.lock"
    started = datetime(2026, 11, 18, tzinfo=UTC)

    with (
        pytest.raises(RuntimeError, match="falha sintética"),
        lab_lock(path, "T4", started, "prova"),
    ):
        raise RuntimeError("falha sintética")

    assert not path.exists()


def test_preserva_trava_de_terceiro_quando_a_original_ja_saiu(tmp_path: Path) -> None:
    path = tmp_path / "lab.lock"
    moved = tmp_path / "lab-antigo.lock"
    with lab_lock(path, "T4", datetime(2026, 11, 18, tzinfo=UTC), "fast"):
        path.rename(moved)
        path.write_text("dono: outra rodada\n", encoding="utf-8")

    assert path.read_text(encoding="utf-8") == "dono: outra rodada\n"


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

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[2] / ".github" / "scripts" / "check_coverage_floors.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_coverage_floors", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_report(tmp_path: Path, files: dict[str, tuple[int, int, int, int]]) -> str:
    report = {
        "files": {
            name: {
                "summary": {
                    "num_statements": s,
                    "covered_lines": cl,
                    "num_branches": b,
                    "covered_branches": cb,
                }
            }
            for name, (s, cl, b, cb) in files.items()
        }
    }
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return str(path)


def _make_layer(root: Path, name: str, *, with_code: bool) -> str:
    layer = root / "src" / "harness_dast" / name
    layer.mkdir(parents=True)
    (layer / "__init__.py").write_text("", encoding="utf-8")
    if with_code:
        (layer / "a.py").write_text("x = 1", encoding="utf-8")
    return f"src/harness_dast/{name}"


def test_floor_passes_when_layer_is_above_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    prefix = _make_layer(tmp_path, "domain", with_code=True)
    report = _write_report(tmp_path, {f"{prefix}/a.py": (10, 10, 10, 10)})

    assert _load().main([report, f"{prefix}=95"]) == 0


def test_floor_fails_when_layer_is_below_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    prefix = _make_layer(tmp_path, "domain", with_code=True)
    report = _write_report(tmp_path, {f"{prefix}/a.py": (10, 10, 10, 5)})

    assert _load().main([report, f"{prefix}=95"]) == 1


def test_floor_is_skipped_when_layer_has_only_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    prefix = _make_layer(tmp_path, "application", with_code=False)
    report = _write_report(tmp_path, {})

    assert _load().main([report, f"{prefix}=85"]) == 0
    assert "piso ignorado" in capsys.readouterr().out


def test_floor_fails_when_prefix_directory_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    report = _write_report(tmp_path, {})

    assert _load().main([report, "src/harness_dast/domian=95"]) == 1
    assert "não existe" in capsys.readouterr().out


def test_floor_fails_when_layer_has_code_but_nothing_was_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    prefix = _make_layer(tmp_path, "domain", with_code=True)
    report = _write_report(tmp_path, {})

    assert _load().main([report, f"{prefix}=95"]) == 1

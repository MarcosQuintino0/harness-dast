"""Executa o hook com um PATH isolado, sem usar uv, Docker ou a CLI reais."""

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

SH = shutil.which("sh")
HOOK = Path(__file__).resolve().parents[3] / "plugin" / "hooks" / "session_start.sh"
VERSION = "1.12.2"
DIGEST = "sha256:" + "a" * 64
IMAGES = ("ghcr.io/exemplo/hdast-zap", "ghcr.io/exemplo/hdast-scope-proxy")
REFS = " ".join(f"{image}:{VERSION}@{DIGEST}" for image in IMAGES)
CALL_TO_ACTION = "Rode /hdast:preparar para resolver."
INFO_ONLY = "Os avisos acima são só informação: o teste pode seguir."

pytestmark = pytest.mark.skipif(SH is None, reason="Shell POSIX sh ausente no ambiente de teste.")


def _shell_path(path: Path) -> str:
    if os.name == "nt":
        return f"/{path.drive[0].lower()}/{path.as_posix()[3:]}"
    return path.as_posix()


def _executable(bin_dir: Path, name: str, body: str) -> None:
    script = bin_dir / name
    script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8", newline="\n")
    script.chmod(0o755)


def _write_lock(tool_dir: Path, *, valid: bool = True) -> None:
    package = "Lib" if os.name == "nt" else "lib/python3.12"
    lock = tool_dir / (
        f"harness-dast/{package}/site-packages/harness_dast/adapters/docker/images.lock.json"
    )
    lock.parent.mkdir(parents=True)
    data = {
        "schema_version": 1,
        "version": VERSION,
        "images": {
            key: {"repository": image, "tag": VERSION, "digest": DIGEST}
            for key, image in zip(("zap", "scope_proxy"), IMAGES, strict=True)
        },
    }
    lock.write_text(json.dumps(data, indent=2) if valid else "{}", encoding="utf-8")


def _run_hook(tmp_path: Path, scenario: str) -> subprocess.CompletedProcess[str]:
    assert SH is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    plugin = tmp_path / "plugin com espaço"
    manifest = plugin / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"version": VERSION}), encoding="utf-8")
    tool_dir = tmp_path / "tools com espaço"
    if scenario != "no_lock":
        _write_lock(tool_dir, valid=scenario != "bad_lock")

    for name in ("sed", "sleep"):
        utility = _utility(name, Path(SH))
        _executable(bin_dir, name, f'exec {shlex.quote(_shell_path(utility))} "$@"')
    if scenario != "no_uv":
        tool_path = shlex.quote(tool_dir.as_posix())
        _executable(bin_dir, "uv", f'[ "$*" = "tool dir" ] && printf "%s\\r\\n" {tool_path}')
    if scenario != "no_hdast":
        version = "0.0.1" if scenario == "wrong_version" else VERSION
        _executable(bin_dir, "hdast", f'[ "$*" = "--version" ] && printf "{version}\\r\\n"')
    if scenario == "no_docker":
        return _launch(bin_dir, plugin)
    info = {"closed": "exit 1", "hung": "exec sleep 30"}.get(scenario, "exit 0")
    inspect = "exit 1" if scenario == "no_image" else f'[ "$*" = "image inspect {REFS}" ]'
    _executable(bin_dir, "docker", f'[ "$*" = "info" ] && {{ {info}; }}\n{inspect}')

    return _launch(bin_dir, plugin)


def _launch(bin_dir: Path, plugin: Path) -> subprocess.CompletedProcess[str]:
    assert SH is not None
    # O shell e o hook são caminhos locais e o PATH contém apenas os dublês.
    return subprocess.run(  # noqa: S603
        [
            SH,
            "-c",
            'PATH=$1; export PATH; exec "$2" "$3"',
            "sh",
            _shell_path(bin_dir),
            _shell_path(Path(SH)),
            _shell_path(HOOK),
        ],
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": _shell_path(plugin)},
        capture_output=True,
        encoding="utf-8",
        timeout=9,
        check=False,
    )


def _utility(name: str, shell: Path) -> Path:
    # Os binários do Git Bash precisam ficar junto das DLLs da instalação original.
    if os.name == "nt":
        adjacent = shell.with_name(f"{name}.exe")
        if adjacent.is_file():
            return adjacent
        return shell.parents[1] / "usr" / "bin" / f"{name}.exe"
    found = shutil.which(name)
    assert found is not None
    return Path(found)


@pytest.mark.parametrize(
    ("scenario", "message"),
    [
        ("no_hdast", "hdast não está no PATH."),
        ("closed", "Docker não responde"),
        ("hung", "Docker não responde"),
    ],
)
def test_session_start_asks_for_preparation_when_something_blocks_the_test(
    tmp_path: Path, scenario: str, message: str
) -> None:
    result = _run_hook(tmp_path, scenario)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert message in result.stdout
    assert result.stdout.splitlines()[-1] == CALL_TO_ACTION


@pytest.mark.parametrize(
    ("scenario", "message"),
    [
        ("no_uv", "uv não está no PATH."),
        ("wrong_version", "A versão do hdast difere da versão do plugin."),
        ("no_image", "Uma ou mais imagens da versão não puderam ser confirmadas"),
        ("bad_lock", "o arquivo de digests da instalação está ilegível"),
    ],
)
def test_session_start_says_test_can_go_on_when_notice_is_only_information(
    tmp_path: Path, scenario: str, message: str
) -> None:
    result = _run_hook(tmp_path, scenario)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert message in result.stdout
    assert CALL_TO_ACTION not in result.stdout
    assert INFO_ONLY in result.stdout


def test_session_start_stays_quiet_about_digests_when_install_has_no_lock_file(
    tmp_path: Path,
) -> None:
    result = _run_hook(tmp_path, "no_lock")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [f"hdast: plugin versão {VERSION}, ambiente pronto."]
    assert "digests" not in result.stdout


def test_session_start_reports_ready_when_everything_is_in_place(tmp_path: Path) -> None:
    result = _run_hook(tmp_path, "ready")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [f"hdast: plugin versão {VERSION}, ambiente pronto."]


def test_session_start_asks_for_preparation_when_docker_is_missing_and_info_exists(
    tmp_path: Path,
) -> None:
    result = _run_hook(tmp_path, "no_docker")

    assert result.returncode == 0, result.stderr
    assert "Docker não está no PATH." in result.stdout
    assert result.stdout.splitlines()[-1] == CALL_TO_ACTION

"""Executa microbenchmark no proxy real, sem tráfego ao alvo."""

import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path

import pytest

from tests.integration.lab_support import LabCli, require_docker
from tests.integration.test_lab_fast import VAMPI_ENV
from tests.integration.test_scan_performance_matrix import _install

pytestmark = pytest.mark.integration


def _docker(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(  # noqa: S603 - docker e argumentos fixos de laboratório
        ["docker", *args],  # noqa: S607 - comando conhecido
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, "falha no docker durante microbenchmark"
    return result.stdout.strip()


def test_guard_benchmark(tmp_path: Path) -> None:
    """Usa montagens reais, porta válida e diretório exclusivo de evidências."""
    require_docker()
    output_dir = Path(os.environ["HDAST_IT_METRICS_DIR"])
    label = os.environ["V18_GUARD_BENCH_LABEL"]
    assert label in ("before", "after")
    cli = LabCli(tmp_path, VAMPI_ENV)
    _install(cli, "vampi", "B")
    try:
        up = cli.stack_up("vampi", "--vulnerable", timeout=900)
        assert up.code == 0
        containers = _docker(
            "ps",
            "-q",
            "--filter",
            "label=com.docker.compose.project=hdast",
            "--filter",
            "label=com.docker.compose.service=scope-proxy",
        ).splitlines()
        assert len(containers) == 1
        container = containers[0]
        image = _docker("inspect", "--format", "{{.Image}}", container)
        mounts = json.loads(_docker("inspect", "--format", "{{json .Mounts}}", container))
        bind_destinations = {m["Destination"] for m in mounts if m["Type"] == "bind"}
        assert {"/policy", "/approvals", "/product"} <= bind_destinations
        script = (
            Path(__file__).with_name("guard_benchmark_support.py").read_text(encoding="utf-8-sig")
        )
        result = json.loads(
            _docker("exec", "-i", container, "/opt/venv/bin/python", "-", stdin=script)
        )
        assert result["run_id"] == up.data["run_id"]
        result.update(
            {
                "image_id": image,
                "host_platform": platform.platform(),
                "git_commit": subprocess.run(
                    ["git", "rev-parse", "HEAD"],  # noqa: S607 - comando fixo
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=10,
                ).stdout.strip(),
                "label": label,
                "benchmark_sha256": hashlib.sha256(script.encode()).hexdigest(),
                "bind_destinations": sorted(
                    bind_destinations & {"/policy", "/approvals", "/product"}
                ),
            }
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        with (output_dir / f"guard-{label}-vampi.json").open("x", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
            file.write("\n")
    finally:
        cli.stack_down()

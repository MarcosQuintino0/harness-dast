"""A cópia cega mantém os módulos e lê o contrato entregue em inputs."""

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.contract.test_letter_guide import _copy_delivered


def test_copia_cega_importa_pilha_e_resolve_operacoes_do_contrato(tmp_path: Path) -> None:
    _copy_delivered("crapi", tmp_path)
    inputs = tmp_path / "inputs"
    inputs.mkdir(exist_ok=True)
    ids = ("signup", "login", "vehicle_resend_email", "add_vehicle")
    contract = {
        "openapi": "3.0.0",
        "info": {"title": "lab", "version": "1"},
        "paths": {
            f"/local/{index}": {
                "post": {"operationId": name, "responses": {"200": {"description": "ok"}}}
            }
            for index, name in enumerate(ids)
        },
    }
    path = inputs / "api.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    program = (
        "import sys; from pathlib import Path; "
        "sys.path.insert(0, sys.argv[1]); "
        "import harness_dast.cli.stack_composition as stack; "
        "from harness_dast.adapters.openapi.loader import load_spec; "
        "from harness_dast.application.lab_accounts import account_paths; "
        "assert Path(stack.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve()); "
        "assert account_paths(load_spec(Path(sys.argv[2]))).signup == '/local/0'"
    )

    result = subprocess.run(  # noqa: S603 - interpretador e programa controlados pelo teste
        [sys.executable, "-I", "-c", program, str(tmp_path / "src"), str(path)],
        cwd=tmp_path,
        env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")} if os.name == "nt" else {},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr

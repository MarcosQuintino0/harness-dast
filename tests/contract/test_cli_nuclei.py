"""Contrato de `hdast nuclei`: envelope, códigos de saída e recusas, com o motor falso (ADR 0122).

O Docker e a segunda cerca não existem aqui: a montagem real (`build_nuclei`) é trocada pelo caso
de uso ligado aos falsos de `tests/fakes/nuclei.py`. O resto é a CLI de verdade: perfil e
aprovação em disco, trava da pilha, envelope JSON e código de saída.
"""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ExitCode
from harness_dast.domain.nuclei_result import NucleiResult
from tests.fakes.approvals import approve_product_on_disk
from tests.fakes.nuclei import RUN_ID, NucleiRig, nuclei_profile_data, result_line

pytestmark = pytest.mark.contract

ZAP_KEY = "chave-zap-do-contrato-nuclei"
RAW_SECRETS = ("CURL-SEGREDO", "REQ-SEGREDO", "RESP-SEGREDO", "EXTRAIDO-SEGREDO", ZAP_KEY)
NUCLEI_KEYS = set(NucleiResult.model_fields)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in (
        "HDAST_ZAP_PROXY_URL",
        "HDAST_AUTH_PROXY_URL",
        "HDAST_PRODUCTS_DIR",
        "HDAST_LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HDAST_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("HDAST_ZAP_API_KEY", ZAP_KEY)


def _write_product(products: Path, data: dict[str, Any], *, approve: bool = True) -> None:
    folder = products / data["product"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "target.yml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    (folder / "openapi.json").write_text("{}", encoding="utf-8")
    if approve:
        approve_product_on_disk(products, data["product"])


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    data: dict[str, Any] | None = None,
    *,
    approve: bool = True,
    lines: tuple[str, ...] = (),
) -> tuple[NucleiRig, Path]:
    profile = data or nuclei_profile_data(nuclei_login=False)
    products = tmp_path / "produtos"
    _write_product(products, profile, approve=approve)
    rig = NucleiRig(tmp_path, profile_data_override=profile, lines=lines)
    monkeypatch.setattr(
        "harness_dast.cli.commands.nuclei.build_nuclei", lambda *args, **kwargs: rig.nuclei()
    )
    return rig, products


def _invoke(
    capsys: pytest.CaptureFixture[str], products: Path, *args: str
) -> tuple[int, dict[str, Any], str]:
    code = run_app(build_app(), ["--json", "nuclei", *args, "--products-dir", str(products)])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def test_envelope_json_traz_o_resultado_limpo_e_sai_com_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig, products = _setup(monkeypatch, tmp_path, lines=(result_line(severity="high"),))

    code, envelope, err = _invoke(capsys, products, "agenda", "--run", RUN_ID)

    assert code == ExitCode.OK
    assert set(envelope) == {"schema_version", "ok", "run_id", "data"}
    assert envelope["ok"] is True
    assert envelope["run_id"] == RUN_ID
    data = envelope["data"]
    assert set(data) == NUCLEI_KEYS
    assert data["status"] == "completed"
    assert [f["proposed_severity"] for f in data["findings"]] == ["high"]
    assert data == json.loads(rig.artifacts.results[RUN_ID].model_dump_json())
    everything = json.dumps(envelope) + err
    assert not any(secret in everything for secret in RAW_SECRETS)


def test_achado_e_dado_nunca_um_codigo_de_saida_de_falha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, products = _setup(monkeypatch, tmp_path, lines=(result_line(severity="critical"),))

    code, envelope, _ = _invoke(capsys, products, "agenda", "--run", RUN_ID)

    assert code == ExitCode.OK
    assert envelope["ok"] is True
    assert len(envelope["data"]["findings"]) == 1


def test_recusa_sem_aprovacao_do_escopo_com_saida_3_e_sem_rodar_o_motor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig, products = _setup(monkeypatch, tmp_path, approve=False)

    code, envelope, _ = _invoke(capsys, products, "agenda", "--run", RUN_ID)

    assert code == ExitCode.SCOPE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "SCOPE_NOT_APPROVED"
    assert rig.engine.specs == []


def test_recusa_fora_da_janela_com_saida_3_e_sem_rodar_o_motor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = nuclei_profile_data(nuclei_login=False)
    data["scope"]["windows"] = ["seg-sex 00:00-01:00 UTC"]
    rig, products = _setup(monkeypatch, tmp_path, data)

    code, envelope, _ = _invoke(capsys, products, "agenda", "--run", RUN_ID)

    assert code == ExitCode.SCOPE
    assert envelope["error"]["code"] == "SCOPE_VIOLATION"
    assert rig.engine.specs == []


def test_recusa_perfil_sem_a_chave_do_nuclei_com_saida_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = nuclei_profile_data(nuclei=False, nuclei_login=False)
    rig, products = _setup(monkeypatch, tmp_path, data)

    code, envelope, _ = _invoke(capsys, products, "agenda", "--run", RUN_ID)

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert "extra_checks.nuclei" in envelope["error"]["message"]
    assert rig.engine.specs == []


def test_parada_pela_trava_devolve_o_resultado_parcial_com_saida_3(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig, products = _setup(monkeypatch, tmp_path, lines=(result_line(),))
    rig.engine.during_run = lambda: setattr(rig.kill, "on", True)

    code, envelope, _ = _invoke(capsys, products, "agenda", "--run", RUN_ID)

    assert code == ExitCode.SCOPE
    assert envelope["ok"] is False
    assert envelope["data"]["status"] == "stopped_kill"
    assert set(envelope["data"]) == NUCLEI_KEYS


def test_run_id_invalido_e_recusado_com_saida_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig, products = _setup(monkeypatch, tmp_path)

    code, envelope, _ = _invoke(capsys, products, "agenda", "--run", "../fora")

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert rig.engine.specs == []


def test_produto_inexistente_e_recusado_com_saida_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, products = _setup(monkeypatch, tmp_path)

    code, envelope, _ = _invoke(capsys, products, "outro", "--run", RUN_ID)

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False


def test_sem_o_run_a_cli_recusa_o_uso_com_saida_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, products = _setup(monkeypatch, tmp_path)

    code = run_app(build_app(), ["--json", "nuclei", "agenda", "--products-dir", str(products)])

    assert code == ExitCode.USAGE
    capsys.readouterr()

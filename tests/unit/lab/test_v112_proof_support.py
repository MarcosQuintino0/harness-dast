"""Verifica o recorte e a sanitizaÃ§Ã£o usados pelas provas V1.12."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from evals.runner.metrics import measure_agent
from harness_dast.adapters.openapi.spec_loader import FileSpecLoader
from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.application.lab_accounts import account_paths
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import review_letter
from harness_dast.domain.probe_plan import plan_probe
from harness_dast.domain.probe_result import OperationResult, ProbeResult, ProbeSummary
from harness_dast.domain.scan_policy import build_policy
from harness_dast.domain.scope import OutboundRequest
from tests.integration.lab_support import REPO, CliResult
from tests.integration.test_crapi_focus_dryrun import (
    HEALTH_PATH,
    _configure_health_path,
    _transcript,
)
from tests.integration.v112_proof_support import (
    control_spec,
    install_focus_spec,
    narrow_control_profile,
    probe_attempts,
    summary,
)


def test_control_spec_recusa_operacao_incorreta(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps({"paths": {"/workshop/api/shop/products": {"get": {"operationId": "outro"}}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="controle ou cadastro ausentes"):
        control_spec(source, tmp_path / "out.json")


def test_control_spec_preserva_cadastro_e_restringe_plano(tmp_path: Path) -> None:
    products = tmp_path / "products"
    product = products / "crapi"
    shutil.copytree(REPO / "lab/crapi/product-profile", product)
    control_spec(REPO / "lab/crapi/openapi.json", product / "openapi.json")
    narrow_control_profile(products)
    profile = FileProfileRepository(products).load("crapi")
    loader = FileSpecLoader(lambda name, path: resolve_product_file(products, name, path))
    spec = loader.load("crapi", profile)
    paths = account_paths(spec)
    assert (paths.signup, paths.login, paths.resend, paths.vehicle) == (
        "/identity/api/auth/signup",
        "/identity/api/auth/login",
        "/identity/api/v2/vehicle/resend_email",
        "/identity/api/v2/vehicle/add_vehicle",
    )
    plan = plan_probe(spec, None, profile.guard(), profile.environment.base_url)
    assert {item.operation_id for item in plan if item.decision == "send"} == {
        "login",
        "get_products",
    }
    assert build_policy(profile.scan).strength == "LOW"


def test_probe_attempts_le_formato_serializado_pela_cli() -> None:
    result = ProbeResult(
        run_id="2026-01-01T00-00-00Z-crapi-abcd",
        product="crapi",
        dry_run=False,
        status="completed",
        seed=1,
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z",
        summary=ProbeSummary(
            operations_total=1,
            operations_sent=1,
            successes=1,
            reachability=1.0,
            reachability_all=1.0,
            by_outcome={"success": 1},
        ),
        operations=(
            OperationResult(
                operation_id="get_products",
                method="GET",
                path="/workshop/api/shop/products",
                outcome="success",
                attempts=1,
            ),
        ),
    )
    status, attempts = probe_attempts(result.model_dump(mode="json"), {"get_products"})
    assert status == "completed"
    assert attempts == {"get_products": 1}


def test_probe_attempts_recusa_envelope_incompleto() -> None:
    with pytest.raises(ValidationError):
        probe_attempts({"operations": []}, {"get_products"})


def test_foco_configura_saude_sem_alterar_blocos_da_carta(tmp_path: Path) -> None:
    letter = yaml.safe_load((REPO / "evals/cases/crapi-foco/carta.yml").read_text(encoding="utf-8"))
    review = review_letter(Letter.from_data(letter), "crapi", date(2026, 11, 17))
    assert review.profile_text is not None
    workspace = tmp_path / "workspace"
    products = workspace / "products"
    product = products / "crapi"
    product.mkdir(parents=True)
    target = product / "target.yml"
    target.write_text(review.profile_text, encoding="utf-8")
    original = yaml.safe_load(target.read_text(encoding="utf-8"))
    inputs = workspace / "inputs"
    inputs.mkdir()
    shutil.copy2(REPO / "lab/crapi/openapi.json", inputs / "openapi.json")
    install_focus_spec(workspace, products)
    _configure_health_path(products)
    configured = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert {k: v for k, v in configured.items() if k != "probe"} == {
        k: v for k, v in original.items() if k != "probe"
    }
    assert configured["probe"] == {**original.get("probe", {}), "health_path": HEALTH_PATH}
    profile = FileProfileRepository(products).load("crapi")
    assert profile.probe.health_path == HEALTH_PATH
    profile.guard().ensure_allowed(
        OutboundRequest(method="GET", url=profile.environment.base_url + HEALTH_PATH)
    )
    loader = FileSpecLoader(lambda name, path: resolve_product_file(products, name, path))
    spec = loader.load("crapi", profile)
    paths = account_paths(spec)
    assert (paths.signup, paths.login, paths.resend, paths.vehicle) == (
        "/identity/api/auth/signup",
        "/identity/api/auth/login",
        "/identity/api/v2/vehicle/resend_email",
        "/identity/api/v2/vehicle/add_vehicle",
    )
    assert (product / profile.openapi).read_bytes() == (inputs / "openapi.json").read_bytes()
    assert profile.scan.strength == "LOW"


def test_summary_omite_mensagens_e_conteudo_externo() -> None:
    result = CliResult(0, {}, "", "")
    result.envelope.update(
        {
            "data": {
                "status": "failed",
                "stages": [
                    {
                        "name": "probe",
                        "status": "failed",
                        "message": "segredo-sintetico",
                        "duration_seconds": 2,
                    }
                ],
            }
        }
    )
    assert "segredo-sintetico" not in json.dumps(summary(result))


def test_transcript_de_ensaio_mede_tempo_sem_modelo_ou_tokens(tmp_path: Path) -> None:
    records = {
        "probe": {
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:05+00:00",
            "exit_code": 0,
        }
    }
    _transcript(tmp_path, records)
    metrics = measure_agent(tmp_path, "ensaio-sem-agente")
    assert metrics.totals.duration_seconds == 5
    assert metrics.totals.tokens is None
    assert metrics.model is None

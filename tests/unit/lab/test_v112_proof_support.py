"""Verifica o recorte e a sanitizaÃ§Ã£o usados pelas provas V1.12."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from evals.runner.metrics import measure_agent
from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.adapters.openapi.spec_loader import FileSpecLoader
from harness_dast.adapters.storage.product_documents import FileProductDocuments
from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.adapters.storage.product_scaffolder import FileProductScaffolder
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.application.lab_accounts import account_paths
from harness_dast.application.probe import Probe, ProbeRequest
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import review_letter
from harness_dast.domain.probe_plan import plan_probe
from harness_dast.domain.probe_result import OperationResult, ProbeResult, ProbeSummary
from harness_dast.domain.scan_policy import build_policy
from harness_dast.domain.scope import OutboundRequest
from tests.fakes.rig import Rig
from tests.integration.lab_support import REPO, CliResult
from tests.integration.test_crapi_focus_dryrun import (
    EXPECTED,
    HEALTH_PATH,
    _configure_health_path,
    _coverage_complete,
    _remove_template_examples,
    _run_evidence,
    _transcript,
)
from tests.integration.v112_proof_support import (
    control_spec,
    install_focus_spec,
    prepare_control_product,
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
    prepare_control_product(products)
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


def test_produto_de_controle_permite_probe_dry_run_com_documentos_reais(tmp_path: Path) -> None:
    products = tmp_path / "products"
    product = prepare_control_product(products)
    assert {path.name for path in product.iterdir()} == {"target.yml", "openapi.json"}
    rig = Rig(env={})
    probe = Probe(
        profiles=FileProfileRepository(products),
        specs=FileSpecLoader(lambda name, path: resolve_product_file(products, name, path)),
        documents=FileProductDocuments(products),
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        zap=rig.zap,
        store=rig.store,
        clock=rig.clock,
        sleeper=rig.clock,
        entropy=rig.entropy,
        value_sources=GeneratorCatalogue,
        harness_version="0.0-test",
    )
    result = probe.execute(ProbeRequest(product="crapi", dry_run=True))
    assert result.status == "completed"
    assert result.dry_run is True
    assert {op.operation_id: op.outcome for op in result.operations}["get_products"] == "dry_run"
    assert rig.target.requests == []


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


def test_foco_descarta_exemplos_e_executa_probe_com_documentos_reais(tmp_path: Path) -> None:
    letter = yaml.safe_load((REPO / "evals/cases/crapi-foco/carta.yml").read_text(encoding="utf-8"))
    review = review_letter(Letter.from_data(letter), "crapi", date(2026, 11, 17))
    assert review.profile_text is not None
    products = tmp_path / "products"
    products.mkdir()
    FileProductScaffolder(products, REPO / "products/_template").scaffold(
        "crapi", target_text=review.profile_text
    )
    product = products / "crapi"
    shutil.copy2(REPO / "lab/crapi/openapi.json", product / "openapi.json")
    _configure_health_path(products)
    rig = Rig(env={})
    probe = Probe(
        profiles=FileProfileRepository(products),
        specs=FileSpecLoader(lambda name, path: resolve_product_file(products, name, path)),
        documents=FileProductDocuments(products),
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        zap=rig.zap,
        store=rig.store,
        clock=rig.clock,
        sleeper=rig.clock,
        entropy=rig.entropy,
        value_sources=GeneratorCatalogue,
        harness_version="0.0-test",
    )
    with pytest.raises(ConfigError, match="criarConvenio"):
        probe.execute(ProbeRequest(product="crapi", dry_run=True))
    _remove_template_examples(products)
    result = probe.execute(ProbeRequest(product="crapi", dry_run=True))
    assert result.status == "completed"
    assert {
        operation.operation_id for operation in result.operations if operation.outcome == "dry_run"
    } == EXPECTED
    assert rig.target.requests == []


def test_foco_recusa_apagar_exemplo_alterado(tmp_path: Path) -> None:
    products = tmp_path / "products"
    product = products / "crapi"
    product.mkdir(parents=True)
    shutil.copy2(REPO / "products/_template/data-rules.yml", product / "data-rules.yml")
    (product / "flows.yml").write_text("conteudo alterado", encoding="utf-8")
    with pytest.raises(ValueError, match="flows"):
        _remove_template_examples(products)
    assert (product / "data-rules.yml").is_file()


def test_evidencia_preserva_corte_de_scan_e_lacunas_de_authz(tmp_path: Path) -> None:
    run_id = "2026-01-01T00-00-00Z-crapi-abcd"
    folder = tmp_path / run_id
    folder.mkdir()
    common = {
        "run_id": run_id,
        "product": "crapi",
        "status": "completed",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
    }
    scan = {
        **common,
        "dry_run": False,
        "policy": {
            "name": "test",
            "strength": "LOW",
            "threshold": "MEDIUM",
            "url_path_injection": True,
            "injectable_mask": 0,
            "disabled_rules": [],
        },
        "limits": {
            "requests_per_second": 1,
            "max_duration_minutes": 1,
            "threads_per_host": 1,
            "delay_ms": 1,
            "max_scan_minutes": 1,
            "max_rule_minutes": 1,
        },
        "health": {"enabled": True},
        "entries": [
            {
                "operation_id": "get_products",
                "method": "GET",
                "path": "/workshop/api/shop/products",
                "message_id": 1,
                "outcome": "truncated",
            }
        ],
    }
    probe = {
        **common,
        "dry_run": False,
        "seed": 1,
        "summary": {
            "operations_total": 1,
            "operations_sent": 1,
            "successes": 1,
            "reachability": 1.0,
            "reachability_all": 1.0,
            "by_outcome": {"success": 1},
        },
        "operations": [
            {
                "operation_id": "get_products",
                "method": "GET",
                "path": "/workshop/api/shop/products",
                "outcome": "success",
                "attempts": 1,
            }
        ],
    }
    authz = {**common, "checks": [{"check": "horizontal", "status": "partial", "tested": 1}]}
    for name, payload in (("scan", scan), ("probe", probe), ("authz", authz), ("negative", common)):
        (folder / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    evidence = _run_evidence(tmp_path, run_id)
    assert evidence["scan_entries"][0]["outcome"] == "truncated"
    assert evidence["authz_checks"][0]["status"] == "partial"
    evidence["probe_attempts"] = dict.fromkeys(EXPECTED, 1)
    assert _coverage_complete(evidence) is False
    evidence["scan_entries"][0]["outcome"] = "completed"
    assert _coverage_complete(evidence) is False
    evidence["authz_checks"][0]["status"] = "completed"
    assert _coverage_complete(evidence) is True
    evidence["scan_rule_gaps"] = [{"state": "interrupted"}]
    assert _coverage_complete(evidence) is False


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

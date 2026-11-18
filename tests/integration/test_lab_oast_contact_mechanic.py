"""Contato do mecânico (C11) com a ponte OAST de pé: só no laboratório (V1.12.2).

Nível RÁPIDO: uma pilha crAPI com `scan.oast` ligado (ponte montada pela CLI, ADR 0105) e o
`probe` do perfil do caso v3 (`mechanic_api` para o próprio workshop, `TRAC_JHN`, `1`).

- com o `vin` ligado ao veículo da conta (`flows.yml`): o `probe` dá 2xx e o SSRF guiado do mesmo
  ciclo observa o retorno;
- sem essa ligação, na MESMA pilha com a ponte: o `receive_report` não acha o veículo e o contato
  responde 500. O 500 vem do dado, não da ponte: o defeito visto na rodada cega V1.12.1 r2 (perfil
  sem a ligação do `vin`) não é de rede.

Medidas vão para `HDAST_IT_METRICS_DIR/lab-oast-contact-mechanic`.
"""

import json
import secrets
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
import yaml

from tests.integration.lab_support import REPO, LabCli, require_docker
from tests.integration.oast_support import OastLab
from tests.integration.run_support import record_metrics
from tests.integration.test_lab_oast import finish_proof
from tests.integration.test_lab_oast_scan import OPERATION, tweak_profile

pytestmark = [pytest.mark.integration, pytest.mark.lab_prova]


@dataclass
class ContactLab:
    """O que a pilha com a ponte produziu."""

    bound: dict[str, Any] = field(default_factory=dict)
    scan: dict[str, Any] = field(default_factory=dict)
    unbound: dict[str, Any] = field(default_factory=dict)


def _contact(cli: LabCli, run_id: str) -> dict[str, Any]:
    probe = json.loads((cli.runs / run_id / "probe.json").read_text(encoding="utf-8"))
    return next(o for o in probe["operations"] if o["operation_id"] == OPERATION)


def _unbind_vin(cli: LabCli) -> None:
    """Tira só a ligação do `vin` do contato; o resto do `flows.yml` fica igual."""
    flows = cli.products / "crapi" / "flows.yml"
    data = yaml.safe_load(flows.read_text(encoding="utf-8"))
    consumer = {"operation": OPERATION, "field": "vin"}
    assert any(consumer in item["consumed_by"] for item in data["bindings"])
    for item in data["bindings"]:
        item["consumed_by"] = [c for c in item["consumed_by"] if c != consumer]
    flows.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


@pytest.fixture(scope="module")
def lab(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ContactLab]:
    require_docker()
    token = secrets.token_hex(8)
    extra = {
        "HDAST_ZAP_API_KEY": secrets.token_hex(32),
        "CRAPI_DB_PASSWORD": secrets.token_hex(16),
        "CRAPI_USER_A_EMAIL": f"a.{token}@example.com",
        "CRAPI_USER_B_EMAIL": f"b.{token}@example.com",
        "CRAPI_USER_A_PASSWORD": "Aa1#" + secrets.token_hex(16),
        "CRAPI_USER_B_PASSWORD": "Aa1#" + secrets.token_hex(16),
    }
    cli = LabCli(tmp_path_factory.mktemp("oast-contact"), extra)
    for name in tuple(cli.env):
        if name.startswith("CRAPI_") and name not in extra:
            del cli.env[name]
    cli.install_product(
        "crapi", REPO / "lab/crapi/product-profile", (REPO / "lab/crapi/openapi.json",)
    )
    tweak_profile(cli.products / "crapi", oast=True)
    marker = "lab-" + secrets.token_hex(6)
    probe = OastLab(cli, extra["HDAST_ZAP_API_KEY"], secrets.token_hex(6))
    probe.use_managed_bridge()
    probe.assert_project_unused()
    probe.assert_crapi_unused()
    evidence: dict[str, object] = {"marker": marker, "source": "crapi-contact-mechanic"}
    out = ContactLab()
    try:
        cli.approve_installed_products()
        cli.freeze_approvals = True
        up = probe.stack_up("crapi")
        assert up.code == 0, up.stdout[-500:]
        evidence["stack_run_id"] = up.data.get("run_id")
        probe.managed_workshop()
        probe.topology(workshop=True)
        good = cli.run("probe", "crapi", "--seed", "1", timeout=600)
        assert good.code == 0, good.stdout[-600:]
        evidence["probe_bound_run_id"] = good.envelope.get("run_id")
        out.bound = _contact(cli, str(good.envelope["run_id"]))
        scan = cli.run(
            "scan", "crapi", "--run", str(good.envelope["run_id"]), "--only", OPERATION,
            "--max-minutes", "4", timeout=900,
        )  # fmt: skip
        evidence["scan_exit"] = scan.code
        assert scan.code == 0, scan.stdout[-600:]
        evidence["scan_run_id"] = scan.envelope.get("run_id")
        scan_dir = cli.runs / str(scan.envelope["run_id"])
        out.scan = json.loads((scan_dir / "scan.json").read_text(encoding="utf-8"))
        evidence["ssrf"] = out.scan.get("ssrf")
        _unbind_vin(cli)
        bad = cli.run("probe", "crapi", "--seed", "1", "--only", OPERATION, timeout=600)
        evidence["probe_unbound_run_id"] = bad.envelope.get("run_id")
        out.unbound = _contact(cli, str(bad.envelope["run_id"]))
        evidence["unbound"] = {k: out.unbound[k] for k in ("outcome", "status")}
        yield out
    finally:
        try:
            finish_proof(probe, marker, evidence)
        finally:
            record_metrics("lab-oast-contact-mechanic", evidence)


def test_with_the_bridge_up_and_the_vin_bound_the_contact_probe_is_2xx(lab: ContactLab) -> None:
    assert lab.bound["outcome"] == "success", lab.bound
    assert 200 <= lab.bound["status"] < 300


def test_with_the_bridge_up_the_guided_ssrf_observes_the_return_in_the_same_cycle(
    lab: ContactLab,
) -> None:
    assert lab.scan["ssrf"]["observed"] >= 1, lab.scan["ssrf"]
    seen = lab.scan["ssrf"]["observations"][0]
    assert seen["operation_id"] == OPERATION
    assert seen["field"] == "mechanic_api"
    assert seen["status"] == 200
    assert lab.scan["oast_verification"]["ssrf"] == "verifiable"


def test_without_the_vin_binding_the_contact_is_500_even_with_the_bridge_up(
    lab: ContactLab,
) -> None:
    assert lab.unbound["outcome"] == "server_error", lab.unbound
    assert lab.unbound["status"] == 500

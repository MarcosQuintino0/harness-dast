"""Reproduz BOLA escondida pelo roteamento e prova limites do envio guardado."""

import pytest

from harness_dast.application.authz.service import AuthzRequest
from harness_dast.domain.authz.result import AuthzResult
from tests.fakes.authz.owner_rig import OwnerApi, add_creation, owner_rig
from tests.fakes.authz.rig import AuthzRig


def execute(rig: AuthzRig, *, dry_run: bool = False) -> AuthzResult:
    probe = rig.run_probe()
    return rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("horizontal",), dry_run=dry_run)
    )


def test_detecta_bola_quando_leitura_roteada_ao_papel_compartilhado() -> None:
    rig = owner_rig()
    result = execute(rig)
    findings = [f for f in result.findings if f.operation_id == "getRecord"]
    assert findings
    assert all(
        f.technique == "authz_horizontal"
        and f.proposed_severity == "high"
        and f.owner_account == "pac_a"
        and f.actor_account == "pac_b"
        for f in findings
    )
    assert any(
        n.operation_id == "getRecord" and n.reason == "shared_role" for n in result.not_tested
    )


def test_protegido_quando_par_nao_pode_ler() -> None:
    result = execute(owner_rig(OwnerApi(bola=False)))
    assert not result.findings
    assert next(s for s in result.checks if s.check == "horizontal").tested >= 2


def test_orcamento_limita_objetos_e_registra_contagem() -> None:
    rig = owner_rig()
    result = execute(rig)
    reads = [
        r
        for r in rig.target.requests
        if r.operation_id.startswith("authz:owner:") and "/records/" in r.url
    ]
    assert len(reads) == 4
    assert all(r.method == "GET" and not r.body for r in reads)
    assert not any(r.url.endswith("/13") for r in reads)
    summary = next(s for s in result.checks if s.check == "horizontal")
    assert summary.message
    assert "2 objeto(s)" in summary.message
    assert any(
        n.operation_id == "getRecord" and n.reason == "budget_exhausted" for n in result.not_tested
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"own": []}, "owner_collection_empty"),
        ({"collection_status": 403}, "owner_collection_unavailable"),
        ({"own": {}}, "ambiguous_identifier"),
        ({"own": [{"id": "11"}]}, "ambiguous_identifier"),
        ({"own": b'[{"id":11,"id":12}]'}, "ambiguous_identifier"),
        ({"peer": [{"id": 11}]}, "ambiguous_identifier"),
        ({"peer": {}}, "ambiguous_identifier"),
        ({"base_status": 403}, "baseline_failed"),
        ({"base_identity": 99}, "baseline_failed"),
        ({"replay_status": 400}, "inconclusive"),
        ({"replay_status": 500}, "inconclusive"),
        ({"replay_identity": 99}, "inconclusive"),
        ({"different": True}, "inconclusive"),
    ],
)
def test_lacuna_visivel_quando_identidade_ou_resposta_nao_prova_comparacao(
    changes: dict[str, object],
    reason: str,
) -> None:
    result = execute(owner_rig(OwnerApi(**changes)))
    assert not [f for f in result.findings if f.operation_id == "getRecord"]
    assert any(
        n.operation_id == "getRecord" and n.reason == reason and n.message
        for n in result.not_tested
    )


@pytest.mark.parametrize("deny", [("/api/records",), ("/api/records/*",)])
def test_cerca_recusa_colecao_ou_item_quando_caminho_negado(deny: tuple[str, ...]) -> None:
    rig = owner_rig(deny=deny)
    result = execute(rig)
    assert any(
        n.operation_id == "getRecord" and n.reason == "scope_denied" for n in result.not_tested
    )
    denied = "/api/records" if deny[0].endswith("records") else "/api/records/"
    assert not [
        r
        for r in rig.target.requests
        if r.operation_id.startswith("authz:owner:")
        and (r.url.endswith(denied) if denied.endswith("records") else denied in r.url)
    ]


def test_simulacao_nao_envia_quando_ha_leitura_de_dono_planejada() -> None:
    rig = owner_rig()
    result = execute(rig, dry_run=True)
    assert result.dry_run
    assert result.requests_sent == 0
    assert not [r for r in rig.target.requests if r.operation_id.startswith("authz:")]
    assert "Leitura de dono" in next(
        s.message or "" for s in result.checks if s.check == "horizontal"
    )


def test_valor_enviado_em_criacao_de_sucesso_serve_sem_nova_escrita() -> None:
    rig = owner_rig(collection=False)
    probe = rig.run_probe()
    add_creation(rig, probe.run_id)
    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("horizontal",))
    )
    assert any(f.operation_id == "getRecord" for f in result.findings)
    assert not [
        r
        for r in rig.target.requests
        if r.operation_id.startswith("authz:owner:") and r.method != "GET"
    ]


def test_sem_probe_de_item_monta_leitura_por_colecao() -> None:
    rig = owner_rig()
    probe = rig.run_probe()
    log = rig.store.exchanges[probe.run_id]
    rig.store.exchanges[probe.run_id] = log.model_copy(
        update={"exchanges": tuple(e for e in log.exchanges if e.operation_id != "getRecord")}
    )
    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("horizontal",))
    )
    assert any(f.operation_id == "getRecord" for f in result.findings)

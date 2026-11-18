"""Casos de fronteira independentes para a agregação de sinais da V1.5.2."""

from datetime import UTC, datetime, timedelta

from harness_dast.domain.finding_build import AlertResolver, OperationRef
from harness_dast.domain.signal_findings import build_proxy_signals
from harness_dast.domain.signal_result import MAX_SIGNAL_FINDINGS
from harness_dast.domain.traffic import ProxyRow

START = datetime(2026, 11, 15, tzinfo=UTC)
WINDOW = (START, START + timedelta(minutes=1))


def audit(path: str, method: str = "GET") -> ProxyRow:
    return ProxyRow(
        at=START,
        decision="allow",
        reason="allowed",
        method=method,
        path=path,
        status=500,
        signals=("sql_error",),
    )


def test_teto_conta_operacoes_distintas_e_preserva_contagem_total() -> None:
    count = MAX_SIGNAL_FINDINGS + 7
    operations = tuple(
        OperationRef(operation_id=f"op{n}", method="GET", path=f"/routes/{n}/{{id}}")
        for n in range(count)
    )
    rows = [audit(f"/routes/{n}/mutado") for n in range(count)]

    result = build_proxy_signals(
        rows, product="demo", window=WINDOW, resolver=AlertResolver({}, {}, operations)
    )

    assert len(result.findings) == MAX_SIGNAL_FINDINGS
    assert result.findings_omitted == 7
    assert result.counts["sql_error"] == count
    assert len({item.fingerprint for item in result.findings}) == MAX_SIGNAL_FINDINGS


def test_mutacoes_e_caminhos_fora_do_contrato_nao_expoem_identificadores() -> None:
    resolver = AlertResolver(
        {}, {}, (OperationRef(operation_id="getFile", method="GET", path="/files/{name}"),)
    )
    identifiers = ("sintetico-9f8e7d", "outro-123456", "desconhecido-987654")
    result = build_proxy_signals(
        [
            audit(f"/files/{identifiers[0]}"),
            audit(f"/files/{identifiers[1]}"),
            audit(f"/other/{identifiers[2]}", "POST"),
        ],
        product="demo",
        window=WINDOW,
        resolver=resolver,
    )

    assert {(f.operation_id, f.occurrences) for f in result.findings} == {("getFile", 2), (None, 1)}
    assert all(identifier not in result.model_dump_json() for identifier in identifiers)

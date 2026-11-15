"""Resultados do teste negativo prontos para os testes do relatório, do `run` e do painel."""

from harness_dast.domain.negative_result import (
    ClassSummary,
    NegativeFinding,
    NegativeNotTested,
    NegativeResult,
    OperationSummary,
)
from harness_dast.domain.negative_values import CLASS_ORDER

PRODUCT = "vampi"
RUN_ID = "2026-11-13T05-15-32Z-vampi-ab12"


def accepted(
    *,
    severity: str = "low",
    field: str = "limite",
    method: str = "GET",
    title: str = "GET /api/produtos: valor aceito",
    restored: bool | None = None,
    created: bool = False,
) -> NegativeFinding:
    """Achado `input_accepted` com severidade escolhida pelo teste."""
    return NegativeFinding(
        finding_id="N-1a2b3c4d",
        fingerprint="1a2b3c4d" * 8,
        technique="input_accepted",
        title=title,
        proposed_severity=severity,  # type: ignore[arg-type]  # o teste só passa severidades válidas
        cwe=20,
        owasp_api_2023="API8:2023 Security Misconfiguration",
        operation_id="listarProdutos",
        method=method,
        path_template="/api/produtos",
        account="user_a",
        location="query",
        field=field,
        case_class="above_maximum",
        declared="maximum 100",
        observed_status=200,
        baseline_status=200,
        restored=restored,
        created=created,
        evidence="Com um valor válido, o probe recebeu 200; o campo foi alterado e aceito.",
        description="O servidor aceitou um valor que o contrato proíbe.",
        solution="Validar a entrada contra o contrato.",
    )


def server_error() -> NegativeFinding:
    """Achado `input_server_error` de severidade baixa, em leitura."""
    return accepted().model_copy(
        update={
            "finding_id": "N-99887766",
            "fingerprint": "99887766" * 8,
            "technique": "input_server_error",
            "cwe": 755,
            "observed_status": 500,
            "title": "GET /api/produtos: erro do servidor",
            "field": "ordem",
            "case_class": "not_in_enum",
            "declared": "enum asc, desc",
        }
    )


def negative_result(
    *,
    findings: tuple[NegativeFinding, ...] | None = None,
    status: str = "completed",
    product: str = PRODUCT,
    run_id: str = RUN_ID,
    created: int = 0,
    not_tested: tuple[NegativeNotTested, ...] | None = None,
) -> NegativeResult:
    """Resultado com contagem por classe e por operação coerente com os achados."""
    items = (accepted(), server_error()) if findings is None else findings
    rows = tuple(
        ClassSummary(
            case_class=name,
            planned=2 if name == "above_maximum" else 0,
            sent=2 if name == "above_maximum" else 0,
            rejected=1 if name == "above_maximum" else 0,
            accepted=1 if name == "above_maximum" else 0,
        )
        for name in CLASS_ORDER
    )
    return NegativeResult(
        run_id=run_id,
        product=product,
        status=status,  # type: ignore[arg-type]  # o teste só passa estados válidos
        stop_message="parou" if status != "completed" else None,
        started_at="2026-11-13T05:30:00+00:00",
        finished_at="2026-11-13T05:40:00+00:00",
        requests_sent=2,
        accounts=("user_a",),
        created_resources=created,
        by_class=rows,
        operations=(
            OperationSummary(
                operation_id="listarProdutos",
                method="GET",
                path="/api/produtos",
                sent=2,
                rejected=1,
                accepted=1,
            ),
        ),
        operations_tested=1,
        findings=items,
        not_tested=(
            (
                NegativeNotTested(
                    operation_id="criarProduto",
                    method="POST",
                    path="/api/produtos",
                    reason="writes_not_authorized",
                    message="escrita não autorizada pela carta: negative.allow_writes",
                ),
            )
            if not_tested is None
            else not_tested
        ),
    )

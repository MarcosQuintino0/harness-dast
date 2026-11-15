"""Resolve sinais pelo contrato dispon?vel, sem alterar a atribui??o dos alertas do ZAP."""

from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.finding_build import AlertResolver, OperationRef


def signal_resolver(probe: AlertResolver, spec: ApiSpec | None) -> AlertResolver:
    """Usa o contrato inteiro se ele ainda contiver os modelos registrados pelo probe.

    Sem contrato ou se houver diverg?ncia, usa s? os modelos hist?ricos do probe. N?o
    verifica altera??es em opera??es ausentes do probe; o OpenAPI atual pode ter mudado.
    """
    if spec is None:
        return probe
    refs = tuple(
        OperationRef(operation_id=op.operation_id, method=op.method, path=op.path)
        for op in spec.operations
    )
    identities = {(ref.operation_id, ref.method.upper(), ref.path) for ref in refs}
    if any(
        (ref.operation_id, ref.method.upper(), ref.path) not in identities
        for ref in probe.operations
    ):
        return probe
    return AlertResolver(probe.by_message, probe.by_alert, refs)

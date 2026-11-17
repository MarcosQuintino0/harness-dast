"""Reconstrói referências declaradas para um POST previamente provado."""

from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.flow import FlowSpec, ResolvedBindings, extract_value


def bindings_from_proven_body(
    flow: FlowSpec | None, operation_id: str, body: JsonValue
) -> ResolvedBindings:
    """Recupera apenas campos consumidores declarados, sem preservar o restante do corpo.

    Raises:
        TargetError: Um campo consumidor não existe ou não é texto nem inteiro.
    """
    fields = {}
    if flow is not None:
        for binding in flow.bindings:
            for consumer in binding.consumed_by:
                if consumer.operation == operation_id and consumer.field is not None:
                    fields[consumer.field] = extract_value(body, consumer.field)
    return ResolvedBindings(fields=fields)

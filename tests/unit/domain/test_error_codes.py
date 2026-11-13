"""`probe.error_codes`, sinal de token vencido e trecho de erro com estrutura por campo."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from harness_dast.domain.excerpt import EXCERPT_CAP, sanitize_excerpt
from harness_dast.domain.http_messages import HttpResponse
from harness_dast.domain.outcome import Outcome, classify_response
from harness_dast.domain.probe_config import ErrorCodes, JsonFieldRule
from harness_dast.domain.retry import RetryState, is_token_expired, next_action


def response(status: int, body: Any = None) -> HttpResponse:
    raw = b"" if body is None else json.dumps(body).encode()
    return HttpResponse(status=status, content_type="application/json", body=raw)


CODES = ErrorCodes(
    field="code",
    outcomes={
        "validation_error": ("VALIDACAO",),
        "conflict": ("CONFLITO", "EM_USO"),
        "not_found": ("REFERENCIA_INEXISTENTE",),
    },
)


def classify(answer: HttpResponse, method: str = "POST") -> Outcome:
    return classify_response(answer, method=method, success_rule=None, csrf=None, error_codes=CODES)


def test_a_declared_code_decides_regardless_of_the_status() -> None:
    assert classify(response(422, {"code": "EM_USO"})) == "conflict"


def test_an_undeclared_code_uses_the_status_heuristic() -> None:
    assert classify(response(409, {"code": "NOVO"})) == "conflict"


def test_a_missing_code_field_uses_the_status_heuristic() -> None:
    assert classify(response(400, {"message": "x"})) == "validation_error"


def test_a_2xx_is_never_reclassified_by_a_code() -> None:
    assert classify(response(200, {"code": "CONFLITO"}), "GET") == "success"


def test_a_list_or_boolean_code_does_not_classify() -> None:
    assert CODES.outcome_for({"code": ["CONFLITO"]}) is None
    assert CODES.outcome_for({"code": True}) is None
    assert CODES.outcome_for(None) is None


def test_a_numeric_code_is_compared_as_text() -> None:
    numeric = ErrorCodes(field="error.code", outcomes={"conflict": ("42",)})

    assert numeric.outcome_for({"error": {"code": 42}}) == "conflict"


@pytest.mark.parametrize(
    "outcomes",
    [
        {"conflict": ("A",), "validation_error": ("A",)},
        {"conflict": ("tem espaço",)},
        {"success": ("A",)},
        {},
    ],
)
def test_invalid_code_maps_are_rejected(outcomes: dict[str, tuple[str, ...]]) -> None:
    with pytest.raises(ValidationError):
        ErrorCodes.model_validate({"field": "code", "outcomes": outcomes})


def test_token_expired_requires_a_401() -> None:
    signal = JsonFieldRule(field="code", value="TOKEN_EXPIRADO")

    assert is_token_expired(response(401, {"code": "TOKEN_EXPIRADO"}), signal)
    assert not is_token_expired(response(403, {"code": "TOKEN_EXPIRADO"}), signal)
    assert not is_token_expired(response(401, {"code": "TOKEN_INVALIDO"}), signal)
    assert is_token_expired(response(401), None)


def test_next_action_reauths_at_most_once_per_request() -> None:
    answer = response(401)
    state = RetryState()

    first = next_action(answer, "GET", csrf=None, can_reauth=True, state=state)
    second = next_action(answer, "GET", csrf=None, can_reauth=True, state=state.after(first))

    assert (first, second) == ("reauth", "done")


def test_the_excerpt_keeps_field_and_rule_when_the_body_exceeds_the_cap() -> None:
    errors = [
        {"field": f"campo{n}", "rule": "REGRA", "message": "mensagem longa " * 3} for n in range(10)
    ]
    body = json.dumps({"code": "VALIDACAO", "message": "dados inválidos", "errors": errors})

    excerpt = sanitize_excerpt(body.encode(), lambda text: text)

    assert len(excerpt) <= EXCERPT_CAP
    parsed = json.loads(excerpt)
    assert parsed["code"] == "VALIDACAO"
    assert parsed["errors"][0] == {"field": "campo0", "rule": "REGRA"}
    assert len(parsed["errors"]) >= 3


def test_the_excerpt_masks_secret_values_even_inside_error_items() -> None:
    body = json.dumps({"errors": [{"field": "senha", "rule": "X", "message": "tok-SEGREDO-123"}]})

    excerpt = sanitize_excerpt(body.encode(), lambda text: text.replace("tok-SEGREDO-123", "***"))

    assert "tok-SEGREDO" not in excerpt
    assert '"field": "senha"' in excerpt


def test_an_error_body_without_per_field_items_keeps_the_old_truncation() -> None:
    body = json.dumps({"message": "x" * 500})

    assert len(sanitize_excerpt(body.encode(), lambda text: text)) <= EXCERPT_CAP

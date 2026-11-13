import copy
import io
import json
import sys
from collections.abc import Mapping

import pytest
import structlog

from harness_dast.observability.logging import (
    MASK,
    SecretRegistry,
    build_redactor,
    configure_logging,
    redact_value,
)

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl"


def _redact(
    event: Mapping[str, object], registry: SecretRegistry | None = None
) -> dict[str, object]:
    processor = build_redactor(registry or SecretRegistry())
    return dict(processor(None, "info", dict(event)))


def test_value_is_masked_when_key_is_sensitive() -> None:
    event = {
        "Authorization": "Bearer abc",
        "set-cookie": "sid=1",
        "Password": "x",
        "access_token": "t",
        "client_secret": "s",
        "X-Api-Key": "k",
        "event": "login",
    }

    result = _redact(event)

    assert result.pop("event") == "login"
    assert set(result.values()) == {MASK}


def test_nested_values_are_masked_when_inside_dict_and_list() -> None:
    event = {
        "event": "req",
        "headers": {"cookie": "a=b", "accept": "json"},
        "items": [{"token": "z"}],
    }

    result = _redact(event)

    assert result["headers"] == {"cookie": MASK, "accept": "json"}
    assert result["items"] == [{"token": MASK}]


def test_registered_secret_is_masked_when_it_appears_inside_text() -> None:
    registry = SecretRegistry()
    registry.register("s3nh4-longa")

    result = _redact({"event": "falhou com s3nh4-longa no corpo"}, registry)

    assert result["event"] == f"falhou com {MASK} no corpo"


def test_longer_secret_is_fully_masked_when_it_contains_shorter_one() -> None:
    registry = SecretRegistry()
    registry.register("abcd")
    registry.register("abcd1234")

    assert registry.mask("valor abcd1234") == f"valor {MASK}"


def test_empty_secret_is_ignored_when_registered() -> None:
    registry = SecretRegistry()
    registry.register("")

    assert registry.mask("texto intacto") == "texto intacto"


def test_jwt_is_masked_when_found_in_free_text() -> None:
    result = _redact({"event": f"resposta {JWT} recebida"})

    assert result["event"] == f"resposta {MASK} recebida"


def test_formatted_cpf_is_masked_when_found_in_text() -> None:
    result = _redact({"event": "paciente 123.456.789-09 criado"})

    assert result["event"] == f"paciente {MASK} criado"


def test_text_is_unchanged_when_nothing_sensitive() -> None:
    event = {
        "event": "pedido 12345678909 id 123.456 versão eyJ",
        "status": 200,
        "user": "user_a",
        "tokens_ok": None,
    }

    result = _redact(event)

    assert result["event"] == event["event"]
    assert result["status"] == 200
    assert result["user"] == "user_a"


def test_cpf_is_not_masked_when_embedded_in_longer_digit_sequence() -> None:
    assert redact_value("9123.456.789-091", SecretRegistry()) == "9123.456.789-091"


def test_input_is_not_modified_when_redacting() -> None:
    event: dict[str, object] = {"password": "x", "nested": {"token": "y"}, "event": JWT}
    original = copy.deepcopy(event)

    _redact(event)

    assert event == original


def test_logs_are_json_on_given_stream_and_redacted_when_configured() -> None:
    stream = io.StringIO()
    registry = SecretRegistry()
    registry.register("segredo-123")
    configure_logging("INFO", registry, stream)

    structlog.get_logger().info("evento", detalhe="usou segredo-123", authorization="Bearer x")
    structlog.get_logger().debug("ignorado")

    lines = stream.getvalue().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "evento"
    assert record["level"] == "info"
    assert record["detalhe"] == f"usou {MASK}"
    assert record["authorization"] == MASK
    assert "segredo-123" not in lines[0]


def test_traceback_is_redacted_when_exception_is_logged() -> None:
    stream = io.StringIO()
    registry = SecretRegistry()
    registry.register("segredo-123")
    configure_logging("INFO", registry, stream)

    try:
        raise ValueError("falha com segredo-123")  # noqa: TRY301
    except ValueError:
        structlog.get_logger().exception("erro")

    assert "segredo-123" not in stream.getvalue()


def test_redact_value_keeps_pair_of_free_text_when_first_item_only_mentions_a_sensitive_word() -> (
    None
):
    result = redact_value(("token expirado", "tente de novo"), SecretRegistry())

    assert result == ["token expirado", "tente de novo"]


def test_redact_value_masks_second_item_when_pair_has_sensitive_header_name() -> None:
    assert redact_value(("X-Api-Key", "abc"), SecretRegistry()) == ["X-Api-Key", MASK]


def test_redact_value_decodes_bytes_with_invalid_utf8_without_failing() -> None:
    assert redact_value(b"\xff\xfeok", SecretRegistry()) == "\ufffd\ufffdok"


def test_logs_go_to_the_current_stderr_when_it_is_replaced_after_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = io.StringIO()
    monkeypatch.setattr(sys, "stderr", first)
    configure_logging("INFO", SecretRegistry())
    first.close()
    second = io.StringIO()
    monkeypatch.setattr(sys, "stderr", second)

    structlog.get_logger().info("evento")

    assert "evento" in second.getvalue()

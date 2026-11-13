"""Testes independentes (QA) da redação de segredos nos logs."""

# ruff: noqa: S105, S104, S603, RUF001, RUF100, PT011, TRY301

import io
import json

import pytest
import structlog

from harness_dast.observability.logging import (
    MASK,
    SecretRegistry,
    configure_logging,
    redact_value,
)

JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
    "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
)
JWT_NO_SIG = "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxIn0."
CPF = "123.456.789-09"


def render(**event: object) -> dict[str, object]:
    """Registra um evento pelo structlog configurado de verdade e devolve o JSON emitido."""
    stream = io.StringIO()
    registry = event.pop("_registry", None)
    configure_logging(
        "DEBUG", registry if isinstance(registry, SecretRegistry) else SecretRegistry(), stream
    )
    structlog.get_logger().info("evento", **event)
    line = stream.getvalue().strip().splitlines()[-1]
    return json.loads(line)  # type: ignore[no-any-return]  # json.loads devolve Any


def raw(**event: object) -> str:
    stream = io.StringIO()
    registry = event.pop("_registry", None)
    configure_logging(
        "DEBUG", registry if isinstance(registry, SecretRegistry) else SecretRegistry(), stream
    )
    structlog.get_logger().info("evento", **event)
    return stream.getvalue()


@pytest.mark.parametrize(
    "key",
    [
        "authorization",
        "Authorization",
        "AUTHORIZATION",
        "Proxy-Authorization",
        "proxy_authorization",
        "ProxyAuthorization",
        "cookie",
        "Set-Cookie",
        "SET_COOKIE",
        "password",
        "Password",
        "user_password",
        "passwd",
        "token",
        "access_token",
        "accessToken",
        "refresh-token",
        "id_token",
        "x-auth-token",
        "secret",
        "client_secret",
        "api_key",
        "API_KEY",
        "x-api-key",
        "X-API-KEY",
        "apikey",
        "ApiKey",
    ],
)
def test_value_is_masked_when_key_is_sensitive_in_any_casing(key: str) -> None:
    assert render(**{key: "valor-sensivel"})[key] == MASK


@pytest.mark.parametrize("key", ["senha", "Senha", "private_key", "credentials"])
def test_value_is_masked_when_key_names_a_credential_in_portuguese_or_common_aliases(
    key: str,
) -> None:
    # O projeto usa SENHA/CHAVE nos nomes de variáveis (ver .env.example e o template).
    assert render(**{key: "valor-sensivel"})[key] == MASK


def test_value_is_masked_when_secret_is_deep_inside_nested_structures() -> None:
    event = {
        "a": {"b": [{"c": ({"Authorization": "Bearer xyz"},)}]},
        "headers": [{"Cookie": "sid=1"}],
    }

    out = raw(**event)

    assert "Bearer xyz" not in out
    assert "sid=1" not in out


def test_value_is_masked_when_dict_key_is_sensitive_inside_list_of_pairs() -> None:
    # Cabeçalhos HTTP costumam chegar como lista de pares; o par ("Cookie", "sid=1") não
    # tem chave de dict, então só a redação por valor ou por posição pegaria.
    out = raw(headers=[("Authorization", "opaque-token-123")])

    assert "opaque-token-123" not in out


@pytest.mark.parametrize("secret", [JWT, JWT_NO_SIG, CPF])
def test_value_is_masked_when_jwt_or_cpf_is_embedded_in_longer_text(secret: str) -> None:
    for text in (
        f"falhou com {secret} no meio",
        f"Authorization: Bearer {secret}",
        f"x={secret};y=2",
        f"\n{secret}\n",
        f'{{"token": "{secret}"}}',
        f"({secret})",
    ):
        assert secret not in raw(mensagem=text), text


def test_value_is_masked_when_jwt_or_cpf_is_inside_exception_text() -> None:
    try:
        raise RuntimeError(f"falha ao chamar com {JWT} e cpf {CPF}")  # noqa: TRY301, TRY003
    except RuntimeError:
        stream = io.StringIO()
        configure_logging("DEBUG", SecretRegistry(), stream)
        structlog.get_logger().exception("erro")

    assert JWT not in stream.getvalue()
    assert CPF not in stream.getvalue()


def test_value_is_masked_when_exception_object_is_passed_as_field() -> None:
    # Objetos que não são str/dict/list chegam ao renderizador via repr/str sem passar pela redação.
    error = RuntimeError(f"upstream devolveu {JWT}")

    assert JWT not in raw(error=error)


def test_value_is_masked_when_registered_secret_is_inside_object_repr() -> None:
    registry = SecretRegistry()
    registry.register("senha-registrada-xyz")

    class Conn:
        def __repr__(self) -> str:
            return "Conn(dsn='u/senha-registrada-xyz@db')"

    assert "senha-registrada-xyz" not in raw(conn=Conn(), _registry=registry)


def test_value_is_masked_when_secret_is_in_a_set_or_bytes() -> None:
    registry = SecretRegistry()
    registry.register("senha-registrada-xyz")

    out = raw(
        conjunto={"senha-registrada-xyz"}, binario=b"senha-registrada-xyz", _registry=registry
    )

    assert "senha-registrada-xyz" not in out


@pytest.mark.parametrize(
    "text",
    [
        "12345678909",
        "123.456.789",
        "123.456.789-0",
        "1123.456.789-09",
        "123.456.789-091",
        "eyJ",
        "eyJhbGci.abc",
        "eyJhbGci",
        "2026-11-13T12:00:00Z",
        "550e8400-e29b-41d4-a716-446655440000",
        "GET /api/users/42",
        "1.2.3.4",
        "token expirado",  # o texto cita a palavra, mas não é um valor
    ],
)
def test_text_is_untouched_when_it_is_not_a_secret(text: str) -> None:
    assert render(mensagem=text)["mensagem"] == text


@pytest.mark.parametrize("value", [0, 1, 3.14, True, None, 12345678909])
def test_scalar_is_untouched_when_value_is_not_text(value: object) -> None:
    assert render(valor=value)["valor"] == value


def test_registry_masks_every_occurrence_and_longest_first() -> None:
    registry = SecretRegistry()
    registry.register("abc")
    registry.register("abcdef")

    assert registry.mask("x abcdef y abc z abcdefabc") == f"x {MASK} y {MASK} z {MASK}{MASK}"


def test_registry_ignores_empty_value_and_does_not_mask_everything() -> None:
    registry = SecretRegistry()
    registry.register("")

    assert registry.mask("texto normal") == "texto normal"


def test_registry_masks_secret_registered_after_logging_was_configured() -> None:
    registry = SecretRegistry()
    stream = io.StringIO()
    configure_logging("DEBUG", registry, stream)
    registry.register("registrado-depois-123")

    structlog.get_logger().info("x", msg="valor registrado-depois-123 aqui")

    assert "registrado-depois-123" not in stream.getvalue()


def test_registry_masks_secret_even_if_it_contains_regex_metacharacters() -> None:
    registry = SecretRegistry()
    registry.register("a.b*c(d)[e]+?")

    assert registry.mask("p a.b*c(d)[e]+? q") == f"p {MASK} q"


def test_redact_value_does_not_mutate_input() -> None:
    value = {"a": [{"token": "t"}, CPF], "b": (JWT,)}
    snapshot = json.dumps(value, sort_keys=True)

    redact_value(value, SecretRegistry())

    assert json.dumps(value, sort_keys=True) == snapshot


def test_event_message_itself_is_redacted() -> None:
    stream = io.StringIO()
    configure_logging("DEBUG", SecretRegistry(), stream)

    structlog.get_logger().info(f"login de {CPF} com {JWT}")

    assert CPF not in stream.getvalue()
    assert JWT not in stream.getvalue()


def test_logs_go_to_the_given_stream_and_are_one_json_object_per_line() -> None:
    stream = io.StringIO()
    configure_logging("INFO", SecretRegistry(), stream)

    structlog.get_logger().info("um")
    structlog.get_logger().debug("dois")
    structlog.get_logger().warning("tres")

    lines = stream.getvalue().strip().splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["um", "tres"]


def test_configure_logging_raises_or_defaults_safely_when_level_is_unknown() -> None:
    stream = io.StringIO()
    try:
        configure_logging("NADA", SecretRegistry(), stream)
        structlog.get_logger().info("x")
    except (ValueError, TypeError, KeyError):
        return
    # Se aceitar, nível desconhecido não pode silenciar os erros.
    structlog.get_logger().error("y")
    assert "y" in stream.getvalue()

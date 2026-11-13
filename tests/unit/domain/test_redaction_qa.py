# ruff: noqa: S105, RUF001
"""QA independente da redação de evidência (`domain/redaction.py`).

Contrato (docstring): cabeçalhos de autenticação, cookies e chaves têm o valor trocado; JWT,
Bearer/Basic, CPF, e-mail e sequências longas são trocados em QUALQUER lugar; corpos JSON e
formulário têm valores de campos sensíveis trocados; segredos registrados são trocados mesmo que
escapem das regras; ANSI, controle e bidi são removidos; o corte vem DEPOIS da redação.
"""

import base64
import json
from urllib.parse import quote, quote_plus

import pytest

from harness_dast.domain.redaction import (
    BODY_CAP,
    MASK,
    redact_alert,
    redact_body,
    redact_header_block,
    redact_message,
    redact_text,
    redact_url,
    strip_control,
)
from harness_dast.domain.zap_messages import ZapMessage
from harness_dast.observability.logging import SecretRegistry

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
PASSWORD = "S3nh@/forte!&=x y"


def registry(*secrets: str) -> SecretRegistry:
    reg = SecretRegistry()
    for secret in secrets:
        reg.register(secret)
    return reg


def no_mask(text: str) -> str:
    return text


# ------------------------------------------------------------------ padrões em qualquer lugar


@pytest.mark.parametrize(
    "template",
    ["{}", "token: {}", "GET /x?q={} HTTP/1.1", '{{"nota": "veja {}"}}', "a\n{}\nb"],
)
def test_redact_text_masks_a_jwt_wherever_it_appears(template: str) -> None:
    out = redact_text(template.format(JWT), no_mask)

    assert "eyJhbGci" not in out
    assert "SflKxw" not in out


@pytest.mark.parametrize(
    "text",
    [
        "Bearer abcdefghijklmnop",
        "bearer abcdefghijklmnop",
        "Basic dXNlcjpwYXNz",
        "Token abcdefgh12345",
    ],
)
def test_redact_text_masks_scheme_tokens_regardless_of_case(text: str) -> None:
    out = redact_text(f"Authorization is {text}.", no_mask)

    assert text.split()[1] not in out


@pytest.mark.parametrize("cpf", ["529.982.247-25", "52998224725"])
def test_redact_text_masks_cpf_with_and_without_punctuation(cpf: str) -> None:
    assert cpf not in redact_text(f"cpf={cpf};", no_mask)


def test_redact_text_masks_email_addresses() -> None:
    assert "maria.silva+x@exemplo.com.br" not in redact_text(
        "dono: maria.silva+x@exemplo.com.br", no_mask
    )


def test_redact_text_keeps_ordinary_text_untouched() -> None:
    text = "Content-Type: application/json; total=12; id=4455"

    assert redact_text(text, no_mask) == text


def test_redact_text_is_idempotent() -> None:
    reg = registry(PASSWORD)
    once = redact_text(f"u={JWT} p={PASSWORD} cpf=529.982.247-25 password=abc", reg.mask)

    assert redact_text(once, reg.mask) == once


# --------------------------------------------------------------------- segredos registrados


def test_redact_text_masks_a_registered_secret_in_every_occurrence() -> None:
    reg = registry(PASSWORD)

    out = redact_text(f"{PASSWORD} e de novo {PASSWORD}", reg.mask)

    assert PASSWORD not in out


def test_redact_body_masks_a_registered_secret_inside_json_string_values() -> None:
    reg = registry(PASSWORD)
    body = json.dumps({"mensagem": f"senha enviada: {PASSWORD}", "n": 1})

    out, _ = redact_body(body, reg.mask)

    assert "forte" not in out


def test_redact_body_masks_a_registered_secret_that_json_escapes_differently() -> None:
    secret = 'ab"c\\d/é'
    reg = registry(secret)
    body = json.dumps({"x": f"valor {secret}"}, ensure_ascii=True)

    out, _ = redact_body(body, reg.mask)

    assert "ab" not in out.replace("***", "") or secret not in out
    assert "c\\\\d" not in out


@pytest.mark.parametrize("encode", [quote, lambda s: quote(s, safe=""), quote_plus])
def test_redact_body_masks_a_registered_secret_sent_in_percent_encoded_form(encode: object) -> None:
    # Defeito: `SecretRegistry.mask` só troca a forma literal. Um segredo com `@`, `/`, `!` ou
    # espaço, enviado em formulário/URL (`application/x-www-form-urlencoded`), aparece
    # codificado (`S3nh%40%2Fforte%21...`) e passa direto quando o nome do campo não é um dos
    # "sensíveis" (`pw`, `pass`, `pin`, `chave`...).
    reg = registry(PASSWORD)
    encoded = encode(PASSWORD)  # type: ignore[operator]
    body = f"login=maria&pw={encoded}"

    out, _ = redact_body(body, reg.mask)

    assert "forte" not in out
    assert "%2Fforte" not in out


def test_redact_url_masks_a_registered_secret_sent_in_percent_encoded_form() -> None:
    reg = registry(PASSWORD)
    url = f"https://api.exemplo.com/login?pw={quote(PASSWORD, safe='')}&u=maria"

    out = redact_url(url, reg.mask)

    assert "forte" not in out


def test_redact_header_block_masks_a_registered_secret_in_a_non_sensitive_header() -> None:
    reg = registry(PASSWORD)

    out, _ = redact_header_block(f"GET /x HTTP/1.1\nX-Debug: {PASSWORD}\nHost: a", reg.mask)

    assert PASSWORD not in out


def test_redact_text_masks_the_base64_form_of_a_registered_secret() -> None:
    secret = "senha-de-teste-9"
    reg = registry(secret)
    encoded = base64.b64encode(secret.encode()).decode()

    assert encoded not in redact_text(f"dado={encoded}", reg.mask)


# --------------------------------------------------------------------------- cabeçalhos


@pytest.mark.parametrize(
    "name",
    [
        "Authorization",
        "authorization",
        "Proxy-Authorization",
        "Cookie",
        "Set-Cookie",
        "X-Api-Key",
        "X-API-KEY",
        "X-CSRF-Token",
        "X-XSRF-TOKEN",
        "X-Auth-Token",
        "X-Session-Id",
        "X-Amz-Security-Token",
        "X-Secret",
    ],
)
def test_redact_header_block_masks_the_value_of_sensitive_headers(name: str) -> None:
    out, _ = redact_header_block(f"GET /x HTTP/1.1\nHost: a\n{name}: valor-secreto-123", no_mask)

    assert "valor-secreto-123" not in out
    assert "Host: a" in out


def test_redact_header_block_keeps_non_sensitive_headers_and_the_request_line() -> None:
    out, _ = redact_header_block(
        "POST /api/pedidos HTTP/1.1\nHost: api.exemplo.com\nContent-Type: application/json", no_mask
    )

    assert out.splitlines() == [
        "POST /api/pedidos HTTP/1.1",
        "Host: api.exemplo.com",
        "Content-Type: application/json",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer abcdefghijklmnop",
        "authorization=Bearer opaque-token-xyz",
        "Authorization: Basic dXNlcjpwYXNz",
        "Proxy-Authorization: Bearer abcdefghijklmnop",
    ],
)
def test_redact_text_masks_the_credential_and_not_only_the_scheme_word(text: str) -> None:
    # Defeito: `_PAIR` consome a palavra `Bearer`/`Basic` como se fosse o valor e a troca por
    # `***`; o token de verdade (opaco, curto ou sem dígito, portanto fora de `_LONG_TOKEN` e de
    # `_JWT`) sobra em claro: `Authorization: *** abcdefghijklmnop`. Vale para corpo, alerta do
    # ZAP e qualquer texto livre; só o cabeçalho HTTP "de verdade" é tratado por nome.
    secret = text.split()[-1]

    for out in (
        redact_text(text, no_mask),
        redact_body(text, no_mask)[0],
        redact_alert({"evidence": text}, no_mask)["evidence"],
    ):
        assert secret not in out


def test_redact_header_block_masks_credentials_embedded_in_the_request_line() -> None:
    out, _ = redact_header_block(
        "GET https://user:pass@host.exemplo.com/x HTTP/1.1\nHost: a", no_mask
    )

    assert "user:pass" not in out


# ------------------------------------------------------------------------------ corpos


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "Password",
        "senha",
        "client_secret",
        "access_token",
        "api_key",
        "apiKey",
        "authorization",
        "csrf_token",
        "sessionId",
        "credential",
        "passwd",
        "pwd",
    ],
)
def test_redact_body_masks_json_values_of_sensitive_names_at_any_depth(key: str) -> None:
    body = json.dumps({"a": {"b": [{key: "valor-secreto-123"}]}, key: "valor-secreto-123"})

    out, _ = redact_body(body, no_mask)

    assert "valor-secreto-123" not in out


def test_redact_body_keeps_non_sensitive_json_values() -> None:
    out, _ = redact_body(json.dumps({"nome": "Maria", "total": 12, "ok": True}), no_mask)

    assert json.loads(out) == {"nome": "Maria", "total": 12, "ok": True}


def test_redact_body_masks_non_string_values_of_sensitive_names() -> None:
    out, _ = redact_body(json.dumps({"senha": 123456, "token": ["a", "b"]}), no_mask)

    assert "123456" not in out


@pytest.mark.parametrize(
    "body",
    [
        "password=abc123&user=maria",
        "user=maria&senha=abc123",
        "token=abc123",
        "Authorization: abc123",
    ],
)
def test_redact_body_masks_sensitive_pairs_in_forms_and_free_text(body: str) -> None:
    out, _ = redact_body(body, no_mask)

    assert "abc123" not in out


@pytest.mark.parametrize(
    "body", ["{", "[1,", '{"a": ', "\x00\x01", "{" * 5000, "[" * 5000 + "]" * 5000]
)
def test_redact_body_never_raises_on_malformed_or_hostile_bodies(body: str) -> None:
    out, _ = redact_body(body, no_mask)

    assert isinstance(out, str)


def test_redact_body_cuts_to_the_cap_and_reports_truncation() -> None:
    out, truncated = redact_body("x" * (BODY_CAP * 3), no_mask)

    assert truncated is True
    assert len(out) <= BODY_CAP


def test_redact_body_redacts_before_cutting_so_a_secret_on_the_boundary_never_leaks() -> None:
    reg = registry("segredo-no-limite-12345")
    body = "a" * (BODY_CAP - 8) + "segredo-no-limite-12345" + "b" * 50

    out, _ = redact_body(body, reg.mask)

    assert "segredo" not in out
    assert "limite" not in out


def test_redact_body_returns_empty_for_blank_input() -> None:
    assert redact_body("   \n ", no_mask) == ("", False)


# ---------------------------------------------------------------------------------- url


def test_redact_url_masks_userinfo_and_sensitive_query_values() -> None:
    out = redact_url(
        "https://usuario:senha123@api.exemplo.com/x?token=abc&page=2&api_key=k1", no_mask
    )

    assert "senha123" not in out
    assert "token=abc" not in out
    assert "k1" not in out
    assert "page=2" in out


# --------------------------------------------------------------------------- controle


def test_strip_control_removes_ansi_bidi_zero_width_and_nul() -> None:
    text = "a\x1b[31mb\x1b[0m‮c​d\x00e\x07f"

    assert strip_control(text) == "abcdef"


def test_strip_control_turns_line_separators_into_spaces_and_drops_carriage_return() -> None:
    assert strip_control("a b\r\nc", keep_newlines=True) == "a b\nc"
    assert "\n" not in strip_control("a\nb", keep_newlines=False)


def test_redact_alert_preserves_keys_and_redacts_every_text_field() -> None:
    reg = registry(PASSWORD)
    alert = {
        "url": f"https://a.exemplo.com/x?token=abc&q={quote(PASSWORD, safe='')}",
        "evidence": f"Authorization: Bearer {JWT}",
        "other": f"o valor {PASSWORD} apareceu",
        "attack": "' OR 1=1 --",
    }

    out = redact_alert(alert, reg.mask)

    assert set(out) == set(alert)
    assert "token=abc" not in out["url"]
    assert "eyJhbGci" not in out["evidence"]
    assert PASSWORD not in out["other"]
    assert out["attack"] == "' OR 1=1 --"


def test_redact_message_redacts_the_four_parts_and_keeps_the_message_id() -> None:
    reg = registry(PASSWORD)
    message = ZapMessage(
        id=42,
        type="1",
        request_header=f"POST /login HTTP/1.1\nHost: a\nAuthorization: Bearer {JWT}",
        request_body=json.dumps({"senha": PASSWORD, "user": "maria"}),
        response_header="HTTP/1.1 200 OK\nSet-Cookie: sid=abc123def456",
        response_body=json.dumps({"access_token": JWT, "echo": PASSWORD}),
    )

    out = redact_message(message, reg.mask)

    dumped = out.model_dump_json()
    assert out.message_id == 42
    assert "eyJhbGci" not in dumped
    assert "abc123def456" not in dumped
    assert "forte" not in dumped


def test_mask_constant_is_the_documented_placeholder() -> None:
    assert MASK == "***"

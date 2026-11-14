"""Codificação de requisições montadas e do login."""

import json

import pytest

from harness_dast.domain.auth import PasswordLoginAuth
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.request_builder import BuiltRequest
from harness_dast.domain.request_encoding import (
    build_get_request,
    build_login_request,
    encode_body,
    encode_built_request,
    join_url,
)

BASE = "https://api.hml.acme-teste.net.br/v2"


def built(**changes: object) -> BuiltRequest:
    data: dict[str, object] = {"operation_id": "op", "method": "POST", "path": "/pacientes"}
    return BuiltRequest.model_validate(data | changes)


def auth(**changes: object) -> PasswordLoginAuth:
    data = {
        "type": "login_password",
        "token_path": "/auth/login",
        "accounts": [
            {
                "alias": "user_a",
                "role": "x",
                "username": {"secret_ref": "env:U"},
                "password": {"secret_ref": "env:P"},
            }
        ],
    } | changes
    return PasswordLoginAuth.model_validate(data)


def test_join_url_keeps_the_base_prefix_and_encodes_the_query() -> None:
    assert join_url(BASE + "/", "/a", (("q", "a b"), ("n", "1"))) == f"{BASE}/a?q=a+b&n=1"
    assert join_url(BASE, "/a") == f"{BASE}/a"


def test_json_body_is_compact_utf8_with_the_media_type() -> None:
    payload, content_type = encode_body({"nome": "João", "n": 1}, "application/json; charset=utf-8")

    assert payload == '{"nome":"João","n":1}'.encode()
    assert content_type == "application/json"


def test_vendor_json_and_form_and_text_bodies_are_supported() -> None:
    assert encode_body({"a": 1}, "application/vnd.api+json")[1] == "application/vnd.api+json"
    assert (
        encode_body({"a": 1, "b": True, "c": None}, "application/x-www-form-urlencoded")[0]
        == b"a=1&b=true&c="
    )
    assert encode_body("oi", "text/plain") == (b"oi", "text/plain")
    assert encode_body(None, "application/json") == (None, None)
    assert encode_body({"a": 1}, None) == (None, None)


@pytest.mark.parametrize(
    ("body", "media"),
    [
        ({"a": 1}, "multipart/form-data"),
        ({"a": 1}, "application/octet-stream"),
        ([1], "application/x-www-form-urlencoded"),
        ({"a": {"b": 1}}, "application/x-www-form-urlencoded"),
    ],
)
def test_unsupported_bodies_are_config_errors_with_a_hint(body: object, media: str) -> None:
    with pytest.raises(ConfigError) as info:
        encode_body(body, media)  # type: ignore[arg-type]

    assert info.value.hint


def test_encode_built_request_assembles_url_headers_cookies_and_body() -> None:
    request = encode_built_request(
        built(
            query=(("page", "2"),),
            headers={"X-Trace": "1"},
            cookies={"a": "b", "c": "d"},
            body={"nome": "x"},
            body_media_type="application/json",
        ),
        base_url=BASE,
        extra_headers=(("Authorization", "Bearer t"),),
        account="user_a",
    )

    assert request.url == f"{BASE}/pacientes?page=2"
    assert dict(request.headers) == {
        "X-Trace": "1",
        "Cookie": "a=b; c=d",
        "Content-Type": "application/json",
        "Authorization": "Bearer t",
    }
    assert request.body == b'{"nome":"x"}'
    assert (request.account, request.route, request.operation_id) == ("user_a", "zap", "op")


def test_a_request_without_body_has_no_content_type() -> None:
    request = encode_built_request(built(method="GET"), base_url=BASE)

    assert request.body is None
    assert "Content-Type" not in dict(request.headers)


def test_login_request_uses_json_or_form_as_the_profile_says() -> None:
    as_json = build_login_request(
        auth(request_encoding="json", username_field="u", password_field="p"),  # noqa: S106 - sentinela ou nome de campo, não um segredo
        base_url=BASE,
        account="user_a",
        username="alice",
        password="s3",  # noqa: S106 - sentinela ou nome de campo, não um segredo
    )
    as_form = build_login_request(
        auth(),
        base_url=BASE,
        account="user_a",
        username="alice",
        password="s 3&",  # noqa: S106 - sentinela ou nome de campo, não um segredo
    )

    assert json.loads(as_json.body or b"") == {"u": "alice", "p": "s3"}
    assert dict(as_json.headers)["Content-Type"] == "application/json"
    assert as_form.body == b"username=alice&password=s+3%26"
    assert dict(as_form.headers)["Content-Type"] == "application/x-www-form-urlencoded"
    assert (as_json.method, as_json.route, as_json.operation_id) == ("POST", "auth", "auth.login")
    assert as_json.url == f"{BASE}/auth/login"


def test_get_request_is_a_plain_get_on_the_chosen_route() -> None:
    request = build_get_request(
        base_url=BASE, path="/saude", operation_id="auth.csrf", account="user_a", route="auth"
    )

    assert (request.method, request.url, request.route) == ("GET", f"{BASE}/saude", "auth")
    assert request.body is None


def test_built_multipart_request_remains_refused() -> None:
    with pytest.raises(ConfigError):
        encode_built_request(
            built(body={"arquivo": "synthetic"}, body_media_type="multipart/form-data"),
            base_url=BASE,
        )

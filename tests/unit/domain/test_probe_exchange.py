"""`exchanges.json`: o que o `probe` guarda para o teste de autorização, sem segredo."""

import json

from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.probe_exchange import MAX_BODY_CHARS, ExchangeLog, build_exchange

BASE = "https://api.exemplo.test"


def identity(text: str) -> str:
    return text


def masking(secret: str):  # type: ignore[no-untyped-def]  # fábrica de teste
    return lambda text: text.replace(secret, "***")


def request(
    method: str = "GET",
    url: str = f"{BASE}/api/x/1?q=2",
    body: object = None,
    content_type: str = "application/json",
    account: str | None = "a1",
    raw: bytes | None = None,
) -> HttpRequest:
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    headers = (("Content-Type", content_type),) if data else ()
    return HttpRequest(
        method=method,
        url=url,
        headers=headers,
        body=data,
        operation_id="op",
        account=account,
    )


def build(req: HttpRequest, mask=identity):  # type: ignore[no-untyped-def]  # auxiliar
    return build_exchange(
        request=req, path_template="/api/x/{id}", status=200, base_url=BASE, mask=mask
    )


def test_a_get_keeps_the_concrete_target_and_no_body() -> None:
    record = build(request())

    assert record is not None
    assert record.target == "/api/x/1?q=2"
    assert record.path == "/api/x/{id}"
    assert record.account == "a1"
    assert record.body is None


def test_a_base_url_with_a_trailing_slash_or_prefix_still_yields_a_relative_target() -> None:
    record = build_exchange(
        request=request(url=f"{BASE}/v1/api/x/1"),
        path_template="/api/x/{id}",
        status=200,
        base_url=f"{BASE}/v1/",
        mask=identity,
    )

    assert record is not None
    assert record.target == "/api/x/1"


def test_a_json_body_is_kept_for_put_patch_and_post_only() -> None:
    put = build(request("PUT", body={"nome": "a"}))
    get = build(request("GET", body={"nome": "a"}))

    assert put is not None
    assert put.body == '{"nome":"a"}'
    assert put.content_type == "application/json"
    assert get is not None
    assert get.body is None


def test_secret_named_fields_are_removed_and_listed() -> None:
    record = build(request("POST", body={"nome": "a", "senha": "x", "dados": {"apiKey": "y"}}))

    assert record is not None
    assert json.loads(record.body or "") == {"nome": "a", "dados": {}}
    assert record.omitted_fields == ("senha", "apiKey")


def test_a_registered_secret_in_the_target_discards_the_record() -> None:
    assert build(request(url=f"{BASE}/api/x/1?k=SEGREDO"), masking("SEGREDO")) is None


def test_a_registered_secret_in_the_body_discards_the_record() -> None:
    assert build(request("PUT", body={"nome": "SEGREDO"}), masking("SEGREDO")) is None


def test_anonymous_requests_and_foreign_urls_are_never_recorded() -> None:
    assert build(request(account=None)) is None
    assert build(request(url="https://outro.test/api/x/1")) is None


def test_non_json_oversized_or_malformed_bodies_are_not_kept() -> None:
    assert (
        build(request("PUT", raw=b"a=1", content_type="application/x-www-form-urlencoded")).body
        is None
    )
    assert build(request("PUT", raw=b"{oops")).body is None
    assert build(request("PUT", raw=b"\xff\xfe")).body is None
    assert build(request("PUT", body={"nome": "a" * (MAX_BODY_CHARS + 1)})) is None


def test_the_log_roundtrips() -> None:
    record = build(request())
    log = ExchangeLog(run_id="r", product="p", exchanges=(record,))

    assert ExchangeLog.model_validate_json(log.model_dump_json()) == log

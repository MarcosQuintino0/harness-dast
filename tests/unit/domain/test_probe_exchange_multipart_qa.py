"""QA independente (V1.5c): `exchanges.json` com multipart nunca guarda valor nem arquivo."""

import json

import pytest

from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.multipart_encoding import encode_multipart
from harness_dast.domain.probe_exchange import ExchangeLog, ExchangeRecord, build_exchange
from harness_dast.domain.synthetic_files import FileSpec

BASE = "https://api.exemplo.test"
SECRET = "tok-super-secreto-12345"  # noqa: S105 - sentinela de teste


def masker(text: str) -> str:
    return text.replace(SECRET, "***")


def upload(
    fields: list[tuple[str, str]], files: list[FileSpec] | None = None, method: str = "POST"
) -> HttpRequest:
    content_type, body = encode_multipart(
        fields,
        files if files is not None else [FileSpec(field="arq", kind="text", filename="a.txt")],
    )
    return HttpRequest(
        method=method,
        url=f"{BASE}/api/docs",
        headers=(("Content-Type", content_type),),
        body=body,
        operation_id="enviar",
        account="a1",
    )


def record(request: HttpRequest) -> ExchangeRecord | None:
    return build_exchange(
        request=request, path_template="/api/docs", status=201, base_url=BASE, mask=masker
    )


def test_a_registered_secret_in_a_text_value_discards_the_whole_record() -> None:
    assert record(upload([("nota", f"antes {SECRET} depois")])) is None


@pytest.mark.parametrize("field", ["password", "senha", "token", "api_key", "secret"])
def test_a_secret_named_text_field_is_omitted_from_the_summary_and_listed(field: str) -> None:
    result = record(upload([(field, "valor"), ("nota", "x")]))

    assert result is not None
    assert result.multipart is not None
    assert field in result.omitted_fields
    assert field not in [part.name for part in result.multipart.parts]
    assert "valor" not in result.model_dump_json()


def test_a_multipart_request_with_a_get_method_has_no_body_record() -> None:
    result = record(upload([("nota", "x")], method="GET"))

    assert result is not None
    assert result.multipart is None
    assert result.body is None


def test_a_multipart_content_type_with_a_garbage_body_is_discarded_not_stored() -> None:
    request = HttpRequest(
        method="POST",
        url=f"{BASE}/api/docs",
        headers=(("Content-Type", "multipart/form-data; boundary=zzz"),),
        body=b"nada de multipart aqui " + SECRET.encode(),
        operation_id="enviar",
        account="a1",
    )

    assert record(request) is None


def test_the_serialised_log_never_has_value_boundary_or_file_bytes() -> None:
    result = record(upload([("nota", "valor-visivel-123")]))
    assert result is not None
    log = ExchangeLog(run_id="r", product="p", exchanges=(result,))

    text = log.model_dump_json()

    assert "valor-visivel-123" not in text
    assert "harness-" not in text
    assert "synthetic file" not in text
    assert json.loads(text)["exchanges"][0]["body"] is None


@pytest.mark.parametrize(
    "target",
    ["//evil.com/x", "/a b", "/a\\b", "/a\tb", "/a#frag", "http://x/y", "a/b", "/a\nb", "/‮"],
)
def test_a_tampered_target_never_validates_in_the_record(target: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - o pydantic levanta `ValidationError` (ValueError)
        ExchangeRecord(
            operation_id="x", method="GET", path="/x", target=target, account="a", status=200
        )

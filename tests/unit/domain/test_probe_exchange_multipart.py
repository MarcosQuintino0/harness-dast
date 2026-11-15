"""`exchanges.json` com envio de arquivo (ADR 0052): só o resumo, nunca o corpo."""

import json

from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.multipart_encoding import encode_multipart
from harness_dast.domain.probe_exchange import ExchangeLog, ExchangeRecord, build_exchange
from harness_dast.domain.synthetic_files import FileSpec, file_content

BASE = "https://api.exemplo.test"
PNG_SIGNATURE = b"\x89PNG"


def identity(text: str) -> str:
    return text


def upload(
    fields: list[tuple[str, str]] | None = None,
    kind: str = "png",
    name: str = "foto.png",
    account: str | None = "a1",
    url: str = f"{BASE}/api/docs",
) -> HttpRequest:
    content_type, body = encode_multipart(
        fields if fields is not None else [("descricao", "texto qualquer")],
        [FileSpec(field="arquivo", kind=kind, filename=name)],  # type: ignore[arg-type]
    )
    return HttpRequest(
        method="POST",
        url=url,
        headers=(("Content-Type", content_type),),
        body=body,
        operation_id="enviar",
        account=account,
    )


def record(request: HttpRequest, mask=identity) -> ExchangeRecord | None:  # type: ignore[no-untyped-def]
    return build_exchange(
        request=request, path_template="/api/docs", status=201, base_url=BASE, mask=mask
    )


def test_an_upload_is_recorded_without_body_without_boundary_and_without_values() -> None:
    result = record(upload())

    assert result is not None
    assert result.body is None
    assert result.content_type == "multipart/form-data"
    assert result.multipart is not None
    assert [(p.name, p.kind, p.size) for p in result.multipart.parts] == [
        ("descricao", "field", 14),
        ("arquivo", "file", 67),
    ]
    assert result.multipart.parts[1].filename == "foto.png"
    assert result.multipart.total_bytes == 81
    dumped = result.model_dump_json()
    assert "boundary" not in dumped
    assert "harness-" not in dumped
    assert "texto qualquer" not in dumped


def test_nothing_of_the_file_reaches_the_serialised_log() -> None:
    results = [record(upload(kind="png")), record(upload(kind="text", name="a.txt"))]
    log = ExchangeLog(run_id="r", product="p", exchanges=tuple(r for r in results if r is not None))

    text = log.model_dump_json()

    assert "synthetic file" not in text
    assert PNG_SIGNATURE.decode("latin-1") not in text
    assert "IHDR" not in text


def test_a_secret_named_text_field_goes_to_omitted_fields_and_not_to_the_parts() -> None:
    result = record(upload(fields=[("password", "x"), ("descricao", "y")]))

    assert result is not None
    assert result.omitted_fields == ("password",)
    assert result.multipart is not None
    assert [p.name for p in result.multipart.parts] == ["descricao", "arquivo"]


def test_a_registered_secret_inside_the_body_discards_the_record() -> None:
    def mask(text: str) -> str:
        return text.replace("SEGREDO-1", "***")

    assert record(upload(fields=[("descricao", "SEGREDO-1")]), mask) is None


def test_a_registered_secret_in_the_target_discards_the_record() -> None:
    def mask(text: str) -> str:
        return text.replace("SEGREDO-1", "***")

    assert record(upload(url=f"{BASE}/api/docs?t=SEGREDO-1"), mask) is None


def test_a_malformed_multipart_body_discards_the_record() -> None:
    request = HttpRequest(
        method="POST",
        url=f"{BASE}/api/docs",
        headers=(("Content-Type", "multipart/form-data; boundary=zz"),),
        body=b"nao e multipart",
        operation_id="enviar",
        account="a1",
    )

    assert record(request) is None


def test_an_anonymous_upload_is_not_recorded() -> None:
    assert record(upload(account=None)) is None


def test_a_json_record_has_no_multipart_summary() -> None:
    request = HttpRequest(
        method="POST",
        url=f"{BASE}/api/x",
        headers=(("Content-Type", "application/json"),),
        body=b'{"a":1}',
        operation_id="criar",
        account="a1",
    )

    result = record(request)

    assert result is not None
    assert result.multipart is None


def test_an_old_exchanges_file_without_the_field_is_still_readable() -> None:
    old = {
        "schema_version": 1,
        "run_id": "r",
        "product": "p",
        "exchanges": [
            {
                "operation_id": "op",
                "method": "GET",
                "path": "/x",
                "target": "/x",
                "account": "a",
                "status": 200,
            }
        ],
    }

    log = ExchangeLog.model_validate_json(json.dumps(old))

    assert log.exchanges[0].multipart is None


def test_the_file_content_constants_are_not_what_the_summary_stores() -> None:
    assert file_content("text") not in record(upload()).model_dump_json().encode()  # type: ignore[union-attr]

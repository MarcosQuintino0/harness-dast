"""`probe` com envio de arquivo (ADR 0052): corpo `multipart` sintético, cerca e resumo gravado."""

from email import policy
from email.parser import BytesParser
from typing import Any

from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.api_model import (
    ApiSpec,
    MediaBody,
    Operation,
    RequestBody,
    SecurityRequirement,
)
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import HarnessError
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.probe_result import ProbeResult
from tests.fakes.probe_ports import InMemoryDocuments, reply
from tests.fakes.rig import ENV, STR, Rig, agenda_spec, default_handler
from tests.unit.api_helpers import rule, rules_from

BINARY = Schema(type="string", format="binary")


def upload_operation(
    path: str = "/api/documentos/enviar",
    schema: Schema | None = None,
    operation_id: str = "enviar",
    part_types: dict[str, str] | None = None,
) -> Operation:
    body = schema or Schema(
        type="object",
        properties={"arquivo": BINARY, "descricao": STR},
        required=("arquivo",),
    )
    return Operation(
        operation_id=operation_id,
        method="post",
        path=path,
        request_body=RequestBody(
            required=True,
            media=(
                MediaBody(
                    media_type="multipart/form-data",
                    body_schema=body,
                    part_content_types=part_types or {},
                ),
            ),
        ),
        security=(SecurityRequirement(schemes=("bearer",)),),
    )


def spec_with(*operations: Operation) -> ApiSpec:
    base = agenda_spec()
    return base.model_copy(update={"operations": (base.operations[0], *operations)})


class Received:
    """Guarda o multipart que o alvo falso conseguiu ler com o parser da biblioteca padrão."""

    def __init__(self, status: int = 201) -> None:
        self.status = status
        self.parts: list[dict[str, Any]] = []
        self.content_types: list[str] = []

    def __call__(self, request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
        if not request.url.split("?")[0].endswith("/documentos/enviar"):
            return default_handler(request, jar)
        headers = dict(request.headers)
        self.content_types.append(headers["Content-Type"])
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {headers['Content-Type']}\r\nMIME-Version: 1.0\r\n\r\n".encode()
            + (request.body or b"")
        )
        assert not message.defects
        for part in message.iter_parts():
            payload = part.get_payload(decode=True)
            self.parts.append(
                {
                    "name": part.get_param("name", header="content-disposition"),
                    "filename": part.get_filename(),
                    "type": part.get_content_type(),
                    "size": len(payload),
                }
            )
        return reply(self.status, {"ok": True})


def run(rig: Rig, **changes: Any) -> ProbeResult:
    return rig.probe().execute(ProbeRequest(product="agenda", **changes))


def outcome(result: ProbeResult, operation_id: str = "enviar") -> str:
    return next(i.outcome for i in result.operations if i.operation_id == operation_id)


def test_the_target_receives_a_real_multipart_and_the_operation_is_a_success() -> None:
    target = Received()
    rig = Rig(spec=spec_with(upload_operation()), handler=target, env=ENV)

    result = run(rig, only=("enviar",))

    assert outcome(result) == "success"
    assert target.content_types[0].startswith("multipart/form-data; boundary=")
    assert [p["name"] for p in target.parts] == ["descricao", "arquivo"]
    file_part = target.parts[1]
    assert (file_part["filename"], file_part["type"], file_part["size"]) == (
        "synthetic.txt",
        "text/plain",
        15,
    )


def test_exchanges_keep_only_the_part_summary_and_no_file_content_anywhere() -> None:
    rig = Rig(spec=spec_with(upload_operation()), handler=Received(), env=ENV)

    result = run(rig, only=("enviar",))

    record = next(iter(rig.store.exchanges.values())).exchanges[0]
    assert record.body is None
    assert record.content_type == "multipart/form-data"
    assert record.multipart is not None
    assert [(p.name, p.kind, p.size) for p in record.multipart.parts][1:] == [
        ("arquivo", "file", 15)
    ]
    stored = rig.store.serialized() + result.model_dump_json()
    assert "synthetic file" not in stored
    assert "boundary" not in stored
    assert "harness-" not in stored


def test_a_synthetic_file_rule_sends_the_png_with_its_name_and_type() -> None:
    target = Received()
    rules = rules_from(rule("arquivo", "synthetic_file", kind="png", name="foto.png"))
    rig = Rig(
        spec=spec_with(upload_operation()),
        handler=target,
        documents=InMemoryDocuments(rules, None),
        env=ENV,
    )

    result = run(rig, only=("enviar",))

    assert outcome(result) == "success"
    assert (target.parts[1]["filename"], target.parts[1]["type"], target.parts[1]["size"]) == (
        "foto.png",
        "image/png",
        67,
    )
    stored = rig.store.serialized()
    assert "IHDR" not in stored
    assert "\\x89PNG" not in stored


def test_the_declared_encoding_content_type_is_used_without_a_rule() -> None:
    target = Received()
    operation = upload_operation(part_types={"arquivo": "text/csv"})
    rig = Rig(spec=spec_with(operation), handler=target, env=ENV)

    run(rig, only=("enviar",))

    assert target.parts[1]["type"] == "text/csv"


def test_a_rejected_type_is_a_validation_error_not_a_build_error() -> None:
    rig = Rig(spec=spec_with(upload_operation()), handler=Received(status=415), env=ENV)

    result = run(rig, only=("enviar",))

    assert outcome(result) in {"validation_error", "client_error"}
    assert not rig.store.exchanges or not next(iter(rig.store.exchanges.values())).exchanges


def test_a_bad_request_is_a_validation_error() -> None:
    rig = Rig(spec=spec_with(upload_operation()), handler=Received(status=400), env=ENV)

    assert outcome(run(rig, only=("enviar",))) == "validation_error"


def test_an_unsupported_multipart_schema_is_a_build_error_with_a_hint() -> None:
    nested = Schema(type="object", properties={"meta": Schema(type="object")}, required=("meta",))
    rig = Rig(spec=spec_with(upload_operation(schema=nested)), handler=Received(), env=ENV)

    result = run(rig, only=("enviar",))

    item = next(i for i in result.operations if i.operation_id == "enviar")
    assert item.outcome == "build_error"
    assert "multipart_unsupported_schema" in (item.message or "")
    assert item.hint


def test_dry_run_shows_the_part_list_and_no_bytes_nor_boundary() -> None:
    target = Received()
    rig = Rig(spec=spec_with(upload_operation()), handler=target, env=ENV)

    result = run(rig, only=("enviar",), dry_run=True)

    item = next(i for i in result.operations if i.operation_id == "enviar")
    assert item.outcome == "dry_run"
    assert item.preview is not None
    assert [(p.name, p.kind, p.size) for p in item.preview.multipart_parts] == [
        ("descricao", "field", item.preview.multipart_parts[0].size),
        ("arquivo", "file", 15),
    ]
    dumped = result.model_dump_json()
    assert "boundary" not in dumped
    assert "synthetic file" not in dumped
    assert target.parts == []


def test_a_denied_path_is_never_sent_even_as_multipart() -> None:
    target = Received()
    operation = upload_operation(path="/api/admin/documentos/enviar", operation_id="envia_admin")
    rig = Rig(spec=spec_with(operation), handler=target, env=ENV)

    result = run(rig, only=("envia_admin",))

    assert outcome(result, "envia_admin") == "skipped_denied"
    assert all("admin" not in path for path in rig.target.paths())


def test_a_path_outside_the_allowed_scope_is_never_sent_as_multipart() -> None:
    operation = upload_operation(path="/outra/documentos/enviar", operation_id="envia_fora")
    rig = Rig(spec=spec_with(operation), handler=Received(), env=ENV)

    result = run(rig, only=("envia_fora",))

    assert outcome(result, "envia_fora") == "skipped_scope"
    assert all("outra" not in path for path in rig.target.paths())


def test_the_upload_goes_through_the_zap_route_like_any_operation() -> None:
    rig = Rig(spec=spec_with(upload_operation()), handler=Received(), env=ENV)

    run(rig, only=("enviar",))

    sent = [r for r in rig.target.requests if r.operation_id == "enviar"]
    assert [r.route for r in sent] == ["zap"]

"""Prévia do que o `--dry-run` enviaria: nomes de campos e geradores, nunca valores."""

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.multipart_encoding import (
    MULTIPART_MEDIA_TYPE,
    MultipartPart,
    encode_multipart,
    summarize_multipart,
)
from harness_dast.domain.probe_result import FieldPlan, RequestPreview
from harness_dast.domain.request_builder import BuiltRequest, ValueRequest, ValueSource
from harness_dast.domain.request_encoding import multipart_fields

MAX_PREVIEW_FIELDS = 60


class RecordingSource:
    """Decora uma `ValueSource` e lembra qual gerador produziu cada campo da última montagem."""

    def __init__(self, inner: ValueSource) -> None:
        """Cria o registrador.

        Args:
            inner: Fonte de valores real.
        """
        self._inner = inner
        self._generators: dict[str, str] = {}

    def __call__(self, request: ValueRequest) -> JsonValue:
        """Delega à fonte real e registra `campo -> gerador` (o valor não é guardado)."""
        self._generators[request.field_path] = request.generator
        return self._inner(request)

    def take(self) -> dict[str, str]:
        """Devolve o que foi registrado desde a última chamada e zera o registro."""
        taken = self._generators
        self._generators = {}
        return taken


def _body_leaves(value: JsonValue, prefix: str) -> list[str]:
    if isinstance(value, dict):
        return [
            leaf for key, item in value.items() for leaf in _body_leaves(item, f"{prefix}.{key}")
        ]
    if isinstance(value, list):
        return [
            leaf for i, item in enumerate(value) for leaf in _body_leaves(item, f"{prefix}[{i}]")
        ]
    return [prefix]


def _multipart_parts(built: BuiltRequest) -> tuple[MultipartPart, ...]:
    """Partes que o multipart levaria (nome, tipo, tamanho); nunca os bytes nem a fronteira."""
    media = (built.body_media_type or "").split(";")[0].strip().lower()
    if media != MULTIPART_MEDIA_TYPE:
        return ()
    content_type, payload = encode_multipart(multipart_fields(built.body), built.files)
    summary = summarize_multipart(content_type, payload)
    return summary.parts if summary is not None else ()


def build_preview(
    operation: Operation,
    built: BuiltRequest,
    generators: dict[str, str],
    *,
    uses_flow_values: bool,
) -> RequestPreview:
    """Resume a requisição montada sem expor nenhum valor.

    Args:
        operation: Operação de origem.
        built: Requisição montada.
        generators: Mapa `campo -> gerador` registrado durante a montagem.
        uses_flow_values: Se algum valor viria de um produtor de `flows.yml`.
    """
    names = [f"path.{p.name}" for p in operation.parameters if p.location == "path"]
    names += [f"query.{name}" for name in dict.fromkeys(n for n, _ in built.query)]
    names += [f"header.{name}" for name in built.headers]
    names += [f"cookie.{name}" for name in built.cookies]
    if built.body is not None:
        names += _body_leaves(built.body, "body")
    names += [f"body.{spec.field}" for spec in built.files]
    return RequestPreview(
        query_names=tuple(dict.fromkeys(n for n, _ in built.query)),
        header_names=tuple(built.headers),
        fields=tuple(
            FieldPlan(name=name, generator=generators.get(name))
            for name in names[:MAX_PREVIEW_FIELDS]
        ),
        uses_flow_values=uses_flow_values,
        multipart_parts=_multipart_parts(built),
    )

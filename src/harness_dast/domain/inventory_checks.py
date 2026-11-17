"""Inventário dentro da cerca (V1.12, F8, ADR 0102). Módulo puro.

Só com `extra_checks.inventory: true` (que só a carta liga). Dois conjuntos de pedidos `GET`,
sempre pela cerca e nunca fora dela:

- **versões irmãs não documentadas**: o contrato tem `/v3/x`; existe `/v2/x`? Para cada caminho
  com um segmento de versão (`v3`), troca-se o número por outros (`v2`, `v4`, `v1`) e, antes,
  manda-se um controle (`v999`) para saber como o alvo responde a um caminho que não existe (SPA
  com resposta curinga, `401` geral de gateway). Só conta a irmã cuja resposta difere da do
  controle e não é `404`;
- **documentação exposta**: uma lista pequena e fixa de caminhos (`/openapi.json`, `/swagger.json`,
  `/docs`, `/redoc`...). Só conta `200` com marca de documentação no corpo.

O que a cerca nega não é enviado nem forçado: vira `not_verifiable_by_fence`. Teto rígido de
`INVENTORY_MAX_REQUESTS` pedidos por execução. Severidade baixa ou informativa.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal
from urllib.parse import urlsplit

from harness_dast.domain.api_model import Operation
from harness_dast.domain.extra_check_result import (
    INVENTORY_DOCS_PLUGIN,
    INVENTORY_SIBLING_PLUGIN,
    ExtraSkip,
    Risk,
    build_alert,
)
from harness_dast.domain.finding import normalize_path_template
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.request_encoding import join_url

INVENTORY_MAX_REQUESTS: Final = 40
"""Teto rígido de pedidos do inventário por execução."""

SIBLING_MAX_FAMILIES: Final = 6
SIBLINGS_PER_FAMILY: Final = 3
CONTROL_VERSION: Final = 999

DOC_PATHS: Final = (
    "/openapi.json",
    "/openapi.yaml",
    "/swagger.json",
    "/swagger.yaml",
    "/swagger",
    "/swagger-ui",
    "/swagger-ui.html",
    "/swagger/index.html",
    "/docs",
    "/redoc",
    "/api-docs",
    "/v2/api-docs",
    "/v3/api-docs",
    "/api/openapi.json",
    "/api/swagger.json",
    "/api/docs",
)
"""Lista fixa de caminhos de documentação (relativos à `base_url`)."""

_VERSION: Final = re.compile(r"^v(\d+)$", re.IGNORECASE)
_PARAM: Final = re.compile(r"\{[^{}]*\}")
_ABSENT: Final = frozenset({404, 410})
_DOC_WINDOW: Final = 65536
_SPEC_MARKERS: Final = ('"openapi"', '"swagger"', "openapi:", "swagger:")
_UI_MARKERS: Final = ("swagger-ui", "swaggerui", "redoc", "rapidoc")

SIBLING_TITLE: Final = "Versão irmã da API não documentada no contrato"
DOCS_TITLE: Final = "Documentação da API exposta"


@dataclass(frozen=True)
class SiblingFamily:
    """Uma operação versionada, o controle e as irmãs candidatas.

    Attributes:
        operation_id: Operação de origem.
        control: Alvo do controle (versão `v999`), que não deve existir.
        siblings: Alvos das irmãs (outras versões), na ordem de envio.
    """

    operation_id: str
    control: str
    siblings: tuple[str, ...]


@dataclass(frozen=True)
class InventoryPlan:
    """O que será enviado e o que ficou de fora."""

    families: tuple[SiblingFamily, ...]
    docs: tuple[str, ...]
    skipped: tuple[ExtraSkip, ...]


@dataclass(frozen=True)
class DocReading:
    """Resultado da leitura de uma resposta de documentação."""

    kind: Literal["spec", "ui"]


def _version_index(segments: Sequence[str]) -> int | None:
    for index, segment in enumerate(segments):
        if _VERSION.match(segment):
            return index
    return None


def _version_number(segment: str) -> int:
    matched = _VERSION.match(segment)
    return int(matched.group(1)) if matched else 0


def _swap(segments: Sequence[str], index: int, number: int) -> str:
    swapped = [*segments[:index], f"v{number}", *segments[index + 1 :]]
    return "/" + "/".join(swapped)


def _concrete_path(operation: Operation, exchanges: Sequence[ExchangeRecord]) -> str | None:
    """Caminho sem parâmetros, ou o concreto de um pedido do `probe` da mesma operação."""
    if not _PARAM.search(operation.path):
        return "/" + operation.path.strip("/")
    for exchange in exchanges:
        if exchange.operation_id == operation.operation_id:
            return urlsplit(exchange.target).path
    return None


def candidate_numbers(current: int) -> tuple[int, ...]:
    """Versões a tentar: a anterior, a seguinte e a anterior à anterior (no máximo três)."""
    options = [current - 1, current + 1, current - 2]
    return tuple(item for item in options if item >= 1)[:SIBLINGS_PER_FAMILY]


def _family_for(
    operation: Operation,
    exchanges: Sequence[ExchangeRecord],
    documented: set[str],
    permits: Callable[[str, str], bool],
    skipped: list[ExtraSkip],
) -> SiblingFamily | None:
    """A família de irmãs de uma operação versionada, ou `None` (o motivo vai em `skipped`)."""
    modelled = normalize_path_template(operation.path).strip("/").split("/")
    index = _version_index(modelled)
    if index is None:
        return None
    concrete = _concrete_path(operation, exchanges)
    if concrete is None:
        skipped.append(ExtraSkip(subject=operation.operation_id, reason="needs_example"))
        return None
    segments = concrete.strip("/").split("/")
    siblings: list[str] = []
    for other in candidate_numbers(_version_number(segments[index])):
        if normalize_path_template(_swap(modelled, index, other)) in documented:
            continue
        target = _swap(segments, index, other)
        if permits("GET", target):
            siblings.append(target)
        else:
            skipped.append(ExtraSkip(subject=target, reason="not_verifiable_by_fence"))
    control = _swap(segments, index, CONTROL_VERSION)
    if siblings and not permits("GET", control):
        skipped.append(ExtraSkip(subject=control, reason="not_verifiable_by_fence"))
        return None
    return SiblingFamily(operation.operation_id, control, tuple(siblings)) if siblings else None


def plan_inventory(
    operations: Mapping[str, Operation],
    exchanges: Sequence[ExchangeRecord],
    *,
    permits: Callable[[str, str], bool],
    only: frozenset[str] = frozenset(),
    max_requests: int = INVENTORY_MAX_REQUESTS,
) -> InventoryPlan:
    """Planeja o inventário respeitando a cerca e o teto.

    Args:
        operations: Operações do OpenAPI por identificador.
        exchanges: Pedidos do `probe` (dão o caminho concreto de modelos com parâmetro).
        permits: `(método, alvo relativo) -> bool`, a decisão do `ScopeGuard` aprovado.
        only: Operações do `--only`; vazio = todas. (A documentação não depende delas.)
        max_requests: Teto pedido; vale no máximo `INVENTORY_MAX_REQUESTS`.
    """
    budget = max(0, min(max_requests, INVENTORY_MAX_REQUESTS))
    documented = {normalize_path_template(op.path) for op in operations.values()}
    skipped: list[ExtraSkip] = []
    kept: list[SiblingFamily] = []
    used = 0
    seen: set[str] = set()
    for operation in operations.values():
        template = normalize_path_template(operation.path)
        if (only and operation.operation_id not in only) or template in seen:
            continue
        seen.add(template)
        family = _family_for(operation, exchanges, documented, permits, skipped)
        if family is None:
            continue
        cost = 1 + len(family.siblings)
        if len(kept) >= SIBLING_MAX_FAMILIES or used + cost > budget:
            skipped.append(ExtraSkip(subject=family.operation_id, reason="budget_exceeded"))
            continue
        kept.append(family)
        used += cost
    docs: list[str] = []
    for path in DOC_PATHS:
        if normalize_path_template(path) in documented:
            continue
        if not permits("GET", path):
            skipped.append(ExtraSkip(subject=path, reason="not_verifiable_by_fence"))
        elif used + len(docs) >= budget:
            skipped.append(ExtraSkip(subject=path, reason="budget_exceeded"))
        else:
            docs.append(path)
    return InventoryPlan(families=tuple(kept), docs=tuple(docs), skipped=tuple(skipped))


def judge_sibling(
    status: int | None, control: int | None
) -> Literal["exists", "absent", "unclear"]:
    """Se a irmã existe: resposta diferente da do controle e que não seja `404` ou `410`.

    `unclear` quando falta resposta, quando é `5xx` (o servidor quebrou: não prova que a versão
    existe) ou quando a irmã responde igual ao controle (o alvo responde a qualquer caminho do
    mesmo jeito: não dá para saber).
    """
    if status is None:
        return "unclear"
    if status in _ABSENT:
        return "absent"
    if status >= 500:
        return "unclear"
    if control is not None and status == control:
        return "unclear"
    return "exists"


def doc_text(body: bytes) -> str:
    """Início do corpo como texto, só para procurar marcas de documentação (nunca é gravado)."""
    return body[:_DOC_WINDOW].decode("utf-8", errors="ignore")


def read_docs(status: int | None, text: str) -> DocReading | None:
    """Se a resposta é documentação: `200` com marca de especificação ou de interface."""
    if status != 200:
        return None
    window = text[:_DOC_WINDOW].lower()
    if any(marker in window for marker in _SPEC_MARKERS):
        return DocReading("spec")
    if any(marker in window for marker in _UI_MARKERS):
        return DocReading("ui")
    return None


def sibling_alert(
    index: int, operation_id: str, target: str, status: int, *, base_url: str
) -> dict[str, str]:
    """Alerta da versão irmã: baixo se respondeu 2xx, informativo nos demais códigos."""
    risk: Risk = "Low" if 200 <= status < 300 else "Informational"
    evidence = (
        f"GET {target} respondeu HTTP {status}, e um caminho de controle com versão inexistente "
        f"respondeu de outro jeito; o contrato (operação '{operation_id}') não documenta esta "
        "versão."
    )
    return build_alert(
        ident=f"inventory-sibling-{index}",
        plugin_id=INVENTORY_SIBLING_PLUGIN,
        title=SIBLING_TITLE,
        cwe=1059,
        risk=risk,
        confidence="Medium",
        method="GET",
        url=join_url(base_url, target),
        param="",
        evidence=evidence,
        description=(
            "Uma versão anterior ou posterior da API responde no servidor e não consta do "
            "contrato. Versões antigas costumam ficar sem as correções e os controles das atuais. "
            + evidence
        ),
        solution=(
            "Desligue a versão que não deve existir ou documente-a e aplique a ela os mesmos "
            "controles de autenticação, autorização e limite das versões atuais."
        ),
    )


def docs_alert(index: int, target: str, reading: DocReading, *, base_url: str) -> dict[str, str]:
    """Alerta da documentação: baixo se é a especificação, informativo se é só a interface."""
    risk: Risk = "Low" if reading.kind == "spec" else "Informational"
    what = "a especificação da API" if reading.kind == "spec" else "a interface de documentação"
    evidence = f"GET {target} respondeu HTTP 200 com {what}."
    return build_alert(
        ident=f"inventory-docs-{index}",
        plugin_id=INVENTORY_DOCS_PLUGIN,
        title=DOCS_TITLE,
        cwe=200,
        risk=risk,
        confidence="High",
        method="GET",
        url=join_url(base_url, target),
        param="",
        evidence=evidence,
        description=(
            "A documentação da API está acessível a quem chama, o que facilita o mapeamento das "
            "operações. Em ambiente de teste isto pode ser intencional. " + evidence
        ),
        solution=(
            "Restrinja a documentação a quem precisa dela (autenticação ou rede interna) "
            "fora dos ambientes de desenvolvimento."
        ),
    )

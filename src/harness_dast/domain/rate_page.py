"""Tamanho de página sem limite (V1.12, F5a, ADR 0101). Módulo puro.

Só com `extra_checks.allow_rate_tests: true` (que só a carta liga). A regra é genérica, derivada do
contrato: uma operação `GET` que o `probe` provou e que tem um parâmetro de consulta inteiro com
nome de tamanho de página (`limit`, `page_size`, `per_page`, `size`, `count`...). A CLI manda dois
pedidos: o do `probe` (tamanho normal) e o mesmo com um valor enorme. Se o alvo aceita e devolve
mais itens, ele honra um tamanho que ninguém deveria poder pedir: achado de severidade média.

Teto rígido: `PAGE_MAX_OPERATIONS` operações por execução (dois pedidos cada); só `GET`.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Final, Literal
from urllib.parse import parse_qsl, quote, urlsplit

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import JsonValue, effective_type
from harness_dast.domain.authz.sensitive import field_words
from harness_dast.domain.extra_check_result import (
    RATE_PAGE_PLUGIN,
    ExtraSkip,
    build_alert,
)
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.request_encoding import join_url

PAGE_MAX_OPERATIONS: Final = 3
"""Teto de operações testadas por execução (dois pedidos cada)."""

PAGE_NORMAL_SIZE: Final = 10
"""Tamanho do pedido de comparação (o do `probe` pode ser aleatório e grande)."""

PAGE_PROBE_SIZE: Final = 10_000
"""Tamanho pedido quando o contrato não declara `maximum`."""

PAGE_MAX_PROBE_SIZE: Final = 100_000
"""Maior tamanho que a CLI aceita pedir (com `maximum` declarado, vale `maximum + 1000`)."""

PAGE_CWE: Final = 770
PAGE_TITLE: Final = "Tamanho de página sem limite aceito (consumo irrestrito de recursos)"

PAGE_NAMES: Final = frozenset(
    {
        "limit",
        "pagesize",
        "perpage",
        "size",
        "count",
        "take",
        "rows",
        "top",
        "maxresults",
        "pagelimit",
        "itemsperpage",
        "pagelen",
        "numresults",
    }
)
"""Nomes (em minúsculas, sem separadores) que identificam o tamanho da página."""

_MAX_LIST_DEPTH: Final = 3
_SIZE_RATIO: Final = 2


@dataclass(frozen=True)
class PageCase:
    """Uma operação com parâmetro de tamanho de página e os dois pedidos.

    Attributes:
        exchange: O pedido que o `probe` provou (dá a conta, o método e os demais parâmetros).
        param: Nome do parâmetro de tamanho.
        base_target: Alvo com o tamanho normal (o pedido de comparação).
        huge_value: Tamanho enorme pedido.
        huge_target: Alvo (caminho e consulta) com o tamanho enorme.
        maximum: `maximum` declarado no contrato, ou `None`.
    """

    exchange: ExchangeRecord = dc_field(repr=False)
    param: str
    base_target: str
    huge_value: int
    huge_target: str
    maximum: int | None

    @property
    def operation_id(self) -> str:
        """Operação do pedido."""
        return self.exchange.operation_id


@dataclass(frozen=True)
class PagePlan:
    """O que será enviado e o que ficou de fora."""

    cases: tuple[PageCase, ...]
    skipped: tuple[ExtraSkip, ...]


@dataclass(frozen=True)
class PageReply:
    """Uma resposta reduzida ao que a decisão usa (o corpo nunca é guardado)."""

    status: int | None
    items: int | None
    size: int
    truncated: bool


@dataclass(frozen=True)
class PageVerdict:
    """Conclusão da comparação.

    Attributes:
        outcome: `accepted` (achado), `limited` ou `inconclusive`.
        detail: Resumo legível, sem valores nem corpo.
    """

    outcome: Literal["accepted", "limited", "inconclusive"]
    detail: str


def is_page_param(name: str) -> bool:
    """Se o NOME parece o tamanho da página (`page_size`, `perPage`, `limit`...)."""
    return "".join(field_words(name)) in PAGE_NAMES


def probe_size(maximum: float | None) -> int | None:
    """Tamanho enorme a pedir, ou `None` se o contrato já permite tamanhos grandes demais."""
    if maximum is None:
        return PAGE_PROBE_SIZE
    value = int(maximum) + 1000
    return value if value <= PAGE_MAX_PROBE_SIZE else None


def normal_size(minimum: float | None, maximum: float | None) -> int:
    """Tamanho de página normal para a comparação: 10, ou o que o contrato permite."""
    value = PAGE_NORMAL_SIZE
    if maximum is not None:
        value = min(value, int(maximum))
    if minimum is not None:
        value = max(value, int(minimum))
    return max(value, 1)


def _page_parameter(
    operation: Operation, target: str
) -> tuple[str, float | None, float | None] | None:
    counts: dict[str, int] = {}
    for name, _ in parse_qsl(urlsplit(target).query, keep_blank_values=True):
        counts[name] = counts.get(name, 0) + 1
    for parameter in operation.parameters:
        schema = parameter.value_schema
        if (
            parameter.location == "query"
            and counts.get(parameter.name, 0) <= 1
            and effective_type(schema) == "integer"
            and is_page_param(parameter.name)
        ):
            return parameter.name, schema.minimum, schema.maximum
    return None


def render_huge_target(target: str, param: str, value: int) -> str:
    """O alvo do `probe` com o parâmetro de tamanho trocado (ou acrescentado) por `value`."""
    parts = urlsplit(target)
    pairs = [
        (name, str(value) if name == param else text)
        for name, text in parse_qsl(parts.query, keep_blank_values=True)
    ]
    if not any(name == param for name, _ in pairs):
        pairs.append((param, str(value)))
    query = "&".join(f"{quote(name, safe='')}={quote(text, safe='')}" for name, text in pairs)
    return f"{parts.path}?{query}"


def plan_page_checks(
    exchanges: Sequence[ExchangeRecord],
    operations: Mapping[str, Operation],
    *,
    permits: Callable[[str, str], bool],
    infrastructure: frozenset[str] = frozenset(),
    only: frozenset[str] = frozenset(),
    max_operations: int = PAGE_MAX_OPERATIONS,
) -> PagePlan:
    """Planeja os testes: `GET` provados pelo `probe` com parâmetro de tamanho de página.

    Args:
        exchanges: Pedidos do `probe`.
        operations: Operações do OpenAPI por identificador.
        permits: `(método, alvo relativo) -> bool`, a decisão do `ScopeGuard` aprovado.
        infrastructure: Caminhos de login, saúde e preparação (ficam fora).
        only: Operações escolhidas por `--only`; vazio = todas.
        max_operations: Teto pedido; vale no máximo `PAGE_MAX_OPERATIONS`.
    """
    budget = max(0, min(max_operations, PAGE_MAX_OPERATIONS))
    cases: list[PageCase] = []
    skipped: list[ExtraSkip] = []
    seen: set[str] = set()
    for exchange in exchanges:
        operation = operations.get(exchange.operation_id)
        if (
            operation is None
            or exchange.method.upper() != "GET"
            or exchange.operation_id in seen
            or exchange.path in infrastructure
            or (only and exchange.operation_id not in only)
        ):
            continue
        found = _page_parameter(operation, exchange.target)
        if found is None:
            continue
        param, low, high = found
        maximum = None if high is None else int(high)
        value = probe_size(maximum)
        if value is None:
            skipped.append(ExtraSkip(subject=exchange.operation_id, reason="contract_allows_huge"))
            continue
        seen.add(exchange.operation_id)
        huge = render_huge_target(exchange.target, param, value)
        base = render_huge_target(exchange.target, param, normal_size(low, high))
        if not permits("GET", huge):
            skipped.append(ExtraSkip(subject=exchange.operation_id, reason="not_allowed_by_scope"))
        elif len(cases) >= budget:
            skipped.append(ExtraSkip(subject=exchange.operation_id, reason="budget_exceeded"))
        else:
            cases.append(PageCase(exchange, param, base, value, huge, maximum))
    return PagePlan(cases=tuple(cases), skipped=tuple(skipped))


def _largest_list(value: JsonValue, depth: int) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict) and depth < _MAX_LIST_DEPTH:
        sizes = [_largest_list(item, depth + 1) for item in value.values()]
        known = [size for size in sizes if size is not None]
        return max(known) if known else None
    return None


def count_items(body: bytes) -> int | None:
    """Quantos itens a resposta JSON lista: a lista do topo ou a maior lista até 3 níveis abaixo.

    `None` se o corpo não é JSON ou não traz lista (o contrato de resposta varia: `items`,
    `results`, `data`...; a regra não presume nome).
    """
    try:
        parsed: JsonValue = json.loads(body)
    except ValueError:
        return None
    return _largest_list(parsed, 0)


def read_reply(status: int | None, body: bytes, *, truncated: bool) -> PageReply:
    """Reduz a resposta ao que a decisão usa."""
    return PageReply(
        status=status,
        items=None if truncated else count_items(body),
        size=len(body),
        truncated=truncated,
    )


def _is_ok(status: int | None) -> bool:
    return status is not None and 200 <= status < 300


def judge_page(base: PageReply, huge: PageReply, maximum: int | None) -> PageVerdict:
    """Compara o pedido normal com o enorme.

    Com `maximum` declarado, vale mais itens do que o contrato permite. Sem ele, vale mais itens
    do que o pedido normal. Sem contagem (corpo cortado ou sem lista), vale o corpo pelo menos
    duas vezes maior (ou cortado só no pedido enorme).
    """
    if not _is_ok(base.status):
        return PageVerdict("inconclusive", f"o pedido normal não deu sucesso (HTTP {base.status})")
    if not _is_ok(huge.status):
        return PageVerdict("limited", f"o alvo recusou o tamanho enorme (HTTP {huge.status})")
    if base.items == 0 and huge.items == 0:
        return PageVerdict(
            "inconclusive", "a lista veio vazia nos dois pedidos: sem dados para comparar"
        )
    if base.items is not None and huge.items is not None:
        limit = maximum if maximum is not None else base.items
        if huge.items > limit:
            where = "o máximo do contrato" if maximum is not None else "o pedido normal"
            return PageVerdict(
                "accepted",
                f"o pedido enorme devolveu {huge.items} itens contra {base.items} do normal, "
                f"acima do limite de {limit} ({where})",
            )
        return PageVerdict(
            "limited", f"o pedido enorme devolveu {huge.items} itens, sem passar de {limit}"
        )
    if (
        base.size > 0
        and (huge.truncated or huge.size > _SIZE_RATIO * base.size)
        and (huge.size > base.size)
    ):
        return PageVerdict(
            "accepted",
            f"sem contagem de itens, o corpo do pedido enorme tem {huge.size} bytes"
            f"{' (cortado pelo teto da CLI)' if huge.truncated else ''} "
            f"contra {base.size} do normal",
        )
    return PageVerdict("inconclusive", "não foi possível comparar a quantidade de itens")


def page_alert(index: int, case: PageCase, detail: str, *, base_url: str) -> dict[str, str]:
    """Alerta do achado: severidade média; confiança média com `maximum` declarado e baixa sem ele.

    Sem `maximum` o limite é só "mais do que o pedido normal": heurística, dita no texto.
    """
    path = urlsplit(join_url(base_url, case.exchange.target)).path
    declared = (
        f"declara maximum {case.maximum}" if case.maximum is not None else "não declara maximum"
    )
    heuristic = case.maximum is None
    evidence = (
        f"Com '{case.param}={case.huge_value}' (o contrato {declared}): {detail}. "
        "Sem erro nem limite."
        + (
            " Heurística: sem `maximum` no contrato, o limite comparado é o pedido normal."
            if heuristic
            else ""
        )
    )
    return build_alert(
        ident=f"rate-page-{index}",
        plugin_id=RATE_PAGE_PLUGIN,
        title=PAGE_TITLE,
        cwe=PAGE_CWE,
        risk="Medium",
        confidence="Low" if heuristic else "Medium",
        method="GET",
        url=join_url(base_url, path),
        param=case.param,
        evidence=evidence,
        description=(
            f"A operação aceita o parâmetro '{case.param}' com um valor muito acima do normal e "
            "devolve a página inteira: quem chama escolhe quanto o servidor processa e transfere. "
            + evidence
        ),
        solution=(
            "Imponha um tamanho máximo de página no servidor (recuse ou reduza o excedente), "
            "declare o `maximum` no contrato e pagine por cursor."
        ),
    )

"""Decisões puras do teste de autorização.

Cobre equivalência de respostas, campos fora do esquema e efeito de um campo injetado.

Nada aqui envia requisição nem grava arquivo. As funções devolvem NOMES e CAMINHOS de campo,
nunca valores: quem chama pode gravar o resultado sem risco de vazar dado do alvo. Este módulo
é puro.
"""

import json
from collections.abc import Iterator
from typing import Final, Literal

from harness_dast.domain.api_schema import JsonValue, Schema, effective_type
from harness_dast.domain.authz.config import normalize_field_name

Verdict = Literal["allowed_equivalent", "allowed_different", "denied", "baseline_failed", "error"]
"""Resultado de repetir um pedido com outra conta (veja `judge_replay`)."""

MAX_DEPTH: Final = 12
MAX_PARSE_DEPTH: Final = 200
"""Aninhamento máximo de um corpo JSON aceito; acima disso o corpo é tratado como não JSON."""
MAX_PATHS: Final = 20
_OK_RANGE: Final = range(200, 300)


def is_success_status(status: int | None) -> bool:
    """Diz se o código é 2xx."""
    return status is not None and status in _OK_RANGE


def parse_json(body: bytes) -> JsonValue | None:
    """Corpo como JSON, ou `None` se vazio, inválido ou profundo demais."""
    if not body.strip():
        return None
    try:
        text = body.decode("utf-8")
        if _nesting_exceeds(text, MAX_PARSE_DEPTH):
            return None
        parsed: JsonValue = json.loads(text)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    return parsed


def _nesting_exceeds(text: str, limit: int) -> bool:
    """Diz se o aninhamento de listas e objetos passa de `limit`, sem interpretar o JSON.

    O limite de recursão do interpretador muda entre versões e sistemas; contar aqui deixa a
    recusa de corpo profundo igual em toda máquina.
    """
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > limit:
                return True
        elif char in "]}":
            depth -= 1
    return False


def strip_volatile(value: JsonValue, volatile: frozenset[str], depth: int = 0) -> JsonValue:
    """Remove, em qualquer nível, os campos cujo nome normalizado está em `volatile`."""
    if depth > MAX_DEPTH:
        return value
    if isinstance(value, dict):
        return {
            name: strip_volatile(item, volatile, depth + 1)
            for name, item in value.items()
            if normalize_field_name(name) not in volatile
        }
    if isinstance(value, list):
        return [strip_volatile(item, volatile, depth + 1) for item in value]
    return value


def bodies_equivalent(first: bytes, second: bytes, volatile: frozenset[str]) -> bool:
    """Diz se duas respostas têm o mesmo conteúdo, ignorando os campos voláteis.

    JSON é comparado como estrutura (a ordem das chaves não conta); o que não é JSON é
    comparado byte a byte. Dois corpos vazios são equivalentes.
    """
    left, right = parse_json(first), parse_json(second)
    if left is None and right is None:
        return first.strip() == second.strip()
    if left is None or right is None:
        return False
    return strip_volatile(left, volatile) == strip_volatile(right, volatile)


def judge_replay(baseline: int | None, replay: int | None, *, equivalent: bool) -> Verdict:
    """Resultado de repetir um pedido com outra conta.

    - Linha de base que não foi 2xx: `baseline_failed` (nada a comparar).
    - Repetição sem resposta ou 5xx: `error` (inconclusivo, nunca "seguro").
    - Repetição 2xx: `allowed_equivalent` se o corpo é equivalente, senão `allowed_different`.
    - Qualquer outro código (401, 403, 404, 400...): `denied`, o resultado esperado.
    """
    if not is_success_status(baseline):
        return "baseline_failed"
    if replay is None or replay >= 500:
        return "error"
    if is_success_status(replay):
        return "allowed_equivalent" if equivalent else "allowed_different"
    return "denied"


def _member_schemas(schema: Schema) -> tuple[Schema, ...]:
    """O esquema e as alternativas de composição, achatadas em lista (sem repetir níveis)."""
    found: list[Schema] = []
    stack = [schema]
    while stack and len(found) < 200:
        node = stack.pop()
        found.append(node)
        stack.extend((*node.all_of, *node.one_of, *node.any_of))
    return tuple(found)


def _declared(schema: Schema) -> tuple[dict[str, list[Schema]], list[Schema], bool]:
    """Propriedades declaradas (união da composição), esquemas de item e se é objeto livre."""
    properties: dict[str, list[Schema]] = {}
    items: list[Schema] = []
    opaque = False
    for member in _member_schemas(schema):
        if member.truncated:
            opaque = True
        for name, sub in member.properties.items():
            properties.setdefault(name, []).append(sub)
        if member.items is not None:
            items.append(member.items)
    if not properties and not items:
        opaque = opaque or effective_type(schema) in {None, "object"}
    return properties, items, opaque


def _walk(value: JsonValue, schema: Schema, prefix: str, depth: int) -> Iterator[str]:
    if depth > MAX_DEPTH:
        return
    properties, items, opaque = _declared(schema)
    if isinstance(value, dict):
        if opaque and not properties:
            return
        for name, item in value.items():
            path = f"{prefix}.{name}" if prefix else name
            if name not in properties:
                yield path
                continue
            for sub in properties[name]:
                yield from _walk(item, sub, path, depth + 1)
    elif isinstance(value, list):
        for item in value[:50]:
            for sub in items:
                yield from _walk(item, sub, f"{prefix}[]", depth + 1)


def unexpected_fields(schema: Schema, body: JsonValue) -> tuple[str, ...]:
    """Caminhos de campo presentes na resposta e ausentes do esquema (sem os valores).

    Objeto sem `properties` no esquema é tratado como livre (nada é fora do esquema), porque
    `additionalProperties` não é modelado. Lista de itens usa o sufixo `[]` no caminho. No
    máximo `MAX_PATHS` caminhos únicos, na ordem em que aparecem.
    """
    found = dict.fromkeys(_walk(body, schema, "", 0))
    return tuple(found)[:MAX_PATHS]


def has_empty_list(schema: Schema, body: JsonValue) -> bool:
    """Diz se a resposta traz uma lista vazia onde o esquema declara itens.

    Lista vazia não deixa comparar os campos dos itens: quem chama não pode contar a operação
    como testada e segura.
    """
    return any(_empty_lists(body, schema, 0))


def _empty_lists(value: JsonValue, schema: Schema, depth: int) -> Iterator[bool]:
    if depth > MAX_DEPTH:
        return
    properties, items, _ = _declared(schema)
    if isinstance(value, dict):
        for name, item in value.items():
            for sub in properties.get(name, []):
                yield from _empty_lists(item, sub, depth + 1)
    elif isinstance(value, list):
        if not value and items:
            yield True
        for item in value[:50]:
            for sub in items:
                yield from _empty_lists(item, sub, depth + 1)


def _leaves(value: JsonValue, prefix: str, depth: int) -> Iterator[tuple[str, JsonValue]]:
    if depth > MAX_DEPTH:
        return
    if isinstance(value, dict):
        for name, item in value.items():
            path = f"{prefix}.{name}" if prefix else name
            if isinstance(item, dict | list):
                yield from _leaves(item, path, depth + 1)
            else:
                yield path, item
    elif isinstance(value, list):
        for item in value[:50]:
            yield from _leaves(item, f"{prefix}[]", depth + 1)


def holds_value(body: JsonValue | None, paths: tuple[str, ...], value: JsonValue) -> bool:
    """Diz se algum dos `paths` ainda tem exatamente `value` (mesmo tipo) no corpo."""
    if body is None:
        return False
    leaves = dict(_leaves(body, "", 0))
    return any(
        path in leaves and type(leaves[path]) is type(value) and leaves[path] == value
        for path in paths
    )


def injected_effect(
    before: JsonValue | None, after: JsonValue | None, field: str, injected: JsonValue
) -> tuple[tuple[str, ...], JsonValue]:
    """Caminhos em que o valor injetado passou a valer, e o valor anterior do primeiro deles.

    Com leitura anterior: um caminho conta quando, DEPOIS, vale o valor injetado e, ANTES,
    valia outra coisa (ou o caminho não existia). Cobre nome diferente (`role` entra, `papel`
    muda). Sem leitura anterior: só conta um caminho cujo último nome é o do campo injetado.
    O tipo importa (`1` não é `true`).

    Returns:
        (caminhos, valor_anterior). O valor anterior é `None` se não havia ou não se sabe.
    """
    if after is None:
        return (), None
    previous = dict(_leaves(before, "", 0)) if before is not None else {}
    hits: list[str] = []
    old: JsonValue = None
    wanted = normalize_field_name(field)
    for path, value in _leaves(after, "", 0):
        if type(value) is not type(injected) or value != injected:
            continue
        last = normalize_field_name(path.rsplit(".", 1)[-1])
        if before is None:
            changed = last == wanted
        else:
            prior = previous.get(path)
            changed = path not in previous or (
                type(prior) is not type(injected) or prior != injected
            )
        if changed:
            if not hits and path in previous:
                old = previous[path]
            hits.append(path)
    return tuple(dict.fromkeys(hits)), old

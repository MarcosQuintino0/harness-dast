"""Geradores básicos do catálogo: números, textos, identificadores, datas e constantes.

Cada gerador é uma função pura de (ambiente, pedido): o sorteio usa o `random.Random` do
ambiente (semente injetada) e as datas usam o relógio injetado. Valores `unique` derivam da
etiqueta da execução e do contador (ver `domain/unique_values.py`).
"""

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.implicit_values import numeric_bounds
from harness_dast.domain.request_builder import ValueRequest
from harness_dast.domain.unique_values import unique_digits, unique_token

_LOWER_ALNUM = "abcdefghijklmnopqrstuvwxyz0123456789"
_DEFAULT_ALNUM_LENGTH = 10
_DEFAULT_UNIQUE_LENGTH = 12
_MAX_ALNUM_LENGTH = 256


@dataclass(frozen=True)
class Environment:
    """Fontes injetadas: gerador de números aleatórios com semente e o relógio."""

    rng: random.Random
    now: datetime


def random_text(env: Environment, size: int) -> str:
    """Texto aleatório (minúsculas e dígitos) de `size` caracteres."""
    return "".join(env.rng.choice(_LOWER_ALNUM) for _ in range(size))


def random_digits(env: Environment, size: int) -> str:
    """Texto de `size` dígitos decimais aleatórios."""
    return "".join(env.rng.choice("0123456789") for _ in range(size))


def _int_arg(request: ValueRequest, name: str, default: int) -> int:
    value = request.args.get(name, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _text_arg(request: ValueRequest, name: str, default: str) -> str:
    value = request.args.get(name, default)
    return value if isinstance(value, str) else default


def gen_numeric(env: Environment, request: ValueRequest) -> JsonValue:
    """Texto de N dígitos; único: prefixo da etiqueta + contador."""
    digits = _int_arg(request, "digits", 1)
    if request.unique:
        return unique_digits(request.run_tag, request.counter, digits)
    return random_digits(env, digits)


def _integer_range(request: ValueRequest) -> tuple[int, int]:
    low, high = numeric_bounds(request.value_schema, request.field_path)
    low, high = _int_arg(request, "min", low), _int_arg(request, "max", high)
    if low > high:
        raise ConfigError(
            "Os limites do esquema e os args do gerador integer não admitem nenhum valor.",
            hint="Ajuste min/max da regra.",
        )
    return low, high


def gen_integer(env: Environment, request: ValueRequest) -> JsonValue:
    """Inteiro no intervalo; único: sequência a partir de um ponto derivado da etiqueta."""
    low, high = _integer_range(request)
    if not request.unique:
        return env.rng.randint(low, high)
    span = high - low + 1
    if request.counter >= span:
        raise ConfigError(
            f"O intervalo do gerador integer só comporta {span} valores únicos.",
            hint="Aumente o intervalo (min/max) da regra.",
        )
    return low + (int(request.run_tag, 16) + request.counter) % span


def gen_number(env: Environment, request: ValueRequest) -> JsonValue:
    """Número decimal no intervalo, arredondado em `decimals` casas."""
    low, high = _integer_range(request)
    return round(env.rng.uniform(low, high), _int_arg(request, "decimals", 2))


def gen_boolean(env: Environment, request: ValueRequest) -> JsonValue:
    """Verdadeiro ou falso."""
    return env.rng.random() < 0.5


def _alnum_length(request: ValueRequest) -> int:
    schema = request.value_schema
    explicit = request.args.get("length")
    if isinstance(explicit, int) and not isinstance(explicit, bool):
        return explicit
    wanted = _DEFAULT_UNIQUE_LENGTH if request.unique else _DEFAULT_ALNUM_LENGTH
    wanted = max(wanted, schema.min_length or 0)
    if schema.max_length is not None:
        wanted = min(wanted, schema.max_length)
    return min(max(wanted, 1), _MAX_ALNUM_LENGTH)


def gen_alphanumeric(env: Environment, request: ValueRequest) -> JsonValue:
    """Letras minúsculas e dígitos; único: etiqueta + contador logo após o prefixo."""
    length = _alnum_length(request)
    prefix = _text_arg(request, "prefix", "")
    room = max(length - len(prefix), 0)
    if request.unique:
        token = unique_token(request.run_tag, request.counter, room)
        return prefix + token + random_text(env, room - len(token))
    return (prefix + random_text(env, room))[:length]


def gen_uuid(env: Environment, request: ValueRequest) -> JsonValue:
    """UUID v4; único: os 12 primeiros dígitos hex são etiqueta (8) e contador (4)."""
    if not request.unique:
        return str(uuid.UUID(int=env.rng.getrandbits(128), version=4))
    head = request.run_tag.ljust(8, "0") + f"{request.counter:04x}"
    rest = f"{env.rng.getrandbits(80):020x}"
    return str(uuid.UUID(hex=head + rest, version=4))


def gen_email(env: Environment, request: ValueRequest) -> JsonValue:
    """E-mail `prefixo + (token | texto)@domínio`; o domínio padrão é reservado a testes."""
    domain = _text_arg(request, "domain", "example.test")
    prefix = _text_arg(request, "prefix", "hd")
    if request.unique:
        local = prefix + unique_token(request.run_tag, request.counter)
    else:
        local = prefix + random_text(env, _DEFAULT_ALNUM_LENGTH)
    return f"{local}@{domain}"


def gen_uri(env: Environment, request: ValueRequest) -> JsonValue:
    """URL `base/r/<token|texto>`; a base padrão é um domínio reservado a testes."""
    base = _text_arg(request, "base", "https://example.test").rstrip("/")
    if request.unique:
        return f"{base}/r/{unique_token(request.run_tag, request.counter)}"
    return f"{base}/r/{random_text(env, _DEFAULT_ALNUM_LENGTH)}"


def _offset_days(env: Environment, request: ValueRequest) -> int:
    low = _int_arg(request, "min_offset_days", -365)
    return env.rng.randint(low, _int_arg(request, "max_offset_days", 365))


def gen_date(env: Environment, request: ValueRequest) -> JsonValue:
    """Data `AAAA-MM-DD` a N dias da data do relógio injetado."""
    return (env.now.astimezone(UTC).date() + timedelta(days=_offset_days(env, request))).isoformat()


def gen_datetime(env: Environment, request: ValueRequest) -> JsonValue:
    """Data e hora RFC 3339 em UTC, a N dias do relógio injetado, com hora sorteada."""
    base = env.now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    moment = base + timedelta(days=_offset_days(env, request), seconds=env.rng.randrange(86400))
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def gen_choice(env: Environment, request: ValueRequest) -> JsonValue:
    """Um valor sorteado da lista `values`."""
    values = request.args.get("values")
    if not isinstance(values, list) or not values:
        raise ConfigError("O gerador choice exige a lista values.")
    return env.rng.choice(values)


def gen_constant(env: Environment, request: ValueRequest) -> JsonValue:
    """Sempre o valor de `value`."""
    return request.args.get("value")


def gen_sequence(env: Environment, request: ValueRequest) -> JsonValue:
    """`start + passo * posição`; com `prefix`, vira texto."""
    number = _int_arg(request, "start", 1) + _int_arg(request, "step", 1) * request.draw_index
    prefix = _text_arg(request, "prefix", "")
    return f"{prefix}{number}" if prefix else number

"""Catálogo FECHADO de geradores de dados: nomes, argumentos aceitos e validação.

O domínio só conhece o contrato de cada gerador (nome, argumentos, se aceita `unique`);
quem os implementa é `adapters/datagen`, e um teste garante que os nomes dos dois lados
coincidem. Argumento é validado aqui, com tipo estrito (`true` não é `1`), sem repetir
o valor recebido nas mensagens. Este módulo é puro.
"""

from collections.abc import Mapping
from typing import Literal, cast

from pydantic import Field

from harness_dast.domain.api_model import safe_identifier
from harness_dast.domain.api_schema import ApiModel, JsonScalar, JsonValue
from harness_dast.domain.errors import ConfigError

ArgKind = Literal["int", "str", "bool", "scalar", "scalar_list"]
BR_DDD_CODES = (
    *range(11, 20), 21, 22, 24, 27, 28, *range(31, 36), 37, 38, *range(41, 50), 51, 53, 54, 55,
    *range(61, 70), 71, 73, 74, 75, 77, 79, *range(81, 90), *range(91, 100),
)  # fmt: skip
"""Códigos de área (DDD) em uso no Brasil, segundo o plano de numeração da Anatel."""
BR_UF_CODES = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR",
    "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
)  # fmt: skip
"""Siglas das 27 unidades da federação."""
_MAX_LIST = 200
MAX_ARG_TEXT = 1000
"""Tamanho máximo de um argumento de texto de gerador."""


class ArgSpec(ApiModel):
    """Um argumento aceito por um gerador.

    Attributes:
        name: Nome do argumento.
        kind: Tipo aceito.
        required: Se é obrigatório.
        default: Valor usado quando ausente (`None` = sem padrão).
        minimum: Menor inteiro aceito (só `int`).
        maximum: Maior inteiro aceito (só `int`).
        choices: Valores permitidos, se for um conjunto fechado.
    """

    name: str
    kind: ArgKind
    required: bool = False
    default: JsonScalar = None
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[int | str, ...] | None = None


class GeneratorDef(ApiModel):
    """Contrato de um gerador do catálogo.

    Attributes:
        name: Nome usado em `generator:` no `data-rules.yml`.
        args: Argumentos aceitos.
        supports_unique: Se aceita `unique: true` (valor único por execução).
        ordered_pairs: Pares (menor, maior) de argumentos que devem estar em ordem.
        summary: Uma linha em português para a documentação.
    """

    name: str
    args: tuple[ArgSpec, ...] = Field(default=())
    supports_unique: bool = False
    ordered_pairs: tuple[tuple[str, str], ...] = ()
    summary: str = ""


def _int(
    name: str,
    *,
    required: bool = False,
    minimum: int | None = None,
    maximum: int | None = None,
    default: int | None = None,
    choices: tuple[int | str, ...] | None = None,
) -> ArgSpec:
    return ArgSpec(
        name=name,
        kind="int",
        required=required,
        minimum=minimum,
        maximum=maximum,
        default=default,
        choices=choices,
    )


def _bool(name: str, *, default: bool = False) -> ArgSpec:
    return ArgSpec(name=name, kind="bool", default=default)


_FORMATTED = _bool("formatted")
_OFFSETS = (
    _int("min_offset_days", minimum=-36500, maximum=36500, default=-365),
    _int("max_offset_days", minimum=-36500, maximum=36500, default=365),
)

CATALOG: tuple[GeneratorDef, ...] = (
    GeneratorDef(
        name="numeric",
        args=(_int("digits", required=True, minimum=1, maximum=30),),
        supports_unique=True,
        summary="Texto de N dígitos decimais.",
    ),
    GeneratorDef(
        name="integer",
        args=(_int("min"), _int("max")),
        supports_unique=True,
        ordered_pairs=(("min", "max"),),
        summary="Inteiro no intervalo (por padrão, o do esquema).",
    ),
    GeneratorDef(
        name="number",
        args=(_int("min"), _int("max"), _int("decimals", minimum=0, maximum=6, default=2)),
        ordered_pairs=(("min", "max"),),
        summary="Número decimal no intervalo.",
    ),
    GeneratorDef(name="boolean", summary="Verdadeiro ou falso."),
    GeneratorDef(
        name="alphanumeric",
        args=(
            _int("length", minimum=1, maximum=256),
            ArgSpec(name="prefix", kind="str", default=""),
        ),
        supports_unique=True,
        summary="Texto de letras e dígitos, com tamanho e prefixo opcionais.",
    ),
    GeneratorDef(name="uuid", supports_unique=True, summary="UUID versão 4."),
    GeneratorDef(
        name="email",
        args=(
            ArgSpec(name="domain", kind="str", default="example.test"),
            ArgSpec(name="prefix", kind="str", default="hd"),
        ),
        supports_unique=True,
        summary="E-mail em domínio de teste reservado (padrão: example.test).",
    ),
    GeneratorDef(
        name="uri",
        args=(ArgSpec(name="base", kind="str", default="https://example.test"),),
        supports_unique=True,
        summary="URL no domínio de teste.",
    ),
    GeneratorDef(
        name="date",
        args=_OFFSETS,
        ordered_pairs=(("min_offset_days", "max_offset_days"),),
        summary="Data AAAA-MM-DD a N dias de hoje (hoje vem do relógio injetado).",
    ),
    GeneratorDef(
        name="datetime",
        args=_OFFSETS,
        ordered_pairs=(("min_offset_days", "max_offset_days"),),
        summary="Data e hora em UTC (RFC 3339) a N dias de agora.",
    ),
    GeneratorDef(
        name="choice",
        args=(ArgSpec(name="values", kind="scalar_list", required=True),),
        summary="Um valor sorteado da lista.",
    ),
    GeneratorDef(
        name="constant",
        args=(ArgSpec(name="value", kind="scalar", required=True),),
        summary="Sempre o mesmo valor.",
    ),
    GeneratorDef(
        name="sequence",
        args=(
            _int("start", default=1),
            _int("step", minimum=1, maximum=1000, default=1),
            ArgSpec(name="prefix", kind="str", default=""),
        ),
        supports_unique=True,
        summary="Sequência crescente; repete entre execuções (use numeric para unicidade).",
    ),
    GeneratorDef(name="br.cpf", args=(_FORMATTED,), supports_unique=True, summary="CPF válido."),
    GeneratorDef(name="br.cnpj", args=(_FORMATTED,), supports_unique=True, summary="CNPJ válido."),
    GeneratorDef(
        name="br.cns",
        args=(
            ArgSpec(
                name="kind", kind="str", default="definitive", choices=("definitive", "provisional")
            ),
        ),
        supports_unique=True,
        summary="Cartão Nacional de Saúde com dígito verificador válido.",
    ),
    GeneratorDef(
        name="br.phone",
        args=(
            _bool("mobile", default=True),
            _int("ddd", choices=BR_DDD_CODES),
            _FORMATTED,
            _bool("country_code"),
        ),
        supports_unique=True,
        summary="Telefone brasileiro com DDD em uso.",
    ),
    GeneratorDef(
        name="br.crm",
        args=(
            _int("digits", minimum=4, maximum=8, default=7),
            ArgSpec(name="uf", kind="str", default="SP", choices=BR_UF_CODES),
        ),
        supports_unique=True,
        summary="CRM sintético NNNNNNN-UF (com unique, o número não repete entre execuções).",
    ),
    GeneratorDef(
        name="br.cep", args=(_FORMATTED,), supports_unique=True, summary="CEP de 8 dígitos."
    ),
)


def generator_names() -> tuple[str, ...]:
    """Nomes de todos os geradores do catálogo, na ordem de declaração."""
    return tuple(definition.name for definition in CATALOG)


def get_generator(name: str) -> GeneratorDef:
    """Devolve a definição do gerador.

    Raises:
        ConfigError: Se o nome não existe no catálogo (a mensagem lista os nomes válidos).
    """
    for definition in CATALOG:
        if definition.name == name:
            return definition
    raise ConfigError(
        f"Gerador desconhecido; os geradores do catálogo são: {', '.join(generator_names())}.",
        hint="Use um nome do catálogo em generator: (veja docs/reference/data-rules-yml.md).",
    )


def _check_kind(spec: ArgSpec, value: object) -> bool:
    if spec.kind == "bool":
        return type(value) is bool
    if spec.kind == "int":
        return type(value) is int
    if spec.kind == "str":
        return isinstance(value, str) and len(value) <= MAX_ARG_TEXT
    if spec.kind == "scalar":
        return _is_scalar(value)
    return (
        isinstance(value, list)
        and 0 < len(value) <= _MAX_LIST
        and all(_is_scalar(item) for item in value)
    )


def _is_scalar(value: object) -> bool:
    if isinstance(value, str):
        return len(value) <= MAX_ARG_TEXT
    return value is None or isinstance(value, bool | int | float)


def _check_arg(generator: str, spec: ArgSpec, value: object) -> None:
    where = f"argumento '{spec.name}' do gerador '{generator}'"
    if not _check_kind(spec, value):
        raise ConfigError(f"{where}: tipo ou tamanho inválido (esperado {spec.kind}).")
    if isinstance(value, int) and not isinstance(value, bool):
        low, high = spec.minimum, spec.maximum
        if (low is not None and value < low) or (high is not None and value > high):
            raise ConfigError(f"{where}: valor fora do intervalo {low}..{high}.")
    if spec.choices is not None and value not in spec.choices:
        raise ConfigError(f"{where}: valor fora das opções permitidas.")


def validate_args(definition: GeneratorDef, args: Mapping[str, object]) -> dict[str, JsonValue]:
    """Valida os argumentos de um gerador e devolve-os com os padrões aplicados.

    Args:
        definition: Definição do gerador.
        args: Argumentos como escritos na regra.

    Returns:
        Novo dicionário com os argumentos informados mais os padrões; argumentos sem padrão
        e não informados ficam ausentes.

    Raises:
        ConfigError: Argumento desconhecido, ausente (obrigatório), de tipo errado, fora do
            intervalo ou fora de ordem. Nenhuma mensagem repete o valor recebido.
    """
    known = {spec.name: spec for spec in definition.args}
    unknown = sorted(set(args) - set(known))
    if unknown:
        raise ConfigError(
            f"Gerador '{definition.name}' não aceita o argumento {safe_identifier(unknown[0])}.",
            hint=f"Argumentos aceitos: {', '.join(known) or 'nenhum'}.",
        )
    result: dict[str, JsonValue] = {}
    for spec in definition.args:
        if spec.name in args:
            _check_arg(definition.name, spec, args[spec.name])
            # `_check_arg` já garantiu que o valor é escalar ou lista de escalares.
            result[spec.name] = cast(JsonValue, args[spec.name])
        elif spec.required:
            raise ConfigError(f"Gerador '{definition.name}' exige o argumento '{spec.name}'.")
        elif spec.default is not None:
            result[spec.name] = spec.default
    _check_order(definition, result)
    return result


def _check_order(definition: GeneratorDef, args: Mapping[str, JsonValue]) -> None:
    for low_name, high_name in definition.ordered_pairs:
        low, high = args.get(low_name), args.get(high_name)
        if isinstance(low, int) and isinstance(high, int) and low > high:
            raise ConfigError(
                f"Gerador '{definition.name}': '{low_name}' não pode ser maior que '{high_name}'."
            )

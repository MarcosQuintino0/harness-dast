"""Geradores de documentos e contatos brasileiros SINTÉTICOS (CPF, CNPJ, CNS, telefone, CEP).

CPF, CNPJ e CNS saem com dígitos verificadores válidos (veja `checkdigits.py`), mas não
foram emitidos a ninguém. Telefone e CEP têm formato válido e DDD em uso, e por isso PODEM
coincidir com números reais: use-os só em ambiente de teste com dados sintéticos.
"""

from harness_dast.adapters.datagen.basic import Environment, random_digits
from harness_dast.adapters.datagen.checkdigits import (
    cnpj_check_digits,
    cns_definitive,
    cns_provisional,
    cpf_check_digits,
)
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.datagen_catalog import BR_DDD_CODES
from harness_dast.domain.request_builder import ValueRequest
from harness_dast.domain.unique_values import unique_digits


def _flag(request: ValueRequest, name: str, *, default: bool = False) -> bool:
    value = request.args.get(name, default)
    return value if isinstance(value, bool) else default


def _digits(env: Environment, request: ValueRequest, width: int) -> str:
    """`width` dígitos: derivados da etiqueta e do contador se único, senão sorteados."""
    if request.unique:
        return unique_digits(request.run_tag, request.counter, width)
    return random_digits(env, width)


def _break_repetition(digits: str) -> str:
    """Se todos os dígitos forem iguais, muda o primeiro (CPF/CNPJ repetidos são inválidos).

    Em valores únicos, o primeiro dígito vem do prefixo da etiqueta, igual em toda a
    execução; somar 1 a ele afasta este valor de todos os demais da execução.
    """
    if len(set(digits)) == 1:
        return str((int(digits[0]) + 1) % 10) + digits[1:]
    return digits


def gen_cpf(env: Environment, request: ValueRequest) -> JsonValue:
    """CPF com dígitos verificadores válidos; `formatted` usa a máscara 000.000.000-00."""
    base = _break_repetition(_digits(env, request, 9))
    full = base + cpf_check_digits(base)
    if _flag(request, "formatted"):
        return f"{full[:3]}.{full[3:6]}.{full[6:9]}-{full[9:]}"
    return full


def gen_cnpj(env: Environment, request: ValueRequest) -> JsonValue:
    """CNPJ numérico com dígitos válidos, filial 0001; `formatted` usa 00.000.000/0000-00."""
    base = _break_repetition(_digits(env, request, 8)) + "0001"
    full = base + cnpj_check_digits(base)
    if _flag(request, "formatted"):
        return f"{full[:2]}.{full[2:5]}.{full[5:8]}/{full[8:12]}-{full[12:]}"
    return full


def gen_cns(env: Environment, request: ValueRequest) -> JsonValue:
    """CNS de 15 dígitos válido; `kind` escolhe `definitive` (1 ou 2) ou `provisional` (7-9)."""
    if request.args.get("kind") == "provisional":
        lead = "7" if request.unique else str(env.rng.choice((7, 8, 9)))
        # O 14º dígito é um enchimento: se o dígito verificador cair em 10, é ele que muda,
        # nunca os dígitos que garantem a unicidade.
        return cns_provisional(lead + _digits(env, request, 12) + "0")
    lead = "1" if request.unique else str(env.rng.choice((1, 2)))
    return cns_definitive(lead + _digits(env, request, 10))


def gen_phone(env: Environment, request: ValueRequest) -> JsonValue:
    """Telefone brasileiro: DDD em uso + celular (9 + 8 dígitos) ou fixo (2-5 + 7 dígitos)."""
    ddd = request.args.get("ddd")
    area = str(ddd) if isinstance(ddd, int) else str(env.rng.choice(BR_DDD_CODES))
    if _flag(request, "mobile", default=True):
        subscriber = "9" + _digits(env, request, 8)
        masked = f"{subscriber[:5]}-{subscriber[5:]}"
    else:
        lead = "3" if request.unique else str(env.rng.choice((2, 3, 4, 5)))
        subscriber = lead + _digits(env, request, 7)
        masked = f"{subscriber[:4]}-{subscriber[4:]}"
    country = _flag(request, "country_code")
    if _flag(request, "formatted"):
        return f"{'+55 ' if country else ''}({area}) {masked}"
    return f"{'55' if country else ''}{area}{subscriber}"


def gen_cep(env: Environment, request: ValueRequest) -> JsonValue:
    """CEP de 8 dígitos (nunca 00000000); `formatted` usa 00000-000."""
    cep = _digits(env, request, 8)
    if cep == "0" * 8:
        cep = "1" + cep[1:]
    return f"{cep[:5]}-{cep[5:]}" if _flag(request, "formatted") else cep


def gen_crm(env: Environment, request: ValueRequest) -> JsonValue:
    """CRM sintético `NNNNNNN-UF`: `digits` dígitos (únicos por execução se `unique`) e a UF."""
    width = request.args.get("digits")
    uf = request.args.get("uf")
    number = _digits(env, request, width if isinstance(width, int) else 7)
    return f"{number}-{uf if isinstance(uf, str) else 'SP'}"

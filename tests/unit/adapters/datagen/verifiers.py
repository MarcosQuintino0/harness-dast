"""Verificadores independentes de CPF, CNPJ, CNS, telefone e CEP, usados como oráculo.

Foram escritos de outra forma que os geradores (somas completas por posição, em vez de
"calcular o dígito e anexar") para que um erro de lógica num lado não se repita no outro.
Fonte dos algoritmos: ver `harness_dast/adapters/datagen/checkdigits.py`.
"""

import re

from harness_dast.domain.datagen_catalog import BR_DDD_CODES


def digits_of(text: str) -> str:
    return re.sub(r"\D", "", text)


def valid_cpf(text: str) -> bool:
    digits = digits_of(text)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for size in (9, 10):
        total = sum(int(digits[i]) * (size + 1 - i) for i in range(size))
        expected = (total * 10) % 11 % 10
        if int(digits[size]) != expected:
            return False
    return True


def valid_cnpj(text: str) -> bool:
    digits = digits_of(text)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    for size in (12, 13):
        weights = [(size - i - 1) % 8 + 2 for i in range(size)]
        total = sum(int(digits[i]) * weights[i] for i in range(size))
        expected = 0 if total % 11 < 2 else 11 - total % 11
        if int(digits[size]) != expected:
            return False
    return True


def valid_cns(text: str) -> bool:
    digits = digits_of(text)
    if len(digits) != 15 or digits[0] not in "12789":
        return False
    if digits[0] in "12" and digits[11:14] not in {"000", "001"}:
        return False
    return sum(int(d) * (15 - i) for i, d in enumerate(digits)) % 11 == 0


def valid_phone(text: str, *, mobile: bool) -> bool:
    digits = digits_of(text)
    if digits.startswith("55") and len(digits) in {12, 13}:
        digits = digits[2:]
    if len(digits) != (11 if mobile else 10) or int(digits[:2]) not in BR_DDD_CODES:
        return False
    return digits[2] == "9" if mobile else digits[2] in "2345"


def valid_cep(text: str) -> bool:
    digits = digits_of(text)
    return len(digits) == 8 and digits != "00000000"

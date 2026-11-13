import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness_dast.adapters.datagen.checkdigits import (
    cnpj_check_digits,
    cns_definitive,
    cns_provisional,
    cpf_check_digits,
)
from tests.unit.adapters.datagen.verifiers import valid_cnpj, valid_cns, valid_cpf

KNOWN_VALID_CPFS = ["52998224725", "11144477735", "39053344705", "12345678909"]
KNOWN_INVALID_CPFS = ["52998224724", "11111111111", "12345678900", "5299822472", "529982247250"]
KNOWN_VALID_CNPJS = ["11222333000181", "11444777000161", "00000000000191"]
KNOWN_INVALID_CNPJS = ["11222333000182", "11111111111111", "1122233300018"]

nine_digits = st.text(alphabet="0123456789", min_size=9, max_size=9)
twelve_digits = st.text(alphabet="0123456789", min_size=12, max_size=12)


@pytest.mark.parametrize("cpf", KNOWN_VALID_CPFS)
def test_cpf_check_digits_reproduce_known_valid_numbers(cpf: str) -> None:
    assert cpf_check_digits(cpf[:9]) == cpf[9:]


def test_cpf_check_digits_match_the_worked_example_of_the_reference() -> None:
    # 529.982.247-25: somas 295 (mod 11 = 9, dígito 2) e 347 (mod 11 = 6, dígito 5).
    assert cpf_check_digits("529982247") == "25"


@pytest.mark.parametrize("cnpj", KNOWN_VALID_CNPJS)
def test_cnpj_check_digits_reproduce_known_valid_numbers(cnpj: str) -> None:
    assert cnpj_check_digits(cnpj[:12]) == cnpj[12:]


def test_cnpj_check_digits_match_the_worked_example_of_the_reference() -> None:
    # 11.222.333/0001-81: somas 102 (mod 11 = 3, dígito 8) e 120 (mod 11 = 10, dígito 1).
    assert cnpj_check_digits("112223330001") == "81"


@pytest.mark.parametrize("cpf", KNOWN_VALID_CPFS)
def test_the_independent_cpf_verifier_accepts_known_valid_numbers(cpf: str) -> None:
    assert valid_cpf(cpf)


@pytest.mark.parametrize("cpf", KNOWN_INVALID_CPFS)
def test_the_independent_cpf_verifier_rejects_known_invalid_numbers(cpf: str) -> None:
    assert not valid_cpf(cpf)


@pytest.mark.parametrize("cnpj", KNOWN_VALID_CNPJS)
def test_the_independent_cnpj_verifier_accepts_known_valid_numbers(cnpj: str) -> None:
    assert valid_cnpj(cnpj)


@pytest.mark.parametrize("cnpj", KNOWN_INVALID_CNPJS)
def test_the_independent_cnpj_verifier_rejects_known_invalid_numbers(cnpj: str) -> None:
    assert not valid_cnpj(cnpj)


@given(nine_digits)
def test_cpf_check_digits_always_produce_a_number_the_verifier_accepts(base: str) -> None:
    if len(set(base)) == 1:
        return

    assert valid_cpf(base + cpf_check_digits(base))


@given(twelve_digits)
def test_cnpj_check_digits_always_produce_a_number_the_verifier_accepts(base: str) -> None:
    if len(set(base + "00")) == 1:
        return

    assert valid_cnpj(base + cnpj_check_digits(base))


@given(nine_digits, st.integers(min_value=0, max_value=1), st.integers(min_value=1, max_value=9))
def test_a_changed_cpf_check_digit_always_fails(base: str, which: int, delta: int) -> None:
    if len(set(base)) == 1:
        return
    valid = base + cpf_check_digits(base)
    index = 9 + which
    mutated = valid[:index] + str((int(valid[index]) + delta) % 10) + valid[index + 1 :]

    assert not valid_cpf(mutated)


@given(twelve_digits, st.integers(min_value=0, max_value=1), st.integers(min_value=1, max_value=9))
def test_a_changed_cnpj_check_digit_always_fails(base: str, which: int, delta: int) -> None:
    valid = base + cnpj_check_digits(base)
    index = 12 + which
    mutated = valid[:index] + str((int(valid[index]) + delta) % 10) + valid[index + 1 :]

    assert not valid_cnpj(mutated)


def test_most_single_digit_changes_in_a_valid_cpf_are_detected() -> None:
    valid = "52998224725"
    detected = total = 0
    for index in range(11):
        for digit in "0123456789":
            if digit == valid[index]:
                continue
            total += 1
            detected += not valid_cpf(valid[:index] + digit + valid[index + 1 :])

    assert detected == total  # com este número nenhuma troca cai na colisão 10/11 -> 0


def test_a_transposition_of_adjacent_digits_is_detected_in_a_valid_cnpj() -> None:
    valid = "11222333000181"
    for index in range(13):
        swapped = list(valid)
        swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
        if swapped != list(valid):
            assert not valid_cnpj("".join(swapped))


def test_cns_definitive_example_uses_the_000_suffix_and_a_valid_digit() -> None:
    cns = cns_definitive("10000000000")

    assert cns[11:14] == "000"
    assert valid_cns(cns)
    assert len(cns) == 15


def test_cns_definitive_switches_to_the_001_suffix_when_the_digit_would_be_ten() -> None:
    # PIS 10000000008: soma ponderada 15*1 + 5*8 = 55, que dá resto 0... procuramos resto 1.
    candidates = [f"1{n:010d}" for n in range(200)]
    with_001 = [c for c in map(cns_definitive, candidates) if c[11:14] == "001"]

    assert with_001, "nenhum PIS da amostra exigiu o sufixo 001"
    assert all(valid_cns(c) for c in with_001)


@given(st.sampled_from("12"), st.text(alphabet="0123456789", min_size=10, max_size=10))
def test_cns_definitive_is_always_valid(lead: str, rest: str) -> None:
    assert valid_cns(cns_definitive(lead + rest))


@given(st.sampled_from("789"), st.text(alphabet="0123456789", min_size=13, max_size=13))
def test_cns_provisional_is_always_valid(lead: str, rest: str) -> None:
    cns = cns_provisional(lead + rest)

    assert len(cns) == 15
    assert valid_cns(cns)


@given(
    st.sampled_from("12"),
    st.text(alphabet="0123456789", min_size=10, max_size=10),
    st.integers(min_value=0, max_value=14),
    st.integers(min_value=1, max_value=9),
)
def test_a_changed_cns_digit_fails_except_at_the_weight_eleven_blind_spot(
    lead: str, rest: str, index: int, delta: int
) -> None:
    valid = cns_definitive(lead + rest)
    mutated = valid[:index] + str((int(valid[index]) + delta) % 10) + valid[index + 1 :]

    if index == 4:  # peso 11 ≡ 0 (mod 11): a soma não enxerga esta posição
        assert valid_cns(mutated)
    else:
        assert not valid_cns(mutated)


def test_the_cns_verifier_rejects_numbers_with_a_wrong_prefix_or_length() -> None:
    assert not valid_cns("3" + "0" * 14)
    assert not valid_cns("1" * 14)
    assert not valid_cns("123456789012345")

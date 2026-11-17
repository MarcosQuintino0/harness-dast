"""Classificação e adulteração de tokens: nunca forja assinatura, nunca troca identidade."""

import base64
import json

import pytest

from harness_dast.domain.authz.token import (
    MAX_TOKEN_CHARS,
    build_tampered_tokens,
    classify_token,
)


def b64(value: object) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def raw64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()


def jwt(header: object = None, payload: object = None, signature: str = "c2ln") -> str:
    head = {"alg": "HS256", "typ": "JWT"} if header is None else header
    body = {"sub": "pac_a", "role": "paciente", "exp": 4102444800} if payload is None else payload
    return f"{b64(head)}.{b64(body)}.{signature}"


def decode(segment: str) -> dict[str, object]:
    parsed = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
    assert isinstance(parsed, dict)
    return parsed


def by_name(token: str, **kwargs: bool) -> dict[str, str]:
    return {item.variant: item.value for item in build_tampered_tokens(token, **kwargs)}


# --- classify_token: válido -----------------------------------------------------------------


def test_classify_recognizes_a_well_formed_jwt() -> None:
    found = classify_token(jwt())

    assert found is not None
    assert found.header["alg"] == "HS256"
    assert found.payload["sub"] == "pac_a"
    assert found.signature == "c2ln"


def test_classify_accepts_an_empty_signature() -> None:
    found = classify_token(jwt(signature=""))

    assert found is not None
    assert found.signature == ""


# --- classify_token: ausente, inválido e malformado -------------------------------------------


@pytest.mark.parametrize("token", ["", "   ", "\n"])
def test_classify_refuses_empty_or_blank(token: str) -> None:
    assert classify_token(token) is None


def test_classify_refuses_two_four_and_five_segments() -> None:
    good = jwt().split(".")

    assert classify_token(".".join(good[:2])) is None
    assert classify_token(".".join([*good, "x"])) is None
    assert classify_token(".".join([*good, "x", "y"])) is None


def test_classify_refuses_invalid_base64_segments() -> None:
    payload = b64({"sub": "x"})

    assert classify_token(f"@@@@.{payload}.sig") is None
    assert classify_token(f"{b64({'alg': 'HS256'})}.%%%%.sig") is None
    assert classify_token(f"a.{payload}.sig") is None  # tamanho 1 mod 4 não existe em base64


def test_classify_refuses_invalid_json_in_the_header() -> None:
    not_utf8 = base64.urlsafe_b64encode(b"\xff\xfe").decode()

    assert classify_token(f"{raw64('{nao e json')}.{b64({'sub': 'x'})}.sig") is None
    assert classify_token(f"{not_utf8}.{b64({})}.s") is None


def test_classify_refuses_non_object_segments() -> None:
    assert classify_token(f"{b64([1, 2])}.{b64({'sub': 'x'})}.sig") is None
    assert classify_token(f"{b64({'alg': 'HS256'})}.{b64('texto')}.sig") is None
    assert classify_token(f"{b64({'alg': 'HS256'})}.{b64(7)}.sig") is None


@pytest.mark.parametrize("header", [{"typ": "JWT"}, {"alg": 256}, {"alg": None}, {"alg": ["x"]}])
def test_classify_refuses_a_header_without_a_textual_alg(header: object) -> None:
    assert classify_token(jwt(header=header)) is None


def test_classify_refuses_a_token_longer_than_the_limit() -> None:
    assert classify_token(jwt(payload={"sub": "x" * MAX_TOKEN_CHARS})) is None


def test_classify_treats_plain_text_as_opaque() -> None:
    assert classify_token("tok-pac_a-1234567890") is None


# --- build_tampered_tokens: JWT ---------------------------------------------------------------


def test_jwt_gets_the_three_variants_and_none_equals_the_original() -> None:
    token = jwt()

    variants = by_name(token)

    assert list(variants) == ["stripped_signature", "alg_none", "altered_claims"]
    assert token not in variants.values()


def test_stripped_signature_keeps_header_and_payload_and_empties_the_third_segment() -> None:
    token = jwt()
    head, body, _ = token.split(".")

    assert by_name(token)["stripped_signature"] == f"{head}.{body}."


def test_alg_none_rewrites_only_the_algorithm_and_drops_the_signature() -> None:
    token = jwt()
    new_head, new_body, new_sig = by_name(token)["alg_none"].split(".")

    assert decode(new_head) == {"alg": "none", "typ": "JWT"}
    assert new_body == token.split(".")[1]
    assert new_sig == ""


def test_altered_claims_adds_one_harmless_claim_and_keeps_the_identity_and_signature() -> None:
    token = jwt()
    head, body, sig = by_name(token)["altered_claims"].split(".")

    claims = decode(body)
    original = decode(token.split(".")[1])
    assert claims["hdast"] == "1"
    assert {k: v for k, v in claims.items() if k != "hdast"} == original
    assert (claims["sub"], claims["role"], claims["exp"]) == ("pac_a", "paciente", 4102444800)
    assert head == token.split(".")[0]
    assert sig == "c2ln"


def test_no_variant_carries_a_valid_signature() -> None:
    token = jwt()
    original_signature = token.split(".")[2]

    for value in by_name(token).values():
        signature = value.split(".")[2]
        assert signature in {"", original_signature}
        if signature == original_signature:
            # só a variante de conteúdo mantém a assinatura antiga, que já não confere
            assert value.split(".")[1] != token.split(".")[1]


def test_jwt_without_signature_gets_no_stripped_variant() -> None:
    variants = by_name(jwt(signature=""))

    assert "stripped_signature" not in variants
    assert set(variants) == {"alg_none", "altered_claims"}


def test_jwt_already_alg_none_gets_no_alg_none_variant() -> None:
    variants = by_name(jwt(header={"alg": "none"}))

    assert "alg_none" not in variants
    assert set(variants) == {"stripped_signature", "altered_claims"}


def test_a_token_that_already_has_the_added_claim_does_not_repeat_itself() -> None:
    token = jwt(payload={"sub": "a", "hdast": "1"})

    assert "altered_claims" not in by_name(token)


# --- build_tampered_tokens: opaco -------------------------------------------------------------


def test_opaque_token_gets_only_the_scrambled_variant_with_same_size_and_alphabet() -> None:
    token = "tok-pac_a-1234567890"  # noqa: S105 - sentinela de teste, não um segredo

    variants = by_name(token)

    assert list(variants) == ["scrambled"]
    scrambled = variants["scrambled"]
    assert scrambled == token[::-1]
    assert scrambled != token
    assert sorted(scrambled) == sorted(token)


def test_palindrome_is_rotated_by_one_character() -> None:
    assert by_name("abcba")["scrambled"] == "bcbaa"


@pytest.mark.parametrize("token", ["", " ", "a", "aa", "zzzz", "com espaco", "tab\there"])
def test_tokens_that_cannot_be_scrambled_get_no_variant(token: str) -> None:
    assert build_tampered_tokens(token) == ()


def test_api_key_is_never_treated_as_jwt() -> None:
    token = jwt()

    assert list(by_name(token, allow_jwt=False)) == ["scrambled"]


@pytest.mark.parametrize("token", ["a.b", "a.b.c.d", "a.b.c.d.e", f"@@.{b64({})}.s"])
def test_malformed_jwt_shaped_text_falls_back_to_scrambled(token: str) -> None:
    assert [item.variant for item in build_tampered_tokens(token)] == ["scrambled"]


def test_variants_are_deterministic() -> None:
    assert build_tampered_tokens(jwt()) == build_tampered_tokens(jwt())
    assert build_tampered_tokens("tok-abc-123") == build_tampered_tokens("tok-abc-123")


def test_token_value_never_appears_in_the_repr() -> None:
    token = jwt()

    assert token not in repr(build_tampered_tokens(token))
    assert token not in repr(classify_token(token))

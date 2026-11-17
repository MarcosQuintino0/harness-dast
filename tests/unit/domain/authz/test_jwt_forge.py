"""Chave HMAC fraca de JWT: quebra offline, re-assinatura de prova, teto e redação (ADR 0098)."""

import base64
import hashlib
import hmac
import json

from harness_dast.domain.authz.findings_access import tampered_finding
from harness_dast.domain.authz.jwt_forge import (
    EXPIRED_AT,
    MAX_EXTRA_CANDIDATES,
    MAX_PROOF_REQUESTS_PER_OPERATION,
    MAX_WEAK_KEY_OPERATIONS,
    WEAK_HMAC_KEYS,
    WEAK_KEYS_VERSION,
    WeakKey,
    find_weak_key,
    forge_with_weak_key,
)

DIGESTS = {"HS256": hashlib.sha256, "HS384": hashlib.sha384, "HS512": hashlib.sha512}
STRONG_KEY = "k9#Qz-8vLm2$Xr7@pW4^tB6&"


def seg(value: object) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def signed(key: str, alg: str = "HS256") -> str:
    body = {"sub": "pac_a", "role": "paciente", "exp": 4102444800}
    signing = f"{seg({'alg': alg, 'typ': 'JWT'})}.{seg(body)}"
    digest = hmac.new(key.encode(), signing.encode(), DIGESTS[alg]).digest()
    return f"{signing}.{base64.urlsafe_b64encode(digest).rstrip(b'=').decode()}"


def decode(part: str) -> dict[str, object]:
    parsed = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    assert isinstance(parsed, dict)
    return parsed


def test_the_list_is_small_fixed_and_has_no_duplicates() -> None:
    assert 20 <= len(WEAK_HMAC_KEYS) <= 60
    assert len(set(WEAK_HMAC_KEYS)) == len(WEAK_HMAC_KEYS)
    assert WEAK_KEYS_VERSION == 1


def test_a_token_signed_with_a_listed_key_is_cracked_for_each_hmac_algorithm() -> None:
    for alg in ("HS256", "HS384", "HS512"):
        found = find_weak_key(signed("secret", alg))

        assert found == WeakKey(key="secret", algorithm=alg)


def test_a_strong_key_is_not_found() -> None:
    assert find_weak_key(signed(STRONG_KEY)) is None


def test_the_caller_may_add_a_few_context_words_but_never_more_than_the_cap() -> None:
    token = signed("meuproduto")
    extras = [f"palavra{n}" for n in range(MAX_EXTRA_CANDIDATES)]

    assert find_weak_key(token) is None
    assert find_weak_key(token, ("meuproduto",)) == WeakKey("meuproduto", "HS256")
    assert find_weak_key(token, [*extras, "meuproduto"]) is None


def test_tokens_that_are_not_hmac_jwts_are_never_cracked() -> None:
    none_alg = f"{seg({'alg': 'none'})}.{seg({'sub': 'a'})}."
    rs256 = f"{seg({'alg': 'RS256'})}.{seg({'sub': 'a'})}.c2ln"

    for token in ("", "opaco-123", "a.b.c", none_alg, rs256):
        assert find_weak_key(token) is None


def test_the_forged_tokens_keep_identity_and_header_and_only_add_a_harmless_claim() -> None:
    original = signed("secret")
    pair = forge_with_weak_key(original, WeakKey("secret", "HS256"))

    assert pair is not None
    harmless, expired = pair
    assert (harmless.variant, expired.variant) == ("weak_key", "weak_key_expired")
    head, body, signature = harmless.value.split(".")
    assert head == original.split(".")[0]
    claims = decode(body)
    assert claims["sub"] == "pac_a"
    assert claims["role"] == "paciente"
    assert claims["exp"] == 4102444800
    assert claims["hdast"] == "1"
    assert signature
    assert signature != original.split(".")[2]
    assert find_weak_key(harmless.value) == WeakKey("secret", "HS256")


def test_the_expired_token_has_exp_in_the_past_and_a_valid_signature() -> None:
    pair = forge_with_weak_key(signed("secret"), WeakKey("secret", "HS256"))

    assert pair is not None
    assert decode(pair[1].value.split(".")[1])["exp"] == EXPIRED_AT
    assert find_weak_key(pair[1].value) is not None


def test_forging_from_something_that_is_not_a_jwt_returns_nothing() -> None:
    assert forge_with_weak_key("opaco", WeakKey("secret", "HS256")) is None


def test_the_hard_cap_per_operation_and_per_run_is_small() -> None:
    assert MAX_PROOF_REQUESTS_PER_OPERATION == 2
    assert MAX_WEAK_KEY_OPERATIONS * MAX_PROOF_REQUESTS_PER_OPERATION <= 20


def test_neither_repr_nor_finding_reveals_the_key_or_the_token() -> None:
    original = signed("secret")
    pair = forge_with_weak_key(original, WeakKey("secret", "HS256"))
    assert pair is not None

    finding = tampered_finding(
        product="agenda",
        operation_id="obterPerfil",
        method="GET",
        path_template="/api/me",
        actor=("pac_a", "paciente"),
        variants=("weak_key", "weak_key_expired"),
        statuses=(200, 200),
    )

    shown = repr(WeakKey("secret", "HS256")) + repr(pair) + finding.model_dump_json()
    assert "'secret'" not in shown
    assert '"secret"' not in shown
    assert pair[0].value not in shown
    assert original not in shown
    assert "chave HMAC fraca" in finding.evidence
    assert finding.proposed_severity == "high"
    assert finding.cwe == 347

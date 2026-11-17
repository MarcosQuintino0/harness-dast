"""Chave HMAC fraca de JWT: quebra OFFLINE e re-assinatura de prova (ADR 0098).

O teste "token adulterado" (ADR 0039) só estraga o token. Este módulo acrescenta o caso em que o
servidor assina o JWT com uma chave HMAC fraca: tenta-se uma lista pequena, fixa e versionada
contra o token da PRÓPRIA conta de teste, sem nenhum pedido ao alvo. Achada a chave, monta-se um
token re-assinado com reivindicação inofensiva (`weak_key`) e, só se aquele for aceito, outro com
`exp` vencido (`weak_key_expired`). Nunca troca `sub`, `role` nem outra identidade ou papel.

Teto rígido, decidido aqui: no máximo `MAX_WEAK_KEY_OPERATIONS` operações por execução, cada uma
com no máximo `MAX_PROOF_REQUESTS_PER_OPERATION` pedidos. O texto da chave e dos tokens é dado
sensível: nenhum repr, mensagem ou achado os cita. As funções são puras e nunca levantam exceção.
"""

import hmac
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

from harness_dast.domain.authz.token import (
    ADDED_CLAIM,
    TamperedToken,
    b64url_decode,
    b64url_encode,
    classify_token,
    encode_object,
)

WEAK_KEYS_VERSION: Final = 1
"""Versão da lista: muda sempre que uma palavra entra ou sai (o relatório a cita)."""

WEAK_HMAC_KEYS: Final[tuple[str, ...]] = (
    "secret",
    "secrets",
    "secretkey",
    "secret_key",
    "secret-key",
    "supersecret",
    "super-secret",
    "mysecret",
    "my_secret",
    "mysecretkey",
    "s3cr3t",
    "password",
    "passw0rd",
    "pass",
    "123456",
    "12345678",
    "123456789",
    "1234",
    "qwerty",
    "abc123",
    "admin",
    "administrator",
    "root",
    "changeme",
    "change-me",
    "changeit",
    "default",
    "test",
    "testing",
    "dev",
    "development",
    "staging",
    "token",
    "key",
    "private",
    "jwt",
    "jwtsecret",
    "jwt_secret",
    "jwt-secret",
    "jwt_secret_key",
    "hmac",
    "hs256",
    "signingkey",
    "signing-key",
    "your-256-bit-secret",
    "your_secret_key",
    "letmein",
    "welcome",
    "hdast",
)
"""Chaves fracas óbvias, testadas nesta ordem (poucas dezenas; nada de dicionário grande)."""

MAX_EXTRA_CANDIDATES: Final = 5
MAX_WEAK_KEY_OPERATIONS: Final = 10
"""Teto de operações por execução que recebem pedido de prova de chave fraca."""
MAX_PROOF_REQUESTS_PER_OPERATION: Final = 2
"""Por operação: um token com reivindicação inofensiva e, se aceito, um com `exp` vencido."""
EXPIRED_AT: Final = 1
"""`exp` do token vencido: um segundo depois da época Unix (sempre no passado)."""

_DIGESTS: Final[dict[str, str]] = {"HS256": "sha256", "HS384": "sha384", "HS512": "sha512"}


@dataclass(frozen=True)
class WeakKey:
    """Chave HMAC fraca achada: o texto é sensível e nunca sai deste objeto para artefato algum.

    Attributes:
        key: Texto da chave.
        algorithm: `HS256`, `HS384` ou `HS512`, o `alg` do próprio token.
    """

    key: str = field(repr=False)
    algorithm: str


def _sign(algorithm: str, key: str, signing_input: str) -> bytes | None:
    digest = _DIGESTS.get(algorithm)
    if digest is None:
        return None
    return hmac.new(key.encode("utf-8"), signing_input.encode("ascii"), digest).digest()


def _candidates(extra: Iterable[str]) -> tuple[str, ...]:
    """Lista fixa mais até `MAX_EXTRA_CANDIDATES` palavras vindas do chamador, sem repetição."""
    extras = tuple(item for item in dict.fromkeys(extra) if item and item not in WEAK_HMAC_KEYS)
    return WEAK_HMAC_KEYS + extras[:MAX_EXTRA_CANDIDATES]


def find_weak_key(token: str, extra_candidates: Iterable[str] = ()) -> WeakKey | None:
    """Tenta a lista de chaves fracas contra a assinatura HMAC do token, sem rede.

    Args:
        token: JWT da conta de teste (sensível).
        extra_candidates: Palavras derivadas do contexto (por exemplo o nome do produto no
            perfil); só as `MAX_EXTRA_CANDIDATES` primeiras além da lista fixa são usadas.

    Returns:
        A chave, se alguma da lista reproduz a assinatura; `None` se o token não é JWT com HMAC,
        não tem assinatura ou nenhuma palavra serve.
    """
    jwt = classify_token(token)
    if jwt is None or not jwt.signature:
        return None
    algorithm = jwt.header["alg"]
    given = b64url_decode(jwt.signature)
    if not isinstance(algorithm, str) or algorithm not in _DIGESTS or given is None:
        return None
    signing_input = token.rsplit(".", 1)[0]
    for key in _candidates(extra_candidates):
        expected = _sign(algorithm, key, signing_input)
        if expected is not None and hmac.compare_digest(expected, given):
            return WeakKey(key=key, algorithm=algorithm)
    return None


def _resign(head: str, claims: dict[str, object], weak: WeakKey) -> str:
    signing_input = f"{head}.{encode_object(claims)}"
    signature = _sign(weak.algorithm, weak.key, signing_input) or b""
    return f"{signing_input}.{b64url_encode(signature)}"


def forge_with_weak_key(token: str, weak: WeakKey) -> tuple[TamperedToken, TamperedToken] | None:
    """Os dois tokens de prova, re-assinados com a chave fraca (nunca com outra identidade).

    O primeiro (`weak_key`) só acrescenta a reivindicação inofensiva `hdast`; o segundo
    (`weak_key_expired`) também põe `exp` no passado e só deve ser enviado se o primeiro foi
    aceito. O cabeçalho original é mantido. Devolve `None` se o token não é um JWT.
    """
    jwt = classify_token(token)
    if jwt is None:
        return None
    head = token.split(".", 1)[0]
    claims: dict[str, object] = {**jwt.payload, ADDED_CLAIM[0]: ADDED_CLAIM[1]}
    harmless = _resign(head, claims, weak)
    expired = _resign(head, {**claims, "exp": EXPIRED_AT}, weak)
    return TamperedToken("weak_key", harmless), TamperedToken("weak_key_expired", expired)

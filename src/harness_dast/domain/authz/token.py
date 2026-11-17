"""Classificação e adulteração de tokens para o teste "token adulterado" (ADR 0039).

Este módulo só REMOVE ou CORROMPE o que protege o token: nunca assina nada, nunca tenta chave,
nunca troca identidade ou papel (`sub`, `role`...) e nunca testa confusão de algoritmo. A
assinatura com chave fraca vive em `jwt_forge` (ADR 0098). O que sai daqui jamais é um token
válido. As funções são
puras e determinísticas (mesma entrada, mesma saída) e nunca levantam exceção: entrada
malformada vira "token opaco". O valor do token é dado sensível: nenhum texto de erro o cita.
"""

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from typing import Final, Literal

TamperVariant = Literal[
    "stripped_signature",
    "alg_none",
    "altered_claims",
    "scrambled",
    "weak_key",
    "weak_key_expired",
]
"""Nome estável de cada variante de adulteração (campo `variants` do achado)."""

MAX_TOKEN_CHARS: Final = 8192
MIN_OPAQUE_CHARS: Final = 2
JWT_SEGMENTS: Final = 3
ADDED_CLAIM: Final = ("hdast", "1")
"""Reivindicação inofensiva acrescentada: não troca identidade, papel nem validade."""
_B64URL = re.compile(r"[A-Za-z0-9_-]+")
_TOKEN_TEXT = re.compile(r"[\x21-\x7e]+")


@dataclass(frozen=True)
class JwtToken:
    """JWT reconhecido: cabeçalho e conteúdo como objetos e a assinatura como veio.

    Attributes:
        header: Cabeçalho decodificado (sempre com `alg` textual).
        payload: Conteúdo decodificado (objeto JSON).
        signature: Terceiro segmento como veio (pode ser vazio).
    """

    header: dict[str, object] = field(repr=False)
    payload: dict[str, object] = field(repr=False)
    signature: str = field(repr=False)


@dataclass(frozen=True)
class TamperedToken:
    """Uma variante adulterada.

    Attributes:
        variant: Nome estável da variante.
        value: Texto do token adulterado (sensível: nunca gravar nem imprimir).
    """

    variant: TamperVariant
    value: str = field(repr=False)


def b64url_decode(segment: str) -> bytes | None:
    """Decodifica um segmento base64url; `None` se malformado."""
    if not _B64URL.fullmatch(segment) or len(segment) % 4 == 1:
        return None
    try:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (binascii.Error, ValueError):
        return None


def b64url_encode(raw: bytes) -> str:
    """Codifica em base64url sem preenchimento."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _json_object(segment: str) -> dict[str, object] | None:
    raw = b64url_decode(segment)
    if raw is None:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def encode_object(value: dict[str, object]) -> str:
    """Objeto JSON compacto em base64url."""
    text = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return b64url_encode(text.encode("utf-8"))


def classify_token(token: str) -> JwtToken | None:
    """Reconhece um JWT: três segmentos, os dois primeiros objetos JSON em base64url.

    O cabeçalho precisa ter `alg` textual e o token não passa de 8192 caracteres. Todo o resto
    (JWE de cinco segmentos, texto qualquer, chave de API, vazio) é opaco: devolve `None`.
    """
    if not token or len(token) > MAX_TOKEN_CHARS:
        return None
    parts = token.split(".")
    if len(parts) != JWT_SEGMENTS:
        return None
    header, payload = _json_object(parts[0]), _json_object(parts[1])
    if header is None or payload is None or not isinstance(header.get("alg"), str):
        return None
    return JwtToken(header=header, payload=payload, signature=parts[2])


def _jwt_variants(token: str, jwt: JwtToken) -> tuple[TamperedToken, ...]:
    head, body, _ = token.split(".")
    found: list[TamperedToken] = []
    if jwt.signature:
        found.append(TamperedToken("stripped_signature", f"{head}.{body}."))
    if jwt.header["alg"] != "none":
        header = {**jwt.header, "alg": "none"}
        found.append(TamperedToken("alg_none", f"{encode_object(header)}.{body}."))
    claims = {**jwt.payload, ADDED_CLAIM[0]: ADDED_CLAIM[1]}
    found.append(TamperedToken("altered_claims", f"{head}.{encode_object(claims)}.{jwt.signature}"))
    return tuple(item for item in found if item.value != token)


def _scrambled(token: str) -> tuple[TamperedToken, ...]:
    if len(token) < MIN_OPAQUE_CHARS or not _TOKEN_TEXT.fullmatch(token):
        return ()
    value = token[::-1]
    if value == token:
        value = token[1:] + token[0]
    return () if value == token else (TamperedToken("scrambled", value),)


def build_tampered_tokens(token: str, *, allow_jwt: bool = True) -> tuple[TamperedToken, ...]:
    """Variantes adulteradas de um token, em ordem estável.

    JWT gera até três variantes (`stripped_signature`, `alg_none`, `altered_claims`; as que
    não se aplicam ou que dariam o próprio token ficam de fora). Token opaco e chave de API
    (`allow_jwt=False`) geram só `scrambled`: o texto invertido (ou rotacionado, se for
    palíndromo). Texto com menos de 2 caracteres, ou com espaço ou caractere de controle, não
    gera variante. Nenhuma variante é válida.
    """
    jwt = classify_token(token) if allow_jwt else None
    if jwt is not None:
        return _jwt_variants(token, jwt)
    return _scrambled(token)

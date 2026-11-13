"""Entrega do token ao ZAP pelo Replacer: regras, renovação e expiração.

Mecanismo (spike do M0, Q3): uma regra `REQ_HEADER` sobre o cabeçalho de autenticação, com
`url` restrito ao alvo, sobrescreve o cabeçalho aprendido nos ataques. Não existe `setRule`:
renova-se com `addRule` da regra nova e `removeRule` da antiga. Toda regra tem o prefixo
`hdast-` e é removida ao fim.

CSRF por cookie duplicado (Spring `CookieCsrfTokenRepository`): o cabeçalho é um `REQ_HEADER`
comum. O cookie é um `REQ_HEADER_STR` com expressão regular que troca só `NOME=valor` dentro
do cabeçalho `Cookie`. Isto NÃO foi verificado contra o ZAP real: se o cookie não existir na
requisição aprendida, a regra não o acrescenta. Este módulo é puro.
"""

import base64
import json
import re
from datetime import UTC, datetime
from typing import Final, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.urlnorm import default_port
from harness_dast.domain.zap_scope import REPLACER_RULE_PREFIX

MatchType = Literal["REQ_HEADER", "REQ_HEADER_STR"]

_MAX_TOKEN_CHARS: Final = 8192


class ReplacerRule(BaseModel):
    """Regra do Replacer do ZAP.

    Attributes:
        description: Nome da regra (sempre com o prefixo `hdast-`).
        match_type: `REQ_HEADER` (valor do cabeçalho) ou `REQ_HEADER_STR` (texto no cabeçalho).
        match_string: Nome do cabeçalho ou expressão regular.
        regex: Se `match_string` é expressão regular.
        replacement: Valor novo (contém o segredo: nunca é gravado nem logado).
        url: Expressão regular da URL; limita a regra ao alvo.
    """

    model_config = ConfigDict(frozen=True)

    description: str
    match_type: MatchType
    match_string: str
    regex: bool
    replacement: str
    url: str

    def __repr__(self) -> str:
        """Representação sem o valor de substituição (segredo)."""
        return f"ReplacerRule(description={self.description!r}, match_string={self.match_string!r})"


def origin_regex(base_url: str) -> str:
    """Expressão regular que cobre só a origem do ambiente (esquema, host e porta)."""
    parts = urlsplit(base_url)
    scheme = parts.scheme.lower()
    host = parts.hostname or ""
    port = parts.port or default_port(scheme)
    suffix = f"(?::{port})?" if port == default_port(scheme) else f":{port}"
    return f"^{re.escape(scheme)}://{re.escape(host)}{suffix}/.*"


def _escape_replacement(value: str) -> str:
    # O Replacer usa a substituição do Java quando a regra é regex: `$` e `\` são especiais.
    return value.replace("\\", "\\\\").replace("$", r"\$")


def build_token_rules(
    *,
    label: str,
    generation: int,
    auth_headers: tuple[tuple[str, str], ...],
    csrf: CsrfConfig | None,
    csrf_value: str | None,
    url_regex: str,
) -> tuple[ReplacerRule, ...]:
    """Monta as regras de uma geração do token.

    Args:
        label: Apelido da conta, que entra no nome da regra (nomes únicos entre contas).
        generation: Número da geração (1, 2...), que entra no nome da regra.
        auth_headers: Cabeçalhos de autenticação da conta (nome, valor).
        csrf: Configuração de CSRF do perfil, ou `None`.
        csrf_value: Valor atual do cookie de CSRF, ou `None`.
        url_regex: Restrição de URL (`origin_regex`).
    """
    rules = [
        ReplacerRule(
            description=f"{REPLACER_RULE_PREFIX}auth-{label}-{generation}-{index}",
            match_type="REQ_HEADER",
            match_string=name,
            regex=False,
            replacement=value,
            url=url_regex,
        )
        for index, (name, value) in enumerate(auth_headers, start=1)
    ]
    if csrf is not None and csrf_value:
        rules.append(
            ReplacerRule(
                description=f"{REPLACER_RULE_PREFIX}csrf-header-{label}-{generation}",
                match_type="REQ_HEADER",
                match_string=csrf.header_name,
                regex=False,
                replacement=csrf_value,
                url=url_regex,
            )
        )
        cookie = re.escape(csrf.cookie_name)
        rules.append(
            ReplacerRule(
                description=f"{REPLACER_RULE_PREFIX}csrf-cookie-{label}-{generation}",
                match_type="REQ_HEADER_STR",
                match_string=rf"(?<![\w-]){cookie}=[^;\s]*",
                regex=True,
                replacement=_escape_replacement(f"{csrf.cookie_name}={csrf_value}"),
                url=url_regex,
            )
        )
    return tuple(rules)


def jwt_expiry(token: str) -> datetime | None:
    """Instante de expiração (`exp`) de um JWT; `None` se não for JWT ou não tiver `exp`."""
    parts = token.rsplit(" ", 1)[-1].split(".")
    if len(parts) != 3 or len(token) > _MAX_TOKEN_CHARS:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, TypeError):
        return None
    exp = claims.get("exp") if isinstance(claims, dict) else None
    if isinstance(exp, bool) or not isinstance(exp, int | float):
        return None
    try:
        return datetime.fromtimestamp(exp, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def refresh_due(
    *,
    issued_at: datetime,
    now: datetime,
    interval_seconds: int,
    expires_at: datetime | None,
    margin_seconds: int = 30,
) -> bool:
    """Diz se o token entregue ao ZAP deve ser renovado.

    Renova quando a idade passa de `interval_seconds` ou, se o token informa a expiração,
    quando faltam menos de `margin_seconds` para ela (o que vier primeiro).
    """
    if (now - issued_at).total_seconds() >= interval_seconds:
        return True
    return expires_at is not None and (expires_at - now).total_seconds() <= margin_seconds

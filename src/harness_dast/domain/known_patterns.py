"""Notas fixas sobre padrões conhecidos e, em geral, esperados. Módulo puro.

A nota explica POR QUE o padrão costuma ser esperado; ela nunca muda a severidade nem a
confiança propostas pelo ZAP e nunca esconde o achado. A decisão continua sendo da pessoa que
triou: a nota só poupa a explicação de sempre. O texto é nosso, escrito no código, nunca vem do
alvo.
"""

from typing import Final

# Regra 10010 do ZAP: "Cookie No HttpOnly Flag". O ZAP informa o NOME do cookie em `param`.
_COOKIE_NO_HTTPONLY: Final = "10010"
_CSRF_COOKIE_NAMES: Final = frozenset({"xsrf-token", "x-xsrf-token", "csrf-token", "csrftoken"})

_XSRF_NOTE: Final = (
    "Padrão conhecido: o cookie de XSRF/CSRF usa o esquema de duplo envio (double submit): o "
    "JavaScript do front-end precisa LER o cookie para devolvê-lo no cabeçalho "
    "X-XSRF-TOKEN. Por isso ele costuma não ter HttpOnly e isso costuma ser esperado. "
    "Confirme com o time que o cookie de SESSÃO (que não é este) tem HttpOnly. A severidade "
    "continua sendo a proposta pelo ZAP."
)


def expected_pattern_note(plugin_id: str, parameter: str) -> str | None:
    """Devolve a nota de um padrão conhecido, ou `None` quando não há.

    Args:
        plugin_id: Regra do ZAP do achado.
        parameter: Parâmetro do achado (para cookies, o nome do cookie).

    Returns:
        Texto em português explicando por que o padrão costuma ser esperado, ou `None`.
    """
    if plugin_id.strip() == _COOKIE_NO_HTTPONLY and parameter.strip().lower() in _CSRF_COOKIE_NAMES:
        return _XSRF_NOTE
    return None

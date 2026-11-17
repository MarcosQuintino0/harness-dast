"""Regras alpha e beta que a imagem do ZAP do harness traz além das estáveis (ADR 0103).

A imagem `hdast/zap` acrescenta ao ZAP 2.17.0 os complementos `ascanrulesBeta` e
`ascanrulesAlpha` em versão fixa. Eles trazem regras que nascem LIGADAS no ZAP; por isso o
harness decide, aqui, quais ficam ligadas: só as poucas úteis para API, e só com
`extra_checks.experimental_rules` (que só a carta liga). Todas as demais ficam desligadas na
política, sempre. Os alertas das regras do catálogo saem marcados como experimentais. Este
módulo é puro.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

Quality = Literal["alpha", "beta"]


class ExperimentalRule(BaseModel):
    """Regra de varredura ativa que só existe nos complementos alpha ou beta da imagem.

    Attributes:
        plugin_id: Identificador da regra no ZAP.
        name: Nome da regra.
        quality: Estado do complemento que a traz (`alpha` ou `beta`).
        selected: Se o harness a liga quando `extra_checks.experimental_rules` está ligada.
        needs_oast: Se a regra só vale com retorno fora de banda (`scan.oast`).
    """

    model_config = ConfigDict(frozen=True)

    plugin_id: int
    name: str
    quality: Quality
    selected: bool = False
    needs_oast: bool = False


EXPERIMENTAL_RULES: Final[tuple[ExperimentalRule, ...]] = (
    ExperimentalRule(
        plugin_id=40033, name="NoSQL Injection - MongoDB", quality="beta", selected=True
    ),
    ExperimentalRule(
        plugin_id=90039,
        name="NoSQL Injection - MongoDB (Time Based)",
        quality="beta",
        selected=True,
    ),
    ExperimentalRule(
        plugin_id=40046,
        name="Server Side Request Forgery",
        quality="beta",
        selected=True,
        needs_oast=True,
    ),
    ExperimentalRule(plugin_id=41, name="Source Code Disclosure - Git", quality="beta"),
    ExperimentalRule(plugin_id=42, name="Source Code Disclosure - SVN", quality="beta"),
    ExperimentalRule(plugin_id=43, name="Source Code Disclosure - File Inclusion", quality="beta"),
    ExperimentalRule(plugin_id=10051, name="Relative Path Confusion", quality="beta"),
    ExperimentalRule(plugin_id=10095, name="Backup File Disclosure", quality="beta"),
    ExperimentalRule(plugin_id=10107, name="Httpoxy - Proxy Header Misuse", quality="beta"),
    ExperimentalRule(plugin_id=20012, name="Anti-CSRF Tokens Check", quality="beta"),
    ExperimentalRule(plugin_id=20014, name="HTTP Parameter Pollution", quality="beta"),
    ExperimentalRule(plugin_id=20016, name="Cross-Domain Misconfiguration", quality="beta"),
    ExperimentalRule(plugin_id=30003, name="Integer Overflow Error", quality="beta"),
    ExperimentalRule(plugin_id=40013, name="Session Fixation", quality="beta"),
    ExperimentalRule(plugin_id=40015, name="LDAP Injection", quality="alpha"),
    ExperimentalRule(plugin_id=40023, name="Possible Username Enumeration", quality="beta"),
    ExperimentalRule(plugin_id=40025, name="Proxy Disclosure", quality="beta"),
    ExperimentalRule(plugin_id=40031, name="Out of Band XSS", quality="beta"),
    ExperimentalRule(plugin_id=40038, name="Bypassing 403", quality="beta"),
    ExperimentalRule(plugin_id=40039, name="Web Cache Deception", quality="alpha"),
    ExperimentalRule(plugin_id=40040, name="CORS Header", quality="beta"),
    ExperimentalRule(plugin_id=40047, name="Text4shell (CVE-2022-42889)", quality="beta"),
    ExperimentalRule(plugin_id=90025, name="Expression Language Injection", quality="beta"),
    ExperimentalRule(plugin_id=90027, name="Cookie Slack Detector", quality="beta"),
    ExperimentalRule(plugin_id=90028, name="Insecure HTTP Method", quality="beta"),
    ExperimentalRule(plugin_id=100044, name="Suspicious Input Transformation", quality="alpha"),
)
"""Todas as regras que `ascanrulesBeta` 64 e `ascanrulesAlpha` 54 acrescentam à imagem estável
(26 regras, medidas em `ascan/view/scanners` da imagem; ADR 0103). Mudar a versão dos
complementos exige reler esta lista."""

REASON_NOT_SELECTED: Final = (
    "Regra alpha ou beta da imagem do harness que não está na lista selecionada: fica desligada "
    "(ADR 0103)."
)
REASON_NEEDS_PERMISSION: Final = (
    "Regra experimental selecionada: só liga com extra_checks.experimental_rules, que só a carta "
    "liga (ADR 0103)."
)

_BY_ID: Final = {rule.plugin_id: rule for rule in EXPERIMENTAL_RULES}


def experimental_rule(plugin_id: int | str) -> ExperimentalRule | None:
    """Regra do catálogo pelo identificador do ZAP (texto ou número), ou `None`."""
    try:
        return _BY_ID.get(int(plugin_id))
    except (TypeError, ValueError):
        return None


def is_experimental_plugin(plugin_id: str) -> bool:
    """Se o alerta vem de uma regra alpha ou beta do catálogo (vira achado experimental)."""
    return experimental_rule(plugin_id) is not None


def enabled_experimental_ids(*, experimental: bool, oast: bool) -> tuple[int, ...]:
    """Regras ligadas: nenhuma sem `experimental`; as que dependem de retorno só com `oast`."""
    if not experimental:
        return ()
    return tuple(
        rule.plugin_id
        for rule in EXPERIMENTAL_RULES
        if rule.selected and (oast or not rule.needs_oast)
    )

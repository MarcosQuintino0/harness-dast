"""Ritmo e autorizações adicionais lidos da carta (ADRs 0096 e 0122).

Todas nascem desligadas. `attack.pacing` aceita `legacy` ou `proxy`, de `source: carta` ou
`pessoa`, sem frase. Cada booleano `true` exige `source: carta` e a frase de origem.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.extra_checks_config import NUCLEI_FIELDS
from harness_dast.domain.letter import Answer, AttackSection
from harness_dast.domain.letter_collect import (
    ATTACK_FLAG_NEEDS_LETTER,
    INVALID_VALUE,
    Collector,
)

Pacing = Literal["legacy", "proxy"]
FLAG_FIELDS: Final = (
    "inject_headers",
    "oast",
    "allow_rate_tests",
    "experimental_rules",
    "inventory",
    *NUCLEI_FIELDS,
)
"""Nomes dos booleanos que exigem frase da carta."""


class AttackFlags(BaseModel):
    """Resultado da leitura das autorizações adicionais.

    Attributes:
        pacing: Ritmo pedido; `legacy` quando ausente.
        inject_headers: Injeção em cabeçalhos e cookies autorizada -> `scan.inject_headers`.
        oast: Retorno fora de banda autorizado -> `scan.oast`.
        allow_rate_tests: Testes de limite autorizados -> `extra_checks.allow_rate_tests`.
        experimental_rules: Regras experimentais autorizadas -> `extra_checks.experimental_rules`.
        inventory: Inventário autorizado -> `extra_checks.inventory`.
        nuclei: Autorização declarada para o Nuclei.
        nuclei_login: Autorização declarada para login com o Nuclei.
        nuclei_wide_paths: Autorização declarada para caminhos fora do Swagger com o Nuclei.
    """

    model_config = ConfigDict(frozen=True)

    pacing: Pacing = "legacy"
    inject_headers: bool = False
    oast: bool = False
    allow_rate_tests: bool = False
    experimental_rules: bool = False
    inventory: bool = False
    nuclei: bool = False
    nuclei_login: bool = False
    nuclei_wide_paths: bool = False


def _read_pacing(c: Collector, answer: Answer | None) -> Pacing:
    value = c.take("attack.pacing", answer, required=False)
    if value is None:
        return "legacy"
    if value == "legacy" or value == "proxy":
        return value
    c.add("attack.pacing", INVALID_VALUE, "Responda legacy ou proxy; na dúvida, desconhecido.")
    return "legacy"


def _read_flag(c: Collector, name: str, answer: Answer | None) -> bool:
    field = f"attack.{name}"
    value = c.take(field, answer, required=False)
    if value is None or value is False:
        return False
    if value is not True:
        c.add(field, INVALID_VALUE, "Responda true (sim) ou false (não).")
        return False
    from_letter = answer is not None and answer.source == "carta"
    quote = answer.quote if answer is not None else None
    if not from_letter or not (quote or "").strip():
        c.add(
            field,
            ATTACK_FLAG_NEEDS_LETTER,
            "Esta capacidade muda o tráfego ou o relato e só vale se a carta assinada a "
            "autorizar: use source: carta e copie em quote a frase da carta. O agente nunca a "
            "liga por conta própria; na dúvida, responda desconhecido (vale false).",
        )
        return False
    return True


def read_attack_flags(c: Collector, attack: AttackSection) -> AttackFlags:
    """Lê `attack.pacing` e as autorizações booleanas, todas desligadas por padrão.

    Ausente, nulo e `desconhecido` valem o padrão sem pendência. Valor de tipo errado ou booleano
    `true` sem origem `carta` e frase vira pendência e a chave fica desligada.
    """
    flags = {name: _read_flag(c, name, getattr(attack, name)) for name in FLAG_FIELDS}
    return AttackFlags(pacing=_read_pacing(c, attack.pacing), **flags)

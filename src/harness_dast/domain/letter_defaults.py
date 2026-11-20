"""Padrões mínimos da CLI para a resposta "não sei" da carta (ADR 0114).

Só quatro campos têm um valor seguro e óbvio: o mais estreito que o domínio aceita. Quando a
pessoa responde `desconhecido` num deles, a CLI usa o valor desta tabela e avisa; o agente nunca
escolhe o valor. Todo o resto continua como estava: os portões (ambiente, dados, autorização,
dono, endereço, escopo, referência, validade, janelas, tipo de login, contas e `deny_paths`)
param o cadastro com "não sei", e o modo do caminho, a força e o bloco `attack` já valem o
mais estreito quando ausentes. Este módulo é puro.
"""

import re
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, ConfigDict

NOTE_PREFIX: Final = "# Padrão mínimo da CLI: "
_NOTE = re.compile(r"^# Padrão mínimo da CLI: (?P<field>[\w.]+) = (?P<value>\S+) ")


class MinimumDefault(BaseModel):
    """Valor fixo da CLI para um campo respondido como "não sei".

    Attributes:
        field: Caminho do campo na carta (`limits.requests_per_second`).
        value: Valor aplicado; o mais estreito que o domínio aceita.
        reason: Por que este valor é o seguro.
    """

    model_config = ConfigDict(frozen=True)

    field: str
    value: int
    reason: str


MINIMUM_DEFAULTS: Final[Mapping[str, MinimumDefault]] = MappingProxyType(
    {
        default.field: default
        for default in (
            MinimumDefault(
                field="limits.requests_per_second",
                value=1,
                reason="uma requisição por segundo é a carga mínima útil para a varredura",
            ),
            MinimumDefault(
                field="limits.max_duration_minutes",
                value=30,
                reason="meia hora limita o tempo em que o alvo fica sob teste",
            ),
            MinimumDefault(
                field="limits.zap_threads_per_host",
                value=1,
                reason="uma conexão simultânea por host é o menor paralelismo do varredor",
            ),
            MinimumDefault(
                field="auth.login_max_per_minute",
                value=1,
                reason="um login por minuto é o menor valor que o perfil aceita (ge=1)",
            ),
        )
    }
)
"""Tabela única dos padrões mínimos, por campo da carta."""


def default_notes(defaults: Iterable[MinimumDefault]) -> str:
    """Linhas de comentário para o topo do `target.yml`, uma por padrão aplicado.

    Servem para o `hdast setup` repetir o aviso no resumo da aprovação. Comentário não entra
    na impressão digital dos blocos de proteção.
    """
    return "".join(
        f"{NOTE_PREFIX}{item.field} = {item.value} (resposta 'não sei' na carta)\n"
        for item in defaults
    )


def read_default_notes(profile_text: str) -> tuple[str, ...]:
    """Lê de volta os padrões aplicados (`campo = valor`) do texto de um `target.yml`."""
    found: list[str] = []
    for line in profile_text.splitlines():
        match = _NOTE.match(line)
        if match is not None:
            found.append(f"{match['field']} = {match['value']}")
    return tuple(found)

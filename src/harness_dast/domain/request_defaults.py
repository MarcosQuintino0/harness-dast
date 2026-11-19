"""Tabela de padrões do modo pedido mínimo da carta (ADR 0120).

Na carta `kind: request`, a pessoa responde só quatro perguntas (portões e dono, endereço,
força, gravação no ambiente). A CLI completa o resto com os valores desta tabela, e cada um
vai escrito de forma explícita no `target.yml`, com aviso e comentário no cabeçalho: o que o
padrão ligou entra na impressão digital e só vale depois da aprovação humana. Os valores
padrão do modelo do perfil NÃO mudam. Resposta explícita da pessoa vence o padrão, inclusive
para desligar; a única exceção é `scope.deny_paths`, que a pessoa só soma à sugestão.

Os valores de carga (`limits.*`) são pontos de partida a calibrar no laboratório (ADR 0120,
fase D). Este módulo é puro.
"""

import re
from collections.abc import Iterable, Mapping
from datetime import date
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, ConfigDict

NOTE_PREFIX: Final = "# Padrão do pedido mínimo: "
SETUP_LABEL: Final = "pedido mínimo: "
"""Prefixo que o `hdast setup` usa para separar estes padrões dos padrões mínimos do ADR 0114."""
DEFAULT_TIMEZONE: Final = "America/Sao_Paulo"
"""Fuso das janelas quando a máquina não informa um nome IANA válido (documentado no ADR 0120)."""
VALIDITY_DAYS: Final = 30
DEFAULT_METHODS: Final = ("GET", "POST", "PUT", "PATCH")
DELETE_METHOD: Final = "DELETE"
FULL_WINDOW: Final = "seg-dom 00:00-24:00"
OUTCOME_CLASSES: Final = (
    "not_found",
    "validation_error",
    "conflict",
    "logical_failure",
    "client_error",
)
_NOTE = re.compile(rf"^{re.escape(NOTE_PREFIX)}(?P<field>[\w.\[\]]+) = (?P<value>.+?) \| ")

type DefaultValue = str | int | bool | date | tuple[str, ...]


class RequestDefault(BaseModel):
    """Valor que a CLI aplicou a um campo que a pessoa não respondeu.

    Attributes:
        field: Caminho do campo na carta (`limits.requests_per_second`).
        value: Valor aplicado.
        reason: Por que este valor é o escolhido.
    """

    model_config = ConfigDict(frozen=True)

    field: str
    value: DefaultValue
    reason: str

    @property
    def shown(self) -> str:
        """O valor como texto de uma linha (avisos, cabeçalho e resumo do `setup`)."""
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        if isinstance(self.value, date):
            return self.value.isoformat()
        if isinstance(self.value, tuple):
            return ", ".join(self.value)
        return str(self.value)

    @property
    def answer_value(self) -> object:
        """O valor na forma que o leitor da carta espera (lista no lugar de tupla)."""
        return list(self.value) if isinstance(self.value, tuple) else self.value


def _static(field: str, value: DefaultValue, reason: str) -> tuple[str, RequestDefault]:
    return field, RequestDefault(field=field, value=value, reason=reason)


REQUEST_DEFAULTS: Final[Mapping[str, RequestDefault]] = MappingProxyType(
    dict(
        (
            _static(
                "environment.name",
                "teste",
                "o pedido mínimo não pergunta o nome do ambiente; é só um rótulo",
            ),
            _static(
                "scope.path_mode",
                "strict",
                "o modo amplo só vale com a frase de uma carta assinada (ADR 0026)",
            ),
            _static(
                "limits.requests_per_second",
                10,
                "carga moderada para um ambiente de teste compartilhado; a calibrar no laboratório",
            ),
            _static(
                "limits.max_duration_minutes",
                30,
                "meia hora limita o tempo em que o alvo fica sob teste",
            ),
            _static(
                "limits.zap_threads_per_host",
                2,
                "paralelismo baixo do varredor; a calibrar no laboratório",
            ),
            _static(
                "auth.login_max_per_minute",
                5,
                "poucos logins por minuto, para não bloquear as contas de teste",
            ),
            _static(
                "scan.strength",
                "LOW",
                "a força mais leve; a pessoa escolhe MEDIUM ou HIGH na pergunta 3",
            ),
            _static(
                "scan.include_outcomes",
                OUTCOME_CLASSES,
                "ataca também as operações que o probe viu recusadas, para cobrir mais da API",
            ),
            _static(
                "scan.inject_headers",
                True,
                "injeta também em cabeçalhos e cookies, onde falhas comuns se escondem",
            ),
            _static(
                "scan.oast",
                True,
                "usa o retorno fora de banda; sem o serviço de retorno a varredura segue sem OAST",
            ),
            _static(
                "extra_checks.allow_rate_tests",
                True,
                "testa o limite de consumo com poucos pedidos e teto fixo no código",
            ),
            _static(
                "extra_checks.experimental_rules",
                True,
                "inclui as regras experimentais do ZAP, com os achados marcados como tal",
            ),
            _static(
                "extra_checks.inventory",
                True,
                "inventaria versões irmãs e documentação exposta, só dentro do escopo",
            ),
            _static(
                "scan.pacing",
                "proxy",
                "o ritmo da varredura passa pelo proxy de escopo e respeita os limites",
            ),
        )
    )
)
"""Padrões fixos, por campo da carta. Os que dependem do pedido (`scope.allow`,
`scope.deny_paths`, `authorization.*`) são montados em `request_letter`."""


def request_notes(defaults: Iterable[RequestDefault]) -> str:
    """Linhas de comentário para o topo do `target.yml`, uma por padrão aplicado.

    Servem para o `hdast setup` repetir o aviso no resumo da aprovação. Comentário não entra
    na impressão digital dos blocos de proteção.
    """
    return "".join(
        f"{NOTE_PREFIX}{item.field} = {item.shown} | {item.reason}\n" for item in defaults
    )


def read_request_notes(profile_text: str) -> tuple[str, ...]:
    """Lê de volta os padrões aplicados (`campo = valor`) do texto de um `target.yml`."""
    found: list[str] = []
    for line in profile_text.splitlines():
        match = _NOTE.match(line)
        if match is not None:
            found.append(f"{match['field']} = {match['value']}")
    return tuple(found)

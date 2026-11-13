"""Identificador de execução e limites de carga.

Este módulo é puro: o instante e a parte aleatória do `RunId` entram por argumento, e os
limites são números validados, sem relógio nem I/O.
"""

import re
from datetime import UTC, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from harness_dast.domain.window import ensure_aware

SLUG_PATTERN = r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?"
"""Forma de um slug de produto: minúsculas, dígitos e hífen, de 1 a 40 caracteres."""

# Tetos absolutos. Existem para que um perfil errado ou inflado (ou um agente que "sugira"
# números altos) nunca transforme o harness num teste de carga contra um ambiente
# compartilhado: o perfil e as sobrescritas só podem escolher valores até estes tetos.
MAX_REQUESTS_PER_SECOND = 50.0
MAX_DURATION_MINUTES = 480  # 8 h: cabe numa janela noturna típica sem deixar execução aberta
MAX_ZAP_THREADS_PER_HOST = 8

_RUN_ID = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z-"
    rf"{SLUG_PATTERN}-[0-9a-f]{{4,8}}"
)
_SLUG = re.compile(SLUG_PATTERN)
_SUFFIX = re.compile(r"[0-9a-f]{4,8}")
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%SZ"


class RunId(BaseModel):
    """Identificador de uma execução: ordenável, seguro como nome de pasta e único.

    Formato: `AAAA-MM-DDTHH-MM-SSZ-<produto>-<sufixo hex>`, por exemplo
    `2026-11-12T21-04-11Z-agenda-7f3a`. Ordenar os textos ordena por instante (UTC).
    Só há letras minúsculas, dígitos e hífen: não existe barra, barra invertida, ponto nem
    dois-pontos, então o valor nunca vira travessia de diretório nem nome inválido no Windows.

    Attributes:
        value: O identificador completo.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str = Field(max_length=100)

    @model_validator(mode="after")
    def validate_format(self) -> Self:
        """Confere o formato e que o carimbo é uma data e hora reais."""
        if not _RUN_ID.fullmatch(self.value):
            raise ValueError("identificador de execução fora do formato esperado")
        try:
            datetime.strptime(self.value[:20], _TIMESTAMP_FORMAT)
        except ValueError:
            raise ValueError("carimbo de data e hora inválido no identificador") from None
        return self

    @classmethod
    def create(cls, *, started_at: datetime, product: str, suffix: str) -> Self:
        """Monta o identificador a partir de valores injetados.

        Args:
            started_at: Instante de início, com fuso; é convertido para UTC.
            product: Slug do produto (`[a-z0-9-]`, 1 a 40 caracteres).
            suffix: 4 a 8 dígitos hexadecimais minúsculos, vindos de uma fonte aleatória
                injetada pelo chamador (o domínio não sorteia nada).

        Raises:
            ConfigError: Se `started_at` não tiver fuso.
            ValueError: Se `product` ou `suffix` estiverem fora do formato.
        """
        ensure_aware(started_at)
        if not _SLUG.fullmatch(product) or not _SUFFIX.fullmatch(suffix):
            raise ValueError("produto ou sufixo fora do formato do identificador de execução")
        stamp = started_at.astimezone(UTC).strftime(_TIMESTAMP_FORMAT)
        return cls(value=f"{stamp}-{product}-{suffix}")

    def __str__(self) -> str:
        """Devolve o identificador como texto."""
        return self.value

    def __lt__(self, other: "RunId") -> bool:
        """Ordena por instante de início (o carimbo vem primeiro no texto)."""
        return self.value < other.value


class RunLimits(BaseModel):
    """Limites de carga de uma execução; sempre fixados, nunca "sem limite".

    Attributes:
        requests_per_second: Taxa máxima de requisições, maior que 0 e até
            `MAX_REQUESTS_PER_SECOND`.
        max_duration_minutes: Duração máxima, de 1 até `MAX_DURATION_MINUTES`.
        zap_threads_per_host: Threads do ZAP por host, de 1 até `MAX_ZAP_THREADS_PER_HOST`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    requests_per_second: float = Field(
        gt=0, le=MAX_REQUESTS_PER_SECOND, allow_inf_nan=False, strict=True
    )
    max_duration_minutes: StrictInt = Field(ge=1, le=MAX_DURATION_MINUTES)
    zap_threads_per_host: StrictInt = Field(ge=1, le=MAX_ZAP_THREADS_PER_HOST)

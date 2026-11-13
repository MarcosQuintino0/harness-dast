"""Janelas de execução e validade da autorização.

Tudo aqui recebe o instante (`now`) como argumento: o domínio nunca lê o relógio. Um `now`
sem fuso (naive) é recusado, porque não há como saber se a janela está aberta.

Forma compacta usada no perfil:  `<dias> <HH:MM>-<HH:MM> <fuso IANA>`

- `<dias>`: lista separada por vírgula de dias (`seg ter qua qui sex sab dom`) ou faixas
  `dia-dia` (`seg-sex`). Uma faixa pode dar a volta na semana (`sex-seg` = sex, sab, dom, seg).
- Horas em 24 h, `00:00` a `24:00`. O início é inclusivo e o fim é exclusivo. Início igual ao
  fim é recusado (seria ambíguo: vazio ou o dia todo); para o dia todo use `00:00-24:00`.
- Fim menor que o início cruza a meia-noite: os dias listados são os dias em que a janela
  COMEÇA. `seg-sex 20:00-06:00` está aberta na sexta às 03:00 de sábado, mas fechada
  na segunda às 03:00 (essa madrugada pertence ao domingo, que não está na lista).
- O relógio de parede local do fuso é o que vale: em mudança de horário de verão a janela
  continua indo de "20:00 locais" a "06:00 locais", mesmo que dure uma hora a mais ou a menos.
"""

import re
from datetime import UTC, date, datetime
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harness_dast.domain.errors import ConfigError, ScopeViolation

_DAY_NAMES = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
_MINUTES_PER_DAY = 24 * 60
_MINUTES_PER_WEEK = 7 * _MINUTES_PER_DAY
_COMPACT = re.compile(r"(\S+) ([0-9]{2}):([0-9]{2})-([0-9]{2}):([0-9]{2}) (\S+)")
_ZONE_KEY = re.compile(r"[A-Za-z0-9_+\-]+(?:/[A-Za-z0-9_+\-]+)*")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_COMPACT_HINT = 'Use o formato "seg-sex 20:00-06:00 America/Sao_Paulo".'


def ensure_aware(now: datetime) -> None:
    """Recusa `datetime` sem fuso.

    Raises:
        ConfigError: Se `now` for naive; o chamador deve passar um instante com fuso.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ConfigError(
            "O instante atual veio sem fuso horário; não dá para saber se a janela está aberta.",
            hint="Passe um datetime com fuso (ex.: datetime.now(UTC)).",
        )


class ExecutionWindow(BaseModel):
    """Janela semanal em que a execução é permitida (ver as regras no docstring do módulo).

    Attributes:
        days: Dias de INÍCIO da janela, 0 = segunda ... 6 = domingo.
        start_minute: Minuto do dia em que abre (0 a 1439), inclusivo.
        end_minute: Minuto do dia em que fecha (1 a 1440), exclusivo; menor que o início
            significa que a janela cruza a meia-noite.
        timezone: Nome IANA do fuso (ex.: `America/Sao_Paulo`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    days: frozenset[int] = Field(min_length=1)
    start_minute: int = Field(ge=0, le=_MINUTES_PER_DAY - 1)
    end_minute: int = Field(ge=1, le=_MINUTES_PER_DAY)
    timezone: str

    @field_validator("days")
    @classmethod
    def validate_days(cls, value: frozenset[int]) -> frozenset[int]:
        """Aceita só dias de 0 a 6."""
        if not all(0 <= day <= 6 for day in value):
            raise ValueError("dia da semana fora de 0-6")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Confere que o fuso existe no banco IANA."""
        _load_zone(value)
        return value

    @model_validator(mode="after")
    def validate_start_differs_from_end(self) -> Self:
        """Recusa início igual ao fim, por qualquer caminho de construção.

        Segurança: sem esta regra, `start == end` virava "o dia todo" em `is_open`
        (`or _MINUTES_PER_DAY`), ampliando a janela autorizada em silêncio. O dia todo
        se escreve `00:00-24:00`.
        """
        if self.start_minute == self.end_minute:
            raise ValueError("início igual ao fim é ambíguo; para o dia todo use 00:00-24:00")
        return self

    @classmethod
    def parse(cls, text: str) -> "ExecutionWindow":
        """Interpreta a forma compacta, por exemplo `seg-sex 20:00-06:00 America/Sao_Paulo`.

        Raises:
            ConfigError: Se o texto não seguir a gramática do módulo, tiver hora inválida,
                início igual ao fim ou fuso desconhecido. A mensagem diz qual parte falhou.
        """
        match = _COMPACT.fullmatch(text.strip())
        if match is None:
            raise ConfigError("Janela de execução fora do formato esperado.", hint=_COMPACT_HINT)
        days_text, sh, sm, eh, em, zone = match.groups()
        start = _to_minutes(sh, sm, allow_24=False)
        end = _to_minutes(eh, em, allow_24=True)
        if start == end:
            raise ConfigError(
                "Janela com início igual ao fim é ambígua.",
                hint="Para o dia todo use 00:00-24:00.",
            )
        try:
            return cls(
                days=_parse_days(days_text),
                start_minute=start,
                end_minute=end,
                timezone=zone,
            )
        except ValueError:
            raise ConfigError(
                "Fuso horário desconhecido na janela de execução.",
                hint="Use um nome IANA, como America/Sao_Paulo.",
            ) from None

    def is_open(self, now: datetime) -> bool:
        """Diz se a janela está aberta no instante `now`.

        Raises:
            ConfigError: Se `now` não tiver fuso.
        """
        ensure_aware(now)
        local = now.astimezone(_load_zone(self.timezone))
        minute_of_week = local.weekday() * _MINUTES_PER_DAY + local.hour * 60 + local.minute
        duration = (self.end_minute - self.start_minute) % _MINUTES_PER_DAY or _MINUTES_PER_DAY
        return any(
            (minute_of_week - day * _MINUTES_PER_DAY - self.start_minute) % _MINUTES_PER_WEEK
            < duration
            for day in self.days
        )


def _load_zone(key: str) -> ZoneInfo:
    # A expressão regular barra caminhos ('..', '/etc/...') antes de tocar o disco.
    if not _ZONE_KEY.fullmatch(key):
        raise ValueError("fuso horário com formato inválido")
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError("fuso horário desconhecido") from None


def _to_minutes(hours: str, minutes: str, *, allow_24: bool) -> int:
    h, m = int(hours), int(minutes)
    if m > 59 or h > 24 or (h == 24 and (m != 0 or not allow_24)):
        raise ConfigError(
            "Hora inválida na janela de execução.",
            hint="Use HH:MM de 00:00 a 23:59 para o início e até 24:00 para o fim.",
        )
    return h * 60 + m


def _parse_days(text: str) -> frozenset[int]:
    days: set[int] = set()
    for part in text.lower().split(","):
        first, dash, last = part.partition("-")
        start = _day_index(first)
        end = _day_index(last) if dash else start
        # Faixa que dá a volta (sex-seg) percorre a semana circularmente.
        days.update((start + offset) % 7 for offset in range((end - start) % 7 + 1))
    return frozenset(days)


def _day_index(name: str) -> int:
    if name not in _DAY_NAMES:
        raise ConfigError(
            "Dia da semana desconhecido na janela de execução.",
            hint="Use seg, ter, qua, qui, sex, sab ou dom (ex.: seg-sex).",
        )
    return _DAY_NAMES.index(name)


def ensure_any_window_open(windows: tuple[ExecutionWindow, ...], now: datetime) -> None:
    """Garante que ao menos uma janela está aberta em `now`; sem janelas, recusa.

    Raises:
        ScopeViolation: Se nenhuma janela estiver aberta (ou se a lista for vazia).
        ConfigError: Se `now` não tiver fuso.
    """
    ensure_aware(now)
    if not any(window.is_open(now) for window in windows):
        raise ScopeViolation(
            "A janela de execução autorizada está fechada.",
            hint="Execute dentro de scope.windows ou peça ao dono do produto outra janela.",
        )


class Authorization(BaseModel):
    """Autorização formal do teste.

    Attributes:
        reference: Identificador do documento de autorização (ex.: número do chamado).
        valid_until: Último dia de validade, inclusive, contado em UTC. Contar em UTC
            pode encerrar até algumas horas antes do fim do dia local (fuso a oeste de
            Greenwich); o erro é para o lado seguro.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: str = Field(min_length=1, max_length=200)
    valid_until: date

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        """Recusa referência em branco ou com caracteres de controle."""
        if not value.strip() or not value.isprintable():
            raise ValueError("referência de autorização vazia ou com caractere não imprimível")
        return value

    @field_validator("valid_until", mode="before")
    @classmethod
    def reject_non_date(cls, value: object) -> object:
        """Aceita só `date` ou texto AAAA-MM-DD; recusa data e hora, texto com hora e inteiros.

        Segurança: data e hora teriam fuso ambíguo, e um inteiro seria lido como timestamp
        (o pydantic aceitaria `1699920000` como data) sem que o autor perceba.
        """
        is_plain_date = isinstance(value, date) and not isinstance(value, datetime)
        if is_plain_date or (isinstance(value, str) and _ISO_DATE.fullmatch(value)):
            return value
        # O pydantic só converte ValueError em erro de validação; TypeError escaparia.
        raise ValueError("use apenas a data, no formato AAAA-MM-DD")

    def ensure_valid(self, now: datetime) -> None:
        """Garante que a autorização ainda vale em `now`.

        Raises:
            ScopeViolation: Se a autorização tiver expirado.
            ConfigError: Se `now` não tiver fuso.
        """
        ensure_aware(now)
        if now.astimezone(UTC).date() > self.valid_until:
            raise ScopeViolation(
                f"A autorização {self.reference} expirou em {self.valid_until.isoformat()}.",
                hint="Obtenha nova autorização formal e atualize scope.authorization.",
            )

"""Formatos do painel da execução: número, data, duração e as palavras de estado. Módulo puro.

Segue `docs/design/execution-panel/system/formats.html`: milhar com ponto (16.854), tokens como
"151 mil" e "1,2 mi", duração em segundos, minutos ou horas, "X de Y" no lugar de porcentagem
e, quando falta o dado, traço com a palavra, nunca zero. As palavras de estado são uma lista
fechada: este módulo é o único lugar onde elas são escritas. Nenhuma função aqui lê relógio nem
fuso do computador: quem monta a visão já entrega as datas no fuso certo.
"""

from datetime import date, datetime
from typing import Final, Literal

NO_DATA: Final = "—"
NOT_MEASURED: Final = "— não medido"

RunStateKind = Literal["finished", "partial", "error"]
FunctionStateKind = Literal["tested", "severe", "failed", "forbidden", "not_tried"]

RUN_STATE_WORDS: Final[dict[str, str]] = {
    "live": "ao vivo",
    "finished": "terminou",
    "partial": "parou no meio",
    "error": "erro",
}
"""Estado do teste inteiro (lista fechada do desenho)."""

FUNCTION_STATE_WORDS: Final[dict[str, str]] = {
    "tested": "atacada",
    "severe": "com falha grave",
    "failed": "não testada",
    "not_tried": "não testada",
    "forbidden": "proibida pela carta",
}
"""Estado de uma função; o `reason` diz por que `failed` e `not_tried` são "não testada"."""

CONFIDENCE_WORDS: Final = ("a confirmar", "prova forte", "confirmada")
"""Degraus do medidor de confiança, do 1 ao 3 (são degraus, não nota)."""

STAGE_WORDS: Final[dict[str, str]] = {
    "done": "feita",
    "cut": "parou no meio",
    "skipped": "não rodou",
    "pending": "não rodou",
}
"""Estado de uma etapa. `não rodou` é a única palavra fora da lista do desenho: o desenho pede
as etapas depois do corte em cinza, e "a seguir" seria falso num teste que já acabou."""

_NUMBER_WORDS: Final = ("zero", "uma", "duas", "três", "quatro", "cinco", "seis", "sete", "oito")
_TOKEN_THOUSAND: Final = 1_000
_MILLION: Final = 1_000_000
_SECONDS_PER_MINUTE: Final = 60
_MINUTES_PER_HOUR: Final = 60


def fmt_count(value: int) -> str:
    """Inteiro com milhar em ponto: `16854` vira `16.854`."""
    return f"{value:,}".replace(",", ".")


def fmt_tokens(value: int | None) -> str:
    """Tokens: abaixo de mil, inteiro; até 999.999, "mil"; acima, "mi" com uma casa."""
    if value is None:
        return NOT_MEASURED
    if value < _TOKEN_THOUSAND:
        return str(value)
    thousands = round(value / _TOKEN_THOUSAND)
    if thousands < _TOKEN_THOUSAND:
        return f"{thousands} mil"
    return f"{value / _MILLION:.1f}".replace(".", ",") + " mi"


def fmt_duration(seconds: float | None) -> str:
    """Duração: menos de 1 min em segundos; até 59 min em minutos; depois horas e minutos."""
    if seconds is None:
        return NOT_MEASURED
    if seconds < _SECONDS_PER_MINUTE:
        return f"{round(max(seconds, 0))} s"
    minutes = round(seconds / _SECONDS_PER_MINUTE)
    if minutes < _MINUTES_PER_HOUR:
        return f"{minutes} min"
    return f"{minutes // _MINUTES_PER_HOUR} h {minutes % _MINUTES_PER_HOUR:02d}"


def fmt_date(moment: date | datetime | None) -> str:
    """Data como `13/11/2026`; sem dado, o traço."""
    return NO_DATA if moment is None else moment.strftime("%d/%m/%Y")


def fmt_datetime(moment: datetime | None) -> str:
    """Data e hora como `13/11/2026 · 20:08` (no fuso que o `datetime` já traz)."""
    return NO_DATA if moment is None else moment.strftime("%d/%m/%Y · %H:%M")


def fmt_clock(moment: datetime | None) -> str:
    """Hora de comando como `20:16:20`."""
    return NO_DATA if moment is None else moment.strftime("%H:%M:%S")


def x_of_y(part: int, whole: int) -> str:
    """Parte de um todo como `26 de 30`, nunca só porcentagem."""
    return f"{fmt_count(part)} de {fmt_count(whole)}"


def count_word(value: int) -> str:
    """Número feminino por extenso até oito ("duas"); acima disso, o algarismo."""
    return _NUMBER_WORDS[value] if 0 <= value < len(_NUMBER_WORDS) else fmt_count(value)


def plural(value: int, one: str, many: str) -> str:
    """`1 falha`, `2 falhas`: a palavra no singular só para o número 1."""
    return f"{fmt_count(value)} {one if value == 1 else many}"


def capitalize_first(text: str) -> str:
    """Põe só a primeira letra em maiúscula (o resto do texto fica como está)."""
    return text[:1].upper() + text[1:]


def product_title(slug: str) -> str:
    """Nome para mostrar de um produto a partir do slug (`clinica-piloto` vira `Clinica Piloto`).

    O perfil só guarda o slug, sem acento; o nome bonito exigiria um campo novo, que a V1.2
    decidiu não criar.
    """
    return " ".join(part.capitalize() for part in slug.split("-") if part) or slug

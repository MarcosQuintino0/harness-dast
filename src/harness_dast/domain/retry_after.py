"""Interpreta o recuo temporário pedido pelo servidor, sem repetir requisições."""

from datetime import datetime
from email.utils import parsedate_to_datetime


def retry_after_seconds(value: str | None, now: datetime) -> float | None:
    """Devolve recuo entre 0 e 60 segundos, ou None para valor ausente ou inválido."""
    if value is None or len(value) > 100:
        return None
    value = value.strip()
    if value.isascii() and value.isdigit() and len(value) <= 3:
        seconds = float(value)
    else:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            seconds = (date - now).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return seconds if 0 < seconds <= 60 else None

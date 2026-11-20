"""Decisão pura sobre a ponte local de retorno OAST."""

from urllib.parse import urlsplit


def should_mount_oast_bridge(base_url: str, *, requested: bool) -> bool:
    """Permite a ponte de laboratório somente para o hostname exato do crAPI."""
    try:
        return requested and urlsplit(base_url).hostname == "crapi"
    except ValueError:
        return False

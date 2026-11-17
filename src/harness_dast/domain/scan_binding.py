"""Recibo aditivo da semente efetivamente entregue ao scanner, sem URL em claro."""

import json
from hashlib import sha256

from pydantic import Field

from harness_dast.domain.api_schema import ApiModel


class ScanBinding(ApiModel):
    """Associa alias e resumo da operação, método e URL completa da semente."""

    account: str = Field(min_length=1)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def bind_scan_seed(operation_id: str, method: str, url: str, account: str) -> ScanBinding:
    """Calcula recibo determinístico sem persistir URL nem credenciais em claro."""
    data = json.dumps([operation_id, method.upper(), url, account], ensure_ascii=True)
    return ScanBinding(account=account, digest=sha256(data.encode()).hexdigest())

"""Chave de mutação estável sem URL, valores ou identificadores de recurso."""

import hashlib
import json


def mutation_key(product: str, operation: str, account: str | None, method: str) -> str:
    """Resume somente contexto da operação; mesma classe de trabalho compartilha pendência."""
    identity = json.dumps((product, operation, account, method), ensure_ascii=True)
    return hashlib.sha256(identity.encode()).hexdigest()

"""Rótulos em português compartilhados pelo `report.md` e pelo `report.html`. Módulo puro."""

from typing import Final

SEVERITY_LABEL: Final = {
    "high": "Alta",
    "medium": "Média",
    "low": "Baixa",
    "informational": "Informativa",
    "unknown": "Desconhecida",
}
"""Nome de cada severidade proposta, da mais grave para a menos."""

SEVERITY_ORDER: Final = tuple(SEVERITY_LABEL)

CHECK_LABEL: Final = {
    "horizontal": "Acesso horizontal (BOLA)",
    "excessive_data": "Dado a mais (exposição excessiva)",
    "anonymous_access": "Acesso sem login",
    "tampered_token": "Token adulterado aceito",
    "vertical": "Acesso vertical (BFLA)",
    "access_matrix": "Tabela quem pode o quê (BFLA)",
    "mass_assignment": "Campo a mais (atribuição em massa)",
    "horizontal_write": "Escrita em recurso de outra conta (BOLA)",
}
CHECK_STATUS_LABEL: Final = {
    "completed": "concluída",
    "partial": "parcial",
    "skipped": "nada pôde ser testado",
    "disabled": "não rodou",
}

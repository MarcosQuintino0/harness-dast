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

SEEDED_SCANS_NOTICE: Final = (
    "{count} operações foram varridas a partir de uma resposta que não foi sucesso (por "
    "exemplo HTTP 404). O ataque partiu de um pedido que o alvo recusou ou não achou; achado "
    "aqui tem menos prova, e 'sem achado' aqui não indica que a operação é segura."
)
"""Aviso fixo de `coverage.seeded_scans` (ADR 0050); `{count}` é o número de operações."""

SEED_ASK_NOTICE: Final = (
    "para varrê-la a carta precisa autorizar `scan.include_outcomes: {outcome}` (peça ao dono "
    "do produto; o agente não liga isso)."
)
"""Frase do ADR 0050 em operação sem varredura por `not_success` (ADR 0046)."""


def seeded_scans_notice(count: int) -> str:
    """Aviso fixo de varredura a partir de resposta que não foi sucesso."""
    return SEEDED_SCANS_NOTICE.format(count=count)


def seed_tag(seed_outcome: str | None) -> str:
    """`(semente: not_found)` para achado vindo de semente que não foi sucesso, senão vazio."""
    return f"(semente: {seed_outcome})" if seed_outcome else ""


CHECK_LABEL: Final = {
    "cors": "Política CORS",
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

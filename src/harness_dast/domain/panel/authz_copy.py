"""Textos do painel conforme a verificação que produziu o achado de autorização."""

from harness_dast.domain.panel.model import PanelFinding

_BETWEEN_ACCOUNTS = frozenset({"authz_horizontal", "authz_horizontal_write"})


def authz_confidence_text(item: PanelFinding) -> str:
    """Descreve a observação registrada, sem inferir técnica ausente pelo título."""
    if item.authz_technique == "authz_cors":
        if item.parameter == "reflected_credentials":
            return "A resposta refletiu uma origem estranha e permitiu credenciais"
        if item.parameter == "wildcard":
            return "A resposta permitiu qualquer origem sem credenciais"
        return "O programa observou a política CORS na resposta"
    if item.authz_technique == "authz_excessive_data":
        return "A resposta trouxe campos que o OpenAPI não declara"
    if item.authz_technique == "authz_vertical":
        return "O programa repetiu o pedido com uma conta de papel menor e observou sucesso"
    if item.authz_technique in _BETWEEN_ACCOUNTS:
        return "O programa repetiu o pedido com outra conta e comparou as respostas"
    return "O programa verificou a resposta do sistema no teste de autorização"


def authz_repro_text(item: PanelFinding) -> str:
    """Explica a prova sem inventar detalhes ausentes do recibo redigido."""
    if item.authz_technique == "authz_cors":
        return (
            "O teste verificou a política CORS da resposta usando uma origem de teste. "
            "O registro não guarda o cabeçalho Origin enviado nem o pedido e a resposta "
            "inteiros. Por isso não há passo a passo para reproduzir à mão aqui."
        )
    if item.authz_technique == "authz_excessive_data":
        return (
            "O teste comparou os campos da resposta com o esquema do OpenAPI. "
            "O registro não guarda o pedido nem a resposta inteiros. Por isso não há passo "
            "a passo para reproduzir à mão aqui."
        )
    if item.authz_technique == "authz_vertical":
        return (
            "O teste repetiu a operação com uma conta de papel menor e registrou o status de "
            "sucesso. O registro não guarda o pedido nem a resposta inteiros. Por isso não há "
            "passo a passo para reproduzir à mão aqui."
        )
    if item.authz_technique in _BETWEEN_ACCOUNTS:
        return (
            "Esta falha vem da comparação entre duas contas: o programa repete um pedido com a "
            "outra conta e compara as respostas, sem guardar o pedido nem a resposta inteiros. "
            "Por isso não há passo a passo para reproduzir à mão aqui."
        )
    return (
        "O teste de autorização não guardou o pedido nem a resposta inteiros. "
        "Por isso não há passo a passo para reproduzir à mão aqui."
    )

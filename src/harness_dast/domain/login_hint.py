"""Dica para o login recusado pelo alvo, escolhida pelo código HTTP da resposta.

A mensagem genérica ("confira usuário e senha") deixou um agente sem saída numa rodada cega:
o alvo respondia 415 porque o perfil mandava o login como formulário e ele só aceitava JSON.
Este módulo decide a dica a partir do código e do formato atual. É puro.
"""

from typing import Literal

_FORMAT_STATUSES = frozenset({400, 415, 422})


def login_refused_hint(status: int, request_encoding: Literal["form", "json"] | None) -> str:
    """Devolve a dica para um login recusado com o código `status`.

    Args:
        status: Código HTTP da resposta do login (400 ou mais).
        request_encoding: Formato com que o perfil envia as credenciais (`auth.request_encoding`),
            ou `None` quando o login não é por usuário e senha.

    Returns:
        Texto da dica, em português, sem repetir usuário nem senha.
    """
    if status in _FORMAT_STATUSES and request_encoding is not None:
        other = "json" if request_encoding == "form" else "form"
        reason = (
            "o alvo não aceita o formato do corpo"
            if status == 415
            else "o alvo pode não ter entendido o corpo"
        )
        return (
            f"HTTP {status}: {reason}. O perfil envia o login como {request_encoding}. Se a "
            f"carta ou o OpenAPI dizem que o login é {other}, troque auth.request_encoding para "
            f"{other} no target.yml (campo livre: não muda a aprovação do escopo) e confira "
            "auth.username_field e auth.password_field."
        )
    if status in (401, 403):
        return (
            f"HTTP {status}: usuário ou senha recusados. Confira os nomes dos segredos "
            "(secret_ref) das contas e se as contas existem no ambiente."
        )
    if status in (404, 405):
        return (
            f"HTTP {status}: o caminho ou o método do login não existe. Confira auth.token_path "
            "no target.yml contra o OpenAPI."
        )
    if status == 429:
        return (
            "HTTP 429: o alvo limitou os logins. Espere a janela do limite antes de tentar de "
            "novo e confira auth.login_limit."
        )
    return (
        f"HTTP {status}: confira usuário e senha da conta, auth.token_path e "
        "auth.request_encoding no target.yml."
    )

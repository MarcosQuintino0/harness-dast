"""Direções de correção SUGERIDAS para APIs no estilo Spring, por CWE.

São texto nosso, genérico e não verificado contra o código do produto: o relatório os rotula
como sugestão. Sem CWE conhecido, o relatório remete à solução padrão do ZAP. Este módulo é puro.
"""

from typing import Final

_HINTS: Final[dict[int, str]] = {
    89: (
        "Use consultas parametrizadas (JPA com parâmetros nomeados, `NamedParameterJdbcTemplate`) "
        "e nunca concatene entrada em SQL; valide o formato do parâmetro de caminho."
    ),
    79: (
        "Trate a entrada como dado: valide formato e tamanho, devolva `Content-Type: "
        "application/json` e `X-Content-Type-Options: nosniff`, e escape na camada de apresentação."
    ),
    209: (
        "Não devolva pilha de execução nem mensagem interna; centralize o tratamento de erro "
        "(`@ControllerAdvice`) e responda com uma mensagem genérica."
    ),
    200: "Revise o que a resposta expõe; devolva só os campos necessários (DTO dedicado).",
    22: "Normalize e valide caminhos recebidos; nunca monte caminho de arquivo com entrada direta.",
    78: (
        "Não passe entrada a comandos do sistema; se inevitável, use lista de argumentos e "
        "permita só valores conhecidos."
    ),
    611: (
        "Desligue entidades externas e DTD no parser de XML "
        "(`XMLConstants.FEATURE_SECURE_PROCESSING`)."
    ),
    918: "Valide destino de requisições feitas pelo servidor contra uma lista permitida de hosts.",
    352: (
        "Mantenha a proteção CSRF do Spring Security para sessões em cookie; use token por "
        "requisição."
    ),
    942: "Restrinja `Access-Control-Allow-Origin` a origens conhecidas; evite `*` com credenciais.",
    693: "Configure os cabeçalhos de segurança (Spring Security `headers()`).",
    16: "Revise a configuração do servidor e dos cabeçalhos de resposta.",
}

DEFAULT_HINT: Final = (
    "Sem sugestão específica para este CWE nesta versão da CLI; siga a solução padrão do ZAP "
    "abaixo e revise com o time do produto."
)


def fix_hint(cwe: int | None) -> str:
    """Sugestão genérica de correção para o CWE, ou o texto padrão."""
    return DEFAULT_HINT if cwe is None else _HINTS.get(cwe, DEFAULT_HINT)

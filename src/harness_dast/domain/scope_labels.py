"""Nomes legíveis, em português, dos códigos de recusa e de liberação da cerca de escopo.

O que garante: todo código conhecido (`ScopeReason`, os motivos do proxy e a marca do modo
amplo) tem uma frase curta para quem lê o relatório e não conhece o identificador; um código
desconhecido volta como está (o relatório nunca esconde um motivo novo). O que não faz: não
decide nada, só nomeia. Este módulo é puro.
"""

from typing import Final

from harness_dast.domain.scope_reason import WIDE_READING_OUTSIDE_ALLOW

SCOPE_CODE_LABELS: Final[dict[str, str]] = {
    # Agrupador antigo e motivos do proxy.
    "malformed_request": "pedido com forma ambígua ou malformada (URL ou caminho)",
    "deny_path": "caminho proibido na carta (deny_paths)",
    "host_not_allowed": "servidor fora do escopo",
    "origin_not_allowed": "origem (esquema, servidor e porta) fora do escopo",
    "path_not_allowed": "caminho fora do que a carta permite (scope.allow)",
    "method_not_allowed": "método HTTP fora do que a carta permite",
    "host_header_mismatch": "cabeçalho Host diferente do endereço pedido",
    "upgrade_refused": "troca de protocolo (WebSocket e similares) recusada",
    "address_forbidden": "endereço de rede proibido",
    "dns_failure": "falha ao resolver o nome do servidor",
    "upstream_error": "o alvo não respondeu ao proxy",
    "kill_switch": "parada de emergência acionada",
    "run_expired": "prazo da execução esgotado",
    "approval_changed": "aprovação ou perfil alterado, ausente ou ilegível",
    "rate_queue_full": "fila de taxa cheia (varredor acima do limite de req/s)",
    "rate_backoff": "recuo temporário solicitado pelo destino",
    "audit_failure": "falha ao gravar a trilha de auditoria",
    # Forma do método, da URL e da autoridade.
    "method_unknown": "método HTTP desconhecido",
    "url_missing": "URL ausente",
    "url_too_long": "URL longa demais",
    "url_forbidden_char": "caractere proibido na URL",
    "url_not_absolute": "URL não absoluta",
    "url_not_ascii": "URL com caracteres fora de ASCII",
    "scheme_not_allowed": "esquema não permitido",
    "credentials_in_url": "usuário e senha dentro da URL",
    "port_invalid": "porta inválida",
    "host_invalid": "nome de servidor inválido",
    # Forma do caminho (o que impede a injeção em segmento de caminho).
    "path_empty_segment": "caminho com segmento vazio (//)",
    "path_encoded_slash": "barra codificada no caminho (%2f)",
    "path_matrix_param": "parâmetro de matriz no caminho (;)",
    "path_trailing_dot_space": "ponto ou espaço no fim de um segmento do caminho",
    "path_double_encoding": "dupla codificação no caminho (%252f)",
    "path_dot_segment": "segmento . ou .. no caminho",
    "path_bad_percent": "codificação percentual inválida no caminho",
    "path_invalid_utf8": "bytes inválidos (UTF-8) no caminho",
    "path_control_char": "caractere de controle no caminho",
    "path_too_many_readings": "caminho com leituras demais (ambíguo)",
    # Marca do modo amplo (liberação, não recusa).
    WIDE_READING_OUTSIDE_ALLOW: (
        "liberado no modo amplo com uma leitura do caminho fora de scope.allow"
    ),
}

READING_MODE_LABELS: Final[dict[str, str]] = {
    "strict": "modo estrito, o padrão: toda leitura do caminho precisa estar em scope.allow",
    "wide": (
        "modo amplo, autorizado na carta: aceita formas ambíguas de caminho e só é seguro com "
        "deny_paths completo"
    ),
}


def label_for(code: str) -> str:
    """Frase legível do código, ou o próprio código quando ele não é conhecido."""
    return SCOPE_CODE_LABELS.get(code, code)


def reading_mode_label(mode: str) -> str:
    """Frase legível do modo de leitura do caminho (`strict` ou `wide`)."""
    return READING_MODE_LABELS.get(mode, mode)

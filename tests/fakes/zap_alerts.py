"""Alertas e mensagens do ZAP com as formas registradas no spike do M0 (Q5), para os testes.

Reconstruídos do spike, não capturados: veja `tests/fixtures/zap_alerts/README.md`.
"""

from harness_dast.domain.zap_messages import ZapMessage

BASE = "https://api.hml.acme-teste.net.br"


def zap_alert(alert_id: str = "1", **changes: str) -> dict[str, str]:
    """Alerta de injeção de SQL como o spike o mostrou (URL atacada, mutada)."""
    alert = {
        "id": alert_id,
        "pluginId": "40018",
        "alertRef": "40018",
        "alert": "SQL Injection",
        "name": "SQL Injection",
        "cweid": "89",
        "wascid": "19",
        "risk": "High",
        "confidence": "Low",
        "method": "GET",
        "url": f"{BASE}/api/pacientes/'",
        "param": "",
        "attack": "'",
        "evidence": "HTTP/1.1 500 Internal Server Error",
        "inputVector": "urlpath",
        "messageId": "1604",
        "sourceMessageId": "4",
        "nodeName": "",
        "description": "<p>SQL injection may be possible.</p>",
        "solution": "<p>Do not trust client side input.</p>",
        "reference": "https://owasp.org/www-community/attacks/SQL_Injection",
        "other": "",
        "tags": "{}",
    }
    alert.update(changes)
    return alert


def attack_message(
    message_id: int,
    *,
    token: str = "tok-do-ataque",  # noqa: S107 - sentinela de teste
    body: str = "",
) -> ZapMessage:
    """Mensagem de ataque cuja requisição leva o token em claro (como o ZAP a guarda)."""
    return ZapMessage(
        id=message_id,
        type="3",
        request_header=(
            f"GET {BASE}/api/pacientes/' HTTP/1.1\r\nHost: api.hml.acme-teste.net.br\r\n"
            f"Authorization: Bearer {token}\r\nContent-Type: application/json\r\n"
        ),
        request_body=body,
        response_header="HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\n",
        response_body='{"error": "SQLSyntaxError near \'"}',
    )

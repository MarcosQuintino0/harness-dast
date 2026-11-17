"""Resultado das checagens próprias da V1.12 (limite de consumo e inventário). Módulo puro.

Duas capacidades que só a carta liga (`extra_checks.allow_rate_tests` e `extra_checks.inventory`,
ADR 0096) mandam pedidos da própria CLI pela cerca e devolvem achados no formato do alerta do ZAP,
anexados ao fluxo normal (mesma redação, agrupamento, fingerprint e triagem; ADR 0100 fez o
mesmo para o SSRF). Aqui ficam o resumo gravado em `scan.json` e a montagem do alerta. Nenhum
valor enviado, corpo de resposta ou segredo entra nesses modelos: só nomes, códigos e contagens.
"""

from typing import Final, Literal

from harness_dast.domain.api_schema import ApiModel

Risk = Literal["Medium", "Low", "Informational"]
ResultOutcome = Literal["finding", "limited", "inconclusive", "absent"]

RATE_PAGE_PLUGIN: Final = "hdast-rate-pagesize"
RATE_ATTEMPTS_PLUGIN: Final = "hdast-rate-attempts"
INVENTORY_SIBLING_PLUGIN: Final = "hdast-inventory-sibling"
INVENTORY_DOCS_PLUGIN: Final = "hdast-inventory-docs"


class ExtraSkip(ApiModel):
    """Operação ou caminho que ficou sem o teste, com o motivo.

    Attributes:
        subject: Operação (`operation_id`) ou caminho concreto.
        reason: Motivo curto: `not_allowed_by_scope`, `not_verifiable_by_fence`,
            `budget_exceeded`, `no_test_identity`, `unsupported_body`, `needs_example`...
        detail: Complemento curto, ou `None`.
    """

    subject: str
    reason: str
    detail: str | None = None


class ExtraCheckResult(ApiModel):
    """O que uma checagem concluiu sobre uma operação ou caminho.

    Attributes:
        check: `page_size`, `attempts`, `sibling` ou `docs`.
        subject: Operação (`operation_id`) ou caminho concreto.
        outcome: `finding` (achado gerado), `limited` (o alvo limitou, sem achado),
            `inconclusive` (não deu para concluir) ou `absent` (não existe).
        requests: Pedidos enviados para esta conclusão.
        detail: Resumo legível, sem valores enviados nem corpo de resposta.
    """

    check: str
    subject: str
    outcome: ResultOutcome
    requests: int = 0
    detail: str | None = None


class ExtraChecksSummary(ApiModel):
    """Resumo de uma checagem extra gravado em `scan.json`.

    Attributes:
        enabled: A chave da carta estava ligada.
        cap: Teto rígido de pedidos desta checagem por execução.
        sent: Pedidos enviados (com as retentativas do despachante).
        findings: Achados gerados.
        results: Conclusão por operação ou caminho.
        skipped: O que ficou sem o teste.
        note: Observação (parada antecipada, por exemplo).
    """

    enabled: bool = False
    cap: int = 0
    sent: int = 0
    findings: int = 0
    results: tuple[ExtraCheckResult, ...] = ()
    skipped: tuple[ExtraSkip, ...] = ()
    note: str | None = None


def build_alert(
    *,
    ident: str,
    plugin_id: str,
    title: str,
    cwe: int,
    risk: Risk,
    confidence: Literal["High", "Medium", "Low"],
    method: str,
    url: str,
    param: str,
    evidence: str,
    description: str,
    solution: str,
) -> dict[str, str]:
    """Alerta no formato do ZAP (`RawAlert`) para um achado da CLI.

    A severidade e a confiança são as propostas pela regra; nada muda depois (a triagem não as
    altera). `evidence` e `description` não podem trazer valor enviado nem corpo de resposta.
    """
    return {
        "id": ident,
        "pluginId": plugin_id,
        "alertRef": f"{plugin_id}-1",
        "alert": title,
        "cweid": str(cwe),
        "wascid": "0",
        "risk": risk,
        "confidence": confidence,
        "method": method,
        "url": url,
        "param": param,
        "attack": "",
        "evidence": evidence,
        "inputVector": "",
        "messageId": "",
        "sourceMessageId": "",
        "description": description,
        "solution": solution,
    }

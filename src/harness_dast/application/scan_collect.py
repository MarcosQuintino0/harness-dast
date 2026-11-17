"""Coleta de alertas e evidência ao fim do `scan`, SEMPRE redigidas antes de gravar.

Nada não redigido chega ao disco: o alerta bruto passa por `redact_alert` e cada mensagem de
evidência por `redact_message`, com os segredos registrados da execução (`SecretVault.mask`).
A evidência é buscada só para as mensagens mais graves e confiáveis (teto fixo), para que uma
varredura barulhenta não encha o disco.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Final

import structlog

from harness_dast.application.common_ports import SecretVault
from harness_dast.application.scan_ports import RunArtifacts, ScanControl
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.redaction import EvidenceMessage, redact_alert, redact_message
from harness_dast.domain.zap_alert import RawAlert, evidence_candidates, parse_severity

EVIDENCE_CAP: Final = 200
"""Mensagens de evidência guardadas por execução."""

_MAX_CONSECUTIVE_FAILURES: Final = 3
_log = structlog.get_logger()


@dataclass(frozen=True)
class Collected:
    """O que foi gravado.

    Attributes:
        alerts_total: Alertas brutos gravados.
        by_risk: Contagem pela severidade proposta pelo ZAP.
        evidence_messages: Mensagens de evidência gravadas.
    """

    alerts_total: int
    by_risk: dict[str, int]
    evidence_messages: int


def collect(
    *,
    scanner: ScanControl,
    artifacts: RunArtifacts,
    vault: SecretVault,
    run_id: str,
    base_url: str,
) -> Collected:
    """Lê os alertas do ZAP, redige, busca a evidência, redige e grava.

    Raises:
        ExternalToolError: Falha ao listar alertas, ou três falhas seguidas ao buscar mensagens.
        ConfigError: Falha de escrita.
    """
    redacted = [redact_alert(alert, vault.mask) for alert in scanner.list_alerts(base_url)]
    artifacts.write_alerts(run_id, redacted)
    parsed = [RawAlert.model_validate(alert) for alert in redacted]
    messages = _fetch_evidence(scanner, vault, parsed)
    artifacts.write_evidence(run_id, messages)
    counts = Counter(parse_severity(alert.risk) for alert in parsed)
    return Collected(len(redacted), dict(sorted(counts.items())), len(messages))


def _fetch_evidence(
    scanner: ScanControl, vault: SecretVault, alerts: list[RawAlert]
) -> list[EvidenceMessage]:
    messages: list[EvidenceMessage] = []
    consecutive = 0
    for message_id in evidence_candidates(alerts, EVIDENCE_CAP):
        try:
            raw = scanner.get_message(message_id)
        except ExternalToolError as error:
            consecutive += 1
            _log.warning("evidence_unavailable", message_id=message_id, reason=error.message)
            if consecutive >= _MAX_CONSECUTIVE_FAILURES:
                raise
            continue
        consecutive = 0
        messages.append(redact_message(raw, vault.mask))
    return messages

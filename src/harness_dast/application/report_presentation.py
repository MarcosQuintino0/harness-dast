"""Monta a apresentação consultiva com entradas externas validadas por portas."""

from typing import Literal, Protocol

from harness_dast.application.verification import verify_offline
from harness_dast.domain.authz.result import AuthzFinding
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import Finding
from harness_dast.domain.human_confirmation import HumanConfirmations
from harness_dast.domain.negative_result import NegativeFinding
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.report.presentation import Calibration, Presentation, PresentedFinding
from harness_dast.domain.signal_result import SignalFinding
from harness_dast.domain.verification import VerificationEntry, VerificationFile


class PresentationFiles(Protocol):
    """Fronteira de leitura dos arquivos consultivos da execução e da calibração."""

    def verification(self, product: str, run_id: str) -> VerificationFile | None:
        """Lê verificação validada ou None se ausente; inválida levanta ConfigError."""
        ...

    def confirmations(self, product: str, run_id: str) -> HumanConfirmations | None:
        """Lê confirmações validadas ou None se ausentes; inválidas levantam ConfigError."""
        ...

    def calibration(self) -> Calibration | None:
        """Lê calibração validada ou None se ausente; inválida levanta ConfigError."""
        ...


class PresentationBuilder:
    """Combina arquivos consultivos sem alterar achados ou consultar o alvo."""

    def __init__(self, files: PresentationFiles) -> None:
        """Recebe a porta de leitura de arquivos."""
        self._files = files

    def build(self, report: FindingsReport) -> Presentation:
        """Monta uma linha por achado atual e ignora entradas órfãs.

        Raises:
            ConfigError: Entrada inválida ou pertencente a outra execução.
        """
        verification = self._files.verification(report.product, report.run_id)
        humans = self._files.confirmations(report.product, report.run_id)
        for envelope in (verification, humans):
            if envelope is not None and (
                envelope.product != report.product or envelope.run_id != report.run_id
            ):
                raise ConfigError(
                    "Arquivo consultivo de outra execução.", hint="Confira produto e run_id."
                )
        offline = verify_offline(report.product, report.run_id, report.findings)
        entries = {item.fingerprint: item for item in offline.entries}
        if verification is not None:
            entries.update({item.fingerprint: item for item in verification.entries})
        confirmations = humans.entries if humans else ()
        rows: list[PresentedFinding] = []
        groups: tuple[
            tuple[
                Literal["zap", "authz", "negative", "proxy"],
                tuple[Finding | AuthzFinding | NegativeFinding | SignalFinding, ...],
            ],
            ...,
        ] = (
            ("zap", report.findings),
            ("authz", report.authz.findings if report.authz else ()),
            ("negative", report.negative.findings if report.negative else ()),
            ("proxy", report.proxy_signals.findings if report.proxy_signals else ()),
        )
        for origin, items in groups:
            for item in items:
                entry = entries.get(item.fingerprint) or VerificationEntry(
                    fingerprint=item.fingerprint,
                    level="not_verifiable",
                    reason="Não há verificação registrada para este achado.",
                )
                rows.append(
                    PresentedFinding(
                        finding_id=item.finding_id,
                        title=item.title,
                        severity=item.proposed_severity,
                        origin=origin,
                        verification=entry,
                        confirmations=tuple(
                            x for x in confirmations if x.fingerprint == item.fingerprint
                        ),
                    )
                )
        return Presentation(findings=tuple(rows), calibration=self._files.calibration())

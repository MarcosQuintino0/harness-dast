"""Caso de uso de registro de confirmação humana, sem tráfego ao alvo."""

from collections.abc import Callable
from datetime import UTC

from pydantic import ValidationError

from harness_dast.application.common_ports import Clock
from harness_dast.application.human_confirmation_ports import (
    HumanConfirmationPrompt,
    HumanConfirmationStore,
    HumanFindingReader,
)
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.human_confirmation import HumanConfirmation, report_has_fingerprint
from harness_dast.domain.redaction import redact_body
from harness_dast.domain.run_ref import require_run_id


class AcknowledgeFinding:
    """Confere contexto e coleta declaração antes de acrescentar um registro."""

    def __init__(
        self,
        store: HumanConfirmationStore,
        findings: HumanFindingReader,
        prompt: HumanConfirmationPrompt,
        clock: Clock,
        mask: Callable[[str], str],
    ) -> None:
        """Recebe portas e função de redação de segredos conhecidos."""
        self._store, self._findings, self._prompt, self._clock, self._mask = (
            store,
            findings,
            prompt,
            clock,
            mask,
        )

    def execute(self, product: str, run_id: str, fingerprint: str, *, interactive: bool) -> bool:
        """Acrescenta registro ou retorna False no cancelamento; recusa entradas inválidas."""
        if not interactive:
            raise ConfigError(
                "Confirmação exige terminal interativo, sem --json.",
                hint="Peça a uma pessoa para executar o comando no terminal.",
            )
        require_run_id(run_id)
        report = self._findings.read_findings(run_id)
        if report.product != product or report.run_id != run_id:
            raise ConfigError("Produto e execução não correspondem ao relatório.")
        if not report_has_fingerprint(report, fingerprint):
            raise ConfigError("Fingerprint não encontrado no relatório da execução.")
        self._store.read(product, run_id)
        answer = self._prompt.ask(fingerprint)
        if answer is None:
            return False
        person, observation = answer
        person = redact_body(person, self._mask, cap=200)[0].strip()
        observation = redact_body(observation, self._mask)[0].strip()
        try:
            entry = HumanConfirmation(
                fingerprint=fingerprint,
                person=person,
                observation=observation,
                confirmed_at=self._clock.now().astimezone(UTC),
            )
        except ValidationError:
            raise ConfigError(
                "Declaração inválida ou ausente.", hint="Informe quem confirmou e o que viu."
            ) from None
        self._store.append(product, run_id, entry)
        return True

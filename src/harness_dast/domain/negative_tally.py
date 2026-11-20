"""Contagem do teste negativo: totais por classe e por operação (ADR 0051).

Acumula, a cada caso enviado, o veredito da reação. Guarda só contagens: nunca valor enviado nem
corpo de resposta. Este módulo é puro.
"""

from collections.abc import Iterable

from harness_dast.domain.negative_plan import NegativeCase
from harness_dast.domain.negative_result import ClassSummary, OperationSummary
from harness_dast.domain.negative_values import CLASS_ORDER, CaseClass
from harness_dast.domain.negative_verdict import Verdict

_OperationKey = tuple[str, str, str]


class NegativeTally:
    """Totais de um estágio em andamento."""

    def __init__(self, planned: Iterable[NegativeCase]) -> None:
        """Cria a contagem com os casos planejados.

        Args:
            planned: Casos do plano (definem os totais `planned` por classe).
        """
        self._planned: dict[CaseClass, int] = dict.fromkeys(CLASS_ORDER, 0)
        for case in planned:
            self._planned[case.case_class] += 1
        self._by_class: dict[CaseClass, dict[Verdict, int]] = {
            name: dict.fromkeys(("rejected", "accepted", "server_error", "inconclusive"), 0)
            for name in CLASS_ORDER
        }
        self._by_operation: dict[_OperationKey, dict[Verdict, int]] = {}

    def record(self, case: NegativeCase, verdict: Verdict) -> None:
        """Conta um caso que chegou ao alvo, com o veredito da resposta."""
        self._by_class[case.case_class][verdict] += 1
        row = self._by_operation.setdefault(
            case.key, dict.fromkeys(("rejected", "accepted", "server_error", "inconclusive"), 0)
        )
        row[verdict] += 1

    def by_class(self) -> tuple[ClassSummary, ...]:
        """Uma linha por classe, na ordem de prioridade."""
        rows: list[ClassSummary] = []
        for name in CLASS_ORDER:
            counts = self._by_class[name]
            rows.append(
                ClassSummary(
                    case_class=name,
                    planned=self._planned[name],
                    sent=sum(counts.values()),
                    rejected=counts["rejected"],
                    accepted=counts["accepted"],
                    server_error=counts["server_error"],
                    inconclusive=counts["inconclusive"],
                )
            )
        return tuple(rows)

    def operations(self) -> tuple[OperationSummary, ...]:
        """Uma linha por operação com ao menos um caso enviado, na ordem do primeiro envio."""
        return tuple(
            OperationSummary(
                operation_id=operation_id,
                method=method,
                path=path,
                sent=sum(counts.values()),
                rejected=counts["rejected"],
                accepted=counts["accepted"],
                server_error=counts["server_error"],
                inconclusive=counts["inconclusive"],
            )
            for (operation_id, method, path), counts in self._by_operation.items()
        )

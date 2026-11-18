"""Comparação entre execuções por fingerprint: novo, persistente e "não observado".

"Não observado nesta execução" NÃO significa "corrigido": a operação pode não ter sido
varrida agora, o varredor é não determinístico e os limites cortam a cobertura. O texto do
aviso e o campo `operation_scanned_now` existem para que ninguém leia o contrário. Este módulo
é puro.
"""

from collections.abc import Collection, Iterable, Sequence
from typing import Final, Literal

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import FINGERPRINT_VERSION, Finding
from harness_dast.domain.report.model import ComparisonInfo, FindingsReport, GoneFinding
from harness_dast.domain.scan_result import ScanEntry

COMPARISON_NOTICE: Final = (
    "'Não observado nesta execução' não significa 'corrigido': a operação pode não ter sido "
    "varrida agora, a varredura pode ter sido cortada ou o varredor pode não ter repetido o "
    "ataque. Confirme com uma nova rodada controlada antes de dar o problema por resolvido."
)

RetestStatus = Literal["reproduced", "not_reproduced", "not_tested"]


class RetestResult(ApiModel):
    """Resultado do reteste de um achado anterior, limitado à execução atual."""

    fingerprint: str
    result: RetestStatus


def entry_was_fully_scanned(entry: ScanEntry) -> bool:
    """Diz se a entrada do `scan.json` prova que a operação foi atacada até o fim.

    Só `completed` com requisições enviadas conta. `refused`, `stopped` (janela, prazo ou
    parada), `truncated` e entradas sem requisição não provam teste: ausência do achado
    nessas operações é `not_tested`, nunca `not_reproduced`.
    """
    return entry.outcome == "completed" and not entry.truncated and entry.requests > 0


def fully_scanned_operations(entries: Iterable[ScanEntry]) -> frozenset[str]:
    """Operações com ao menos uma entrada que prova teste completo (`entry_was_fully_scanned`)."""
    return frozenset(entry.operation_id for entry in entries if entry_was_fully_scanned(entry))


def classify_retest(
    previous: Sequence[Finding],
    current: Sequence[Finding],
    scanned_operations: Collection[str],
) -> tuple[RetestResult, ...]:
    """Classifica cada achado anterior pela evidência registrada na execução atual.

    Args:
        previous: Achados selecionados de uma execução comparável.
        current: Achados atuais do mesmo produto e da mesma versão de fingerprint.
        scanned_operations: Identificadores das operações efetivamente varridas agora.

    Returns:
        Um resultado para cada item anterior, na ordem recebida, inclusive se o
        fingerprint se repetir. Ausência do fingerprint só conta como não reprodução
        quando a operação está na cobertura registrada.
    """
    observed = {item.fingerprint for item in current}
    return tuple(
        RetestResult(
            fingerprint=item.fingerprint, result=_retest_status(item, observed, scanned_operations)
        )
        for item in previous
    )


def _retest_status(
    finding: Finding, observed: set[str], scanned_operations: Collection[str]
) -> RetestStatus:
    if finding.fingerprint in observed:
        return "reproduced"
    if finding.operation_id is not None and finding.operation_id in scanned_operations:
        return "not_reproduced"
    return "not_tested"


def ensure_comparable(baseline: FindingsReport, product: str) -> None:
    """Confere se a execução base pode ser comparada com a atual.

    Raises:
        ConfigError: Produto diferente ou versão do fingerprint diferente (fingerprints de
            versões distintas não se comparam).
    """
    if baseline.product != product:
        raise ConfigError(
            "A execução de comparação é de outro produto.",
            hint="Compare execuções do mesmo produto.",
        )
    if baseline.fingerprint_version != FINGERPRINT_VERSION:
        raise ConfigError(
            f"A execução de comparação usa a versão {baseline.fingerprint_version} do "
            f"fingerprint; esta CLI usa a {FINGERPRINT_VERSION}.",
            hint="Gere de novo o relatório da execução antiga com a CLI da época e compare "
            "manualmente.",
        )


def compare_findings(
    current: Sequence[Finding],
    baseline: FindingsReport,
    scanned_operations: Collection[str],
) -> tuple[tuple[Finding, ...], tuple[GoneFinding, ...], ComparisonInfo]:
    """Marca cada achado como novo ou persistente e lista os não observados.

    Args:
        current: Achados desta execução.
        baseline: Relatório da execução base (já conferido por `ensure_comparable`).
        scanned_operations: Operações varridas nesta execução.

    Returns:
        Os achados atuais com `comparison`, os achados da base não observados e o resumo.
    """
    before = {item.fingerprint for item in baseline.findings}
    retest = classify_retest(baseline.findings, current, scanned_operations)
    marked = tuple(
        item.model_copy(
            update={"comparison": "persistent" if item.fingerprint in before else "new"}
        )
        for item in current
    )
    gone = tuple(
        GoneFinding(
            fingerprint=item.fingerprint,
            finding_id=item.finding_id,
            title=item.title,
            proposed_severity=item.proposed_severity,
            method=item.method,
            path_template=item.path_template,
            operation_scanned_now=classified.result == "not_reproduced",
        )
        for item, classified in zip(baseline.findings, retest, strict=True)
        if classified.result != "reproduced"
    )
    persistent = sum(1 for item in marked if item.comparison == "persistent")
    info = ComparisonInfo(
        baseline_run_id=baseline.run_id,
        new=len(marked) - persistent,
        persistent=persistent,
        not_observed=len(gone),
        notice=COMPARISON_NOTICE,
    )
    return marked, gone, info

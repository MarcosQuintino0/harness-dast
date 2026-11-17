"""Comparação entre execuções por fingerprint: novo, persistente e "não observado".

"Não observado nesta execução" NÃO significa "corrigido": a operação pode não ter sido
varrida agora, o varredor é não determinístico e os limites cortam a cobertura. O texto do
aviso e o campo `operation_scanned_now` existem para que ninguém leia o contrário. Este módulo
é puro.
"""

from collections.abc import Collection, Sequence
from typing import Final

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import FINGERPRINT_VERSION, Finding
from harness_dast.domain.report.model import ComparisonInfo, FindingsReport, GoneFinding

COMPARISON_NOTICE: Final = (
    "'Não observado nesta execução' não significa 'corrigido': a operação pode não ter sido "
    "varrida agora, a varredura pode ter sido cortada ou o varredor pode não ter repetido o "
    "ataque. Confirme com uma nova rodada controlada antes de dar o problema por resolvido."
)


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
    before = {item.fingerprint: item for item in baseline.findings}
    now = {item.fingerprint for item in current}
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
            operation_scanned_now=item.operation_id in scanned_operations,
        )
        for item in baseline.findings
        if item.fingerprint not in now
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

"""Reteste dos achados do Nuclei (ADR 0122): seleção e classificação, tudo puro.

O reteste repete só os modelos dos achados abertos (`U-...`) e classifica cada um pela
impressão digital, como faz com os do ZAP. O texto nunca diz "corrigido": o modelo que não casou
de novo só prova que não casou nesta execução. "Reproduzido" aqui é o mesmo motor com o mesmo
modelo, não uma confirmação independente.
"""

from collections.abc import Sequence
from typing import Final

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import Finding
from harness_dast.domain.finding_diff import RetestStatus
from harness_dast.domain.nuclei_findings import NucleiFinding
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.retest import RetestEntry, select_for_retest
from harness_dast.domain.zap_alert import SEVERITY_RANK

__all__ = ["nuclei_retest_entries", "select_retest_targets"]

_REASONS: Final[dict[RetestStatus, str]] = {
    "reproduced": (
        "O mesmo modelo do Nuclei voltou a casar no mesmo método e caminho nesta execução. É o "
        "mesmo motor e o mesmo modelo: reprodução, não confirmação independente."
    ),
    "not_reproduced": (
        "O Nuclei rodou até o fim nesta execução e o modelo não casou de novo no mesmo método e "
        "caminho. Isto não prova que o problema foi corrigido."
    ),
    "not_tested": (
        "O Nuclei não rodou até o fim nesta execução (parada, falha ou sem resultado); nada se "
        "pode afirmar sobre o achado."
    ),
}


def select_retest_targets(
    findings: Sequence[Finding],
    nuclei_findings: Sequence[NucleiFinding],
    chosen: Sequence[str],
    max_findings: int,
) -> tuple[tuple[Finding, ...], tuple[NucleiFinding, ...]]:
    """Escolhe os achados do ZAP e os do Nuclei a retestar.

    Args:
        findings: Achados do ZAP da execução anterior.
        nuclei_findings: Achados abertos do Nuclei da execução anterior (`nuclei.json`).
        chosen: Fingerprints de `--finding`, do ZAP ou do Nuclei; vazio escolhe os de severidade
            alta e média do ZAP e todos os abertos do Nuclei, do mais grave para o menos.
        max_findings: Teto de achados (1 a 30).

    Returns:
        Os achados do ZAP e os do Nuclei escolhidos, sem repetição. Sem achado elegível do ZAP,
        mas com achados do Nuclei, a parte do ZAP vem vazia e o reteste roda só o Nuclei.

    Raises:
        ConfigError: Teto fora do intervalo, fingerprint inexistente, excesso sobre o teto ou
            nada a retestar (nem do ZAP, nem do Nuclei).
    """
    by_fingerprint = {item.fingerprint: item for item in nuclei_findings}
    names = tuple(dict.fromkeys(chosen))
    if names:
        zap_names = tuple(name for name in names if name not in by_fingerprint)
        picked_nuclei = tuple(by_fingerprint[name] for name in names if name in by_fingerprint)
        selected = select_for_retest(findings, zap_names, max_findings) if zap_names else ()
        if len(selected) + len(picked_nuclei) > max_findings:
            raise ConfigError(
                f"--finding citou {len(selected) + len(picked_nuclei)} achados, acima do teto "
                f"--max {max_findings}.",
                hint="Reduza os --finding ou aumente --max (até 30).",
            )
        return selected, picked_nuclei
    try:
        selected = select_for_retest(findings, (), max_findings)
    except ConfigError:
        if not nuclei_findings:
            raise
        selected = ()
    ranked = sorted(nuclei_findings, key=lambda item: -SEVERITY_RANK[item.proposed_severity])
    return selected, tuple(ranked[:max_findings])


def nuclei_retest_entries(
    selected: Sequence[NucleiFinding], current: NucleiResult | None
) -> tuple[RetestEntry, ...]:
    """Classifica cada achado do Nuclei pela impressão digital na execução nova.

    Args:
        selected: Achados escolhidos da execução anterior.
        current: `nuclei.json` da execução nova, ou `None` se o estágio não deixou resultado.

    Returns:
        Uma entrada por achado, na ordem. `reproduced` se a mesma impressão digital voltou
        (mesmo com parada depois); `not_reproduced` só se o estágio terminou; senão `not_tested`.
    """
    seen = {item.fingerprint for item in current.findings} if current else frozenset[str]()
    finished = current is not None and current.status == "completed"
    entries: list[RetestEntry] = []
    for item in selected:
        status: RetestStatus = (
            "reproduced"
            if item.fingerprint in seen
            else ("not_reproduced" if finished else "not_tested")
        )
        entries.append(_entry(item, status))
    return tuple(entries)


def _entry(item: NucleiFinding, status: RetestStatus) -> RetestEntry:
    record = item.record
    return RetestEntry(
        fingerprint=item.fingerprint,
        finding_id=item.finding_id,
        title=record.template_id,
        proposed_severity=item.proposed_severity,
        method=record.method or "-",
        path_template=record.matched_path,
        operation_id=f"nuclei:{record.template_id}",
        origin="nuclei",
        result=status,
        reason=_REASONS[status],
    )

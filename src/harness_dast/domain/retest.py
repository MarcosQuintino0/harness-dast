"""Reteste de achados (ADR 0112): seleção, resultado e `retest.json`, tudo puro.

O reteste repete a varredura só nas operações dos achados escolhidos e classifica cada um com
`classify_retest`. O texto nunca diz "corrigido": o varredor não é determinístico e os limites
cortam a cobertura, então o máximo que se afirma é "não reproduzido nesta execução".
"""

from collections.abc import Collection, Sequence
from typing import Final, Literal

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import Finding
from harness_dast.domain.finding_diff import (
    COMPARISON_NOTICE,
    RetestResult,
    RetestStatus,
    classify_retest,
)
from harness_dast.domain.zap_alert import SEVERITY_RANK, Severity

RETEST_SCHEMA_VERSION: Final = 1
DEFAULT_MAX_FINDINGS: Final = 10
MAX_FINDINGS_LIMIT: Final = 30

_DEFAULT_SEVERITIES: Final[frozenset[Severity]] = frozenset({"high", "medium"})
_REASONS: Final[dict[RetestStatus, str]] = {
    "reproduced": "O mesmo fingerprint apareceu de novo nesta execução.",
    "not_reproduced": (
        "A operação foi testada nesta execução e o fingerprint não apareceu. Isto não prova "
        "que o problema foi corrigido."
    ),
    "not_tested": (
        "A operação não foi testada nesta execução (corte, limite ou falha de alcance); nada "
        "se pode afirmar sobre o achado."
    ),
}


class RetestEntry(ApiModel):
    """Um achado da execução anterior e o que o reteste observou sobre ele.

    `origin` diz quem achou (`zap` ou `nuclei`, ADR 0122); no Nuclei, `operation_id` é
    `nuclei:<modelo>` e `title` é o identificador do modelo.
    """

    fingerprint: str
    finding_id: str
    title: str
    proposed_severity: Severity
    method: str
    path_template: str
    operation_id: str
    origin: Literal["zap", "nuclei"] = "zap"
    result: RetestStatus
    reason: str


class RetestCounts(ApiModel):
    """Contagem dos três resultados."""

    reproduced: int
    not_reproduced: int
    not_tested: int


class RetestReport(ApiModel):
    """Conteúdo de `retest.json`.

    Attributes:
        schema_version: Versão do formato.
        product: Produto.
        previous_run_id: Execução anterior, de onde vieram os achados.
        run_id: Execução do reteste.
        generated_at: Instante da geração (ISO 8601).
        only: Operações repetidas, na ordem.
        counts: Contagem por resultado.
        entries: Um item por achado escolhido, na ordem da seleção.
        notice: Aviso de que "não reproduzido" não prova correção.
    """

    schema_version: int = RETEST_SCHEMA_VERSION
    product: str
    previous_run_id: str
    run_id: str
    generated_at: str
    only: tuple[str, ...]
    counts: RetestCounts
    entries: tuple[RetestEntry, ...]
    notice: str = COMPARISON_NOTICE


def select_for_retest(
    findings: Sequence[Finding], chosen: Sequence[str], max_findings: int
) -> tuple[Finding, ...]:
    """Escolhe os achados a retestar.

    Args:
        findings: Achados da execução anterior (`findings.json`).
        chosen: Fingerprints pedidos com `--finding`; vazio escolhe os de severidade alta e
            média, do mais grave para o menos, na ordem do relatório.
        max_findings: Teto de achados (1 a 30).

    Returns:
        Os achados escolhidos, sem repetição.

    Raises:
        ConfigError: Teto fora do intervalo, fingerprint inexistente ou sem operação, ou nada
            a retestar.
    """
    if not 1 <= max_findings <= MAX_FINDINGS_LIMIT:
        raise ConfigError(
            f"--max precisa estar entre 1 e {MAX_FINDINGS_LIMIT}.",
            hint=f"O padrão é {DEFAULT_MAX_FINDINGS}; para mais achados, rode em partes.",
        )
    picked = _explicit(findings, chosen) if chosen else _by_severity(findings, max_findings)
    if not picked:
        raise ConfigError(
            "A execução anterior não tem achado de severidade alta ou média para retestar.",
            hint="Escolha achados com --finding FINGERPRINT ou informe outra execução.",
        )
    if len(picked) > max_findings:
        raise ConfigError(
            f"--finding citou {len(picked)} achados, acima do teto --max {max_findings}.",
            hint="Reduza os --finding ou aumente --max (até 30).",
        )
    return picked


def _explicit(findings: Sequence[Finding], chosen: Sequence[str]) -> tuple[Finding, ...]:
    by_fingerprint = {item.fingerprint: item for item in findings}
    names = tuple(dict.fromkeys(chosen))
    unknown = [name for name in names if name not in by_fingerprint]
    if unknown:
        raise ConfigError(
            f"{len(unknown)} fingerprint(s) de --finding não existem na execução anterior.",
            hint="Copie o fingerprint de findings.json da execução anterior.",
        )
    picked = tuple(by_fingerprint[name] for name in names)
    without = [item.finding_id for item in picked if item.operation_id is None]
    if without:
        raise ConfigError(
            "Achado sem operação do probe não pode ser retestado: " + ", ".join(without) + ".",
            hint="O reteste repete operações; reteste este achado com um run completo.",
        )
    return picked


def _by_severity(findings: Sequence[Finding], max_findings: int) -> tuple[Finding, ...]:
    eligible = [
        item
        for item in findings
        if item.proposed_severity in _DEFAULT_SEVERITIES and item.operation_id is not None
    ]
    eligible.sort(key=lambda item: -SEVERITY_RANK[item.proposed_severity])
    return tuple(eligible[:max_findings])


def operations_of(findings: Sequence[Finding]) -> tuple[str, ...]:
    """Operações dos achados, sem repetição e na ordem (a lista do `--only`).

    Raises:
        ConfigError: Algum achado não tem operação.
    """
    names = [item.operation_id for item in findings]
    found = tuple(dict.fromkeys(name for name in names if name is not None))
    if len(found) == 0 or any(name is None for name in names):
        raise ConfigError(
            "Achado sem operação do probe não pode ser retestado.",
            hint="Reteste este achado com um run completo.",
        )
    return found


def build_retest_report(
    *,
    product: str,
    previous_run_id: str,
    run_id: str,
    generated_at: str,
    selected: Sequence[Finding],
    current: Sequence[Finding],
    scanned_operations: Collection[str],
    nuclei_entries: Sequence[RetestEntry] = (),
) -> RetestReport:
    """Classifica os achados escolhidos e monta o `retest.json`.

    Args:
        product: Produto.
        previous_run_id: Execução anterior.
        run_id: Execução do reteste.
        generated_at: Instante da geração.
        selected: Achados escolhidos (`select_for_retest`).
        current: Achados da execução nova.
        scanned_operations: Operações efetivamente varridas na execução nova.
        nuclei_entries: Entradas já classificadas dos achados do Nuclei (`retest_nuclei`); vêm
            depois das do ZAP e entram na contagem.

    Returns:
        O relatório, com o aviso fixo.
    """
    results = classify_retest(selected, current, scanned_operations)
    zap_entries = tuple(
        _entry(item, result) for item, result in zip(selected, results, strict=True)
    )
    entries = (*zap_entries, *nuclei_entries)
    counts = RetestCounts(
        reproduced=sum(1 for item in entries if item.result == "reproduced"),
        not_reproduced=sum(1 for item in entries if item.result == "not_reproduced"),
        not_tested=sum(1 for item in entries if item.result == "not_tested"),
    )
    return RetestReport(
        product=product,
        previous_run_id=previous_run_id,
        run_id=run_id,
        generated_at=generated_at,
        only=operations_of(selected) if selected else (),
        counts=counts,
        entries=entries,
    )


def _entry(finding: Finding, result: RetestResult) -> RetestEntry:
    return RetestEntry(
        fingerprint=finding.fingerprint,
        finding_id=finding.finding_id,
        title=finding.title,
        proposed_severity=finding.proposed_severity,
        method=finding.method,
        path_template=finding.path_template,
        operation_id=finding.operation_id or "",
        result=result.result,
        reason=_REASONS[result.result],
    )


def reproduced_at_threshold(report: RetestReport, threshold: str) -> bool:
    """Diz se algum achado reproduzido tem severidade no limiar de falha ou acima.

    `unknown` conta como acima de qualquer limiar diferente de `none` (falha fechada).
    """
    if threshold == "none":
        return False
    floor = SEVERITY_RANK[threshold]
    return any(
        item.result == "reproduced"
        and (item.proposed_severity == "unknown" or SEVERITY_RANK[item.proposed_severity] >= floor)
        for item in report.entries
    )

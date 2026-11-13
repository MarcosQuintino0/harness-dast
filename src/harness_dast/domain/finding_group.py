"""Agrupamento de achados pela causa provável (visão a mais; nenhum achado some).

Regra (versão 1): dois achados são do MESMO grupo quando têm a mesma regra do ZAP
(`alert_ref`), o mesmo vetor de entrada, o mesmo parâmetro e a mesma severidade proposta.
A lista "onde aparece" mostra todos os caminhos do grupo: agrupar nunca esconde onde o problema
está. Achados de origens diferentes entram pela mesma regra, sem tratamento especial.

O grupo NÃO altera severidade, confiança, status nem fingerprint de ninguém: todo achado
pertence a exatamente um grupo e continua em `findings`. Este módulo é puro.
"""

import hashlib
from collections.abc import Sequence
from typing import Final

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.finding import Finding
from harness_dast.domain.known_patterns import expected_pattern_note

GROUPING_VERSION: Final = 1
_SEVERITY_ORDER: Final = ("high", "medium", "low", "informational", "unknown")
_SEPARATOR: Final = "\x1f"


class GroupLocation(ApiModel):
    """Onde um achado do grupo aparece.

    Attributes:
        finding_id: Achado de `findings` a que a linha se refere.
        method: Método HTTP da requisição aprendida.
        path_template: Modelo de caminho da requisição aprendida.
        operation_id: Operação do probe, ou `None`.
        occurrences: Alertas do ZAP reunidos nesse achado.
    """

    finding_id: str
    method: str
    path_template: str
    operation_id: str | None = None
    occurrences: int


class FindingGroup(ApiModel):
    """Achados com a mesma causa provável.

    Attributes:
        group_id: `G-` e 8 hexadecimais da chave do grupo (legível, não é identidade).
        title: Título do achado mais bem classificado do grupo.
        plugin_id: Regra do ZAP.
        alert_ref: Regra com sub-regra.
        parameter: Parâmetro comum, vazio quando não há.
        input_vector: Vetor comum, vazio para achados passivos.
        proposed_severity: Severidade proposta, igual à de todos os membros.
        cwe: CWE comum, ou `None`.
        findings_count: Quantos achados há no grupo.
        occurrences: Soma dos alertas do ZAP dos membros.
        finding_ids: Achados do grupo, na ordem de `findings`.
        locations: Onde cada achado aparece.
        expected_note: Nota fixa do código quando o padrão costuma ser esperado, ou `None`.
    """

    group_id: str
    title: str
    plugin_id: str
    alert_ref: str
    parameter: str = ""
    input_vector: str = ""
    proposed_severity: str
    cwe: int | None = None
    findings_count: int
    occurrences: int
    finding_ids: tuple[str, ...]
    locations: tuple[GroupLocation, ...]
    expected_note: str | None = None


def _key(item: Finding) -> tuple[str, ...]:
    return (
        item.alert_ref.strip(),
        item.input_vector.strip().lower(),
        item.parameter.strip(),
        item.proposed_severity,
    )


def _group_id(key: tuple[str, ...]) -> str:
    digest = hashlib.sha256(
        _SEPARATOR.join((f"hdast-group-v{GROUPING_VERSION}", *key)).encode("utf-8")
    )
    return f"G-{digest.hexdigest()[:8]}"


def _sort_key(group: FindingGroup) -> tuple[int, int, str, str]:
    return (
        _SEVERITY_ORDER.index(group.proposed_severity),
        -group.findings_count,
        group.title,
        group.group_id,
    )


def group_findings(findings: Sequence[Finding]) -> tuple[FindingGroup, ...]:
    """Agrupa os achados pela causa provável.

    Args:
        findings: Achados já ordenados (o primeiro de cada grupo dá o título).

    Returns:
        Grupos ordenados por severidade, tamanho e título; cada achado em exatamente um.
    """
    buckets: dict[tuple[str, ...], list[Finding]] = {}
    for item in findings:
        buckets.setdefault(_key(item), []).append(item)
    groups = [_build(key, members) for key, members in buckets.items()]
    return tuple(sorted(groups, key=_sort_key))


def _build(key: tuple[str, ...], members: list[Finding]) -> FindingGroup:
    head = members[0]
    return FindingGroup(
        group_id=_group_id(key),
        title=head.title,
        plugin_id=head.plugin_id,
        alert_ref=head.alert_ref,
        parameter=head.parameter.strip(),
        input_vector=head.input_vector.strip().lower(),
        proposed_severity=head.proposed_severity,
        cwe=head.classification.cwe,
        findings_count=len(members),
        occurrences=sum(item.occurrences for item in members),
        finding_ids=tuple(item.finding_id for item in members),
        locations=tuple(
            GroupLocation(
                finding_id=item.finding_id,
                method=item.method,
                path_template=item.path_template,
                operation_id=item.operation_id,
                occurrences=item.occurrences,
            )
            for item in members
        ),
        expected_note=expected_pattern_note(head.plugin_id, head.parameter),
    )

"""Reprodução de um achado do Nuclei pelo `confirm`, sem E/S (ADR 0122).

O `confirm` repete o MESMO modelo do achado pelo caso de uso do Nuclei, com o mesmo motor e a
mesma cerca. Isso é reprodução, nunca confirmação independente: um modelo com defeito repete o
defeito. Por isso o veredito é conservador:

- `reproduced` só quando a nova execução devolve a mesma impressão digital (modelo, método e
  caminho); vale mesmo que a execução tenha parado depois, porque o achado já foi visto;
- `inconclusive` quando não voltou, com o motivo (parada, linhas ilegíveis ou só "não voltou").
  Não voltar NÃO prova correção nem falso positivo, então `likely_false_positive` nunca sai daqui.

Nenhum texto do resultado carrega caminho, host, valor extraído ou conteúdo do alvo: só o
identificador do modelo, as versões fixadas e contagens.
"""

from typing import Final

from harness_dast.domain.nuclei_findings import NucleiFinding
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.verification import VerificationEntry

__all__ = [
    "NUCLEI_RECIPE",
    "judge_nuclei_reproduction",
    "nuclei_not_verifiable",
]

NUCLEI_RECIPE: Final = "nuclei_template"
"""Nome da receita registrada em `verification.json` para a reprodução do Nuclei."""
_CONTROL: Final = (
    "Sem controle independente: o Nuclei repete o mesmo modelo com o mesmo motor. Reprodução "
    "não é confirmação independente."
)


def nuclei_not_verifiable(finding: NucleiFinding, reason: str) -> VerificationEntry:
    """Entrada `not_verifiable` para um achado do Nuclei que não pôde ser repetido."""
    return VerificationEntry(
        fingerprint=finding.fingerprint,
        level="not_verifiable",
        reason=reason,
        recipe=NUCLEI_RECIPE,
    )


def _attack(finding: NucleiFinding, result: NucleiResult, *, matched: int) -> str:
    return (
        f"Modelo {finding.record.template_id} repetido pelo Nuclei {result.nuclei_version} "
        f"(modelos {result.templates_version}); {matched} ocorrência(s) com a mesma "
        f"impressão digital, {len(result.findings)} achado(s) no total; "
        f"{result.malformed_lines} linha(s) ilegível(is)."
    )


def judge_nuclei_reproduction(finding: NucleiFinding, result: NucleiResult) -> VerificationEntry:
    """Compara a repetição do modelo com o achado original.

    Args:
        finding: Achado do `nuclei.json` original.
        result: Resultado limpo da nova execução do mesmo modelo.

    Returns:
        `reproduced` se a mesma impressão digital voltou; senão `inconclusive`.
    """
    matched = sum(
        item.occurrences for item in result.findings if item.fingerprint == finding.fingerprint
    )
    attack = _attack(finding, result, matched=matched)
    if matched:
        return VerificationEntry(
            fingerprint=finding.fingerprint,
            level="reproduced",
            reason=(
                "Reprodução: o mesmo modelo do Nuclei voltou a casar no mesmo método e caminho. "
                "É o mesmo motor e o mesmo modelo, não uma confirmação independente."
            ),
            recipe=NUCLEI_RECIPE,
            attack=attack,
            control=_CONTROL,
        )
    if result.status != "completed":
        why = "A repetição parou antes do fim, então o modelo pode não ter chegado ao caminho."
    elif result.malformed_lines:
        why = "Houve linhas da saída do Nuclei que não puderam ser lidas."
    else:
        why = "O modelo rodou até o fim e não casou de novo; isso não prova correção."
    return VerificationEntry(
        fingerprint=finding.fingerprint,
        level="inconclusive",
        reason=f"Não reproduzido: {why} Também não prova falso positivo.",
        recipe=NUCLEI_RECIPE,
        attack=attack,
        control=_CONTROL,
    )

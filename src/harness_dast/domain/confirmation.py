"""Seleção e avaliação conservadora das receitas de confirmação, sem E/S.

O arquivo reúne o planejamento e os vereditos das receitas para manter suas premissas de
comparação revisáveis juntas; não contém envio nem persistência.
"""

import re
from hashlib import sha256
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.authz.result import AuthzFinding
from harness_dast.domain.finding import Finding, normalize_path_template
from harness_dast.domain.http_messages import HttpResponse
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.scan_result import ScanEntry
from harness_dast.domain.verification import VerificationEntry, classify_finding

Recipe = Literal["sql_boolean", "sql_time", "xss_reflected", "internal_error"]
_RECIPES: dict[str, Recipe] = {
    "40018": "sql_boolean",
    "40022": "sql_time",
    "40012": "xss_reflected",
    "90022": "internal_error",
}


class ConfirmationPlan(ApiModel):
    """Uma semente elegível e receita fixa para um único parâmetro de consulta."""

    recipe: Recipe
    exchange: ExchangeRecord
    parameter: str = Field(min_length=1, max_length=200)
    marker: str = Field(pattern=r"^[a-f0-9]{16}$")


def plan_confirmation(
    finding: Finding,
    exchanges: tuple[ExchangeRecord, ...],
    scans: tuple[ScanEntry, ...],
    marker: str,
) -> ConfirmationPlan | VerificationEntry:
    """Seleciona somente GET varrido com semente de sucesso e parâmetro inequívoco."""
    if finding.plugin_id in {"10020", "10021", "10036", "10038"}:
        return classify_finding(finding)
    if finding.plugin_id == "6":
        return _refuse(
            finding,
            "Travessia exige arquivo e conteúdo benignos comprovados; falta oráculo seguro.",
        )
    if finding.method.upper() != "GET":
        return _refuse(
            finding, "Escritas e DELETE não são repetidos sem autorização e diário comprovados."
        )
    recipe = _RECIPES.get(finding.plugin_id)
    if recipe is None:
        return _refuse(finding, "Não há receita segura para este tipo de achado.")
    if finding.seed_outcome is not None:
        return _refuse(finding, "Semente com resultado diferente de sucesso não é repetida.")
    if finding.input_vector.lower() not in {"query", "querystring"}:
        return _refuse(finding, "A receita só suporta parâmetro de consulta comprovado.")
    for exchange in exchanges:
        if not _matches(finding, exchange, scans):
            continue
        pairs = parse_qsl(urlsplit(exchange.target).query, keep_blank_values=True)
        if sum(name == finding.parameter for name, _ in pairs) != 1:
            continue
        return ConfirmationPlan(
            recipe=recipe, exchange=exchange, parameter=finding.parameter, marker=marker
        )
    return _refuse(
        finding, "Não há semente GET de sucesso, varrida e com parâmetro de consulta inequívoco."
    )


def _matches(finding: Finding, exchange: ExchangeRecord, scans: tuple[ScanEntry, ...]) -> bool:
    if finding.operation_id is None or exchange.operation_id != finding.operation_id:
        return False
    if exchange.method.upper() != "GET" or not 200 <= exchange.status < 300:
        return False
    if exchange.body is not None or exchange.multipart is not None or exchange.omitted_fields:
        return False
    if normalize_path_template(exchange.path) != normalize_path_template(finding.path_template):
        return False
    return any(
        scan.operation_id == exchange.operation_id
        and scan.method.upper() == "GET"
        and normalize_path_template(scan.path) == normalize_path_template(exchange.path)
        and bool(scan.scan_id)
        and scan.requests > 0
        and scan.outcome != "refused"
        and scan.seed_outcome is None
        for scan in scans
    )


def _refuse(finding: Finding, reason: str) -> VerificationEntry:
    return VerificationEntry(fingerprint=finding.fingerprint, level="not_verifiable", reason=reason)


def recipe_targets(plan: ConfirmationPlan) -> tuple[str, ...]:
    """Monta somente valores fixos para a consulta da semente, preservando o caminho."""
    marker = f"<hdast-{plan.marker}>"
    values: dict[Recipe, tuple[str | None, ...]] = {
        "sql_boolean": (None, "' OR '1'='1", "' OR '1'='2", "' OR '1'='1", "' OR '1'='2"),
        "sql_time": (
            None,
            None,
            "' OR pg_sleep(2) IS NULL--",
            None,
            "' OR pg_sleep(2) IS NULL--",
            None,
        ),
        "xss_reflected": (f"hdast-{plan.marker}", marker, f"hdast-{plan.marker}", marker),
        "internal_error": (None, "'", None, "'"),
    }
    return tuple(_replace_query(plan, value) for value in values[plan.recipe])


def _replace_query(plan: ConfirmationPlan, value: str | None) -> str:
    if value is None:
        return plan.exchange.target
    parts = urlsplit(plan.exchange.target)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode([(name, value if name == plan.parameter else item) for name, item in pairs])
    return urlunsplit(("", "", parts.path, query, ""))


def judge_confirmation(
    plan: ConfirmationPlan, responses: tuple[HttpResponse | None, ...], fingerprint: str
) -> VerificationEntry:
    """Compara medições repetidas; nunca inclui corpos nem mensagens externas no resultado."""
    expected = len(recipe_targets(plan))
    if len(responses) != expected or any(response is None for response in responses):
        return _result(
            fingerprint,
            plan.recipe,
            "inconclusive",
            "Falha de transporte ou orçamento insuficiente.",
        )
    measured = tuple(response for response in responses if response is not None)
    if (
        any(response.body_truncated or response.status >= 500 for response in measured)
        and plan.recipe != "internal_error"
    ):
        return _result(
            fingerprint,
            plan.recipe,
            "inconclusive",
            "Resposta truncada ou erro do servidor impede comparação segura.",
        )
    if any(response.status in {401, 403, 429} for response in measured):
        return _result(
            fingerprint, plan.recipe, "inconclusive", "Autenticação ou limite impediu a comparação."
        )
    controls: tuple[HttpResponse, ...]
    attacks: tuple[HttpResponse, ...]
    if plan.recipe == "sql_boolean":
        result = _boolean(fingerprint, measured)
        controls, attacks = (measured[0], measured[2], measured[4]), (measured[1], measured[3])
    elif plan.recipe == "sql_time":
        result = _timing(fingerprint, measured)
        controls, attacks = tuple(measured[i] for i in (0, 1, 3, 5)), (measured[2], measured[4])
    elif plan.recipe == "xss_reflected":
        result = _xss(fingerprint, plan, measured)
        controls, attacks = (measured[0], measured[2]), (measured[1], measured[3])
    else:
        result = _internal_error(fingerprint, measured)
        controls, attacks = (measured[0], measured[2]), (measured[1], measured[3])
    return result.model_copy(
        update={"attack": _summarize(attacks), "control": _summarize(controls)}
    )


def _summarize(responses: tuple[HttpResponse, ...]) -> str:
    return "; ".join(f"HTTP {item.status}, {item.elapsed_ms} ms" for item in responses)


def _result(
    fingerprint: str, recipe: Recipe, level: Literal["reproduced", "inconclusive"], reason: str
) -> VerificationEntry:
    return VerificationEntry(fingerprint=fingerprint, recipe=recipe, level=level, reason=reason)


def _signature(response: HttpResponse) -> tuple[int, bytes]:
    return response.status, sha256(response.body).digest()


def _boolean(fingerprint: str, r: tuple[HttpResponse, ...]) -> VerificationEntry:
    base, true1, false1, true2, false2 = map(_signature, r)
    if 200 <= r[0].status < 300 and base == true1 == true2 and false1 == false2 and false1 != base:
        return _result(
            fingerprint,
            "sql_boolean",
            "reproduced",
            "Verdadeiro repetiu a base e falso divergiu duas vezes; banco não identificado.",
        )
    return _result(
        fingerprint,
        "sql_boolean",
        "inconclusive",
        "Comparação sem diferença consistente; respostas iguais não refutam o alerta.",
    )


def _timing(fingerprint: str, r: tuple[HttpResponse, ...]) -> VerificationEntry:
    controls = [r[i].elapsed_ms for i in (0, 1, 3, 5)]
    attacks = [r[i].elapsed_ms for i in (2, 4)]
    variation = max(controls) - min(controls)
    if (
        200 <= r[0].status < 300
        and len({_signature(x) for x in r}) == 1
        and variation <= 500
        and min(attacks) - max(controls) >= max(1200, 3 * variation)
    ):
        return _result(
            fingerprint,
            "sql_time",
            "reproduced",
            "Dois atrasos superaram a variação dos controles; receita específica de PostgreSQL.",
        )
    return _result(
        fingerprint,
        "sql_time",
        "inconclusive",
        "Atraso não se distinguiu da variação natural; outros bancos não são cobertos.",
    )


def _xss(
    fingerprint: str, plan: ConfirmationPlan, r: tuple[HttpResponse, ...]
) -> VerificationEntry:
    marker = f"<hdast-{plan.marker}>".encode()
    harmless = f"hdast-{plan.marker}".encode()
    attacks = (r[1], r[3])
    controls = (r[0], r[2])
    if (
        all(
            (x.content_type or "").split(";")[0].strip().lower() == "text/html" and marker in x.body
            for x in attacks
        )
        and all(marker not in x.body and harmless in x.body for x in controls)
        and len({x.status for x in r}) == 1
        and 200 <= r[0].status < 300
    ):
        return _result(
            fingerprint,
            "xss_reflected",
            "reproduced",
            "Marcador refletiu em HTML contra controle; isso não prova execução JavaScript.",
        )
    return _result(
        fingerprint,
        "xss_reflected",
        "inconclusive",
        "Não houve reflexão HTML não codificada consistente contra controle.",
    )


def _internal_error(fingerprint: str, r: tuple[HttpResponse, ...]) -> VerificationEntry:
    def detailed(response: HttpResponse) -> bool:
        body = response.body.lower()
        return (
            response.status >= 500
            and (
                b"traceback (most recent call last)" in body
                or (b"exception" in body and (b"\n\tat " in body or b"\n    at " in body))
            )
            and not response.body_truncated
        )

    if (
        detailed(r[1])
        and detailed(r[3])
        and 200 <= r[0].status < 300
        and _signature(r[0]) == _signature(r[2])
    ):
        return _result(
            fingerprint,
            "internal_error",
            "reproduced",
            "Erro detalhado repetido divergiu da entrada válida; não identifica injeção SQL.",
        )
    return _result(
        fingerprint,
        "internal_error",
        "inconclusive",
        "O detalhe de erro não se repetiu de modo consistente contra entrada válida.",
    )


def select_confirmation_findings(
    findings: tuple[Finding | AuthzFinding, ...], limit: int, fingerprint: str | None
) -> tuple[Finding | AuthzFinding, ...]:
    """Ordena achados por severidade e aplica seleção que apenas reduz o teto.

    Raises:
        ConfigError: Teto fora de 1..30, fingerprint inválido ou inexistente.
    """
    from harness_dast.domain.errors import ConfigError

    if not 1 <= limit <= 30:
        raise ConfigError("--max deve estar entre 1 e 30.")
    fingerprints = [item.fingerprint for item in findings]
    if len(fingerprints) != len(set(fingerprints)) or any(
        re.fullmatch(r"[0-9a-f]{64}", value) is None for value in fingerprints
    ):
        raise ConfigError("A execução contém fingerprints inválidos ou repetidos.")
    if fingerprint is not None:
        matching = tuple(item for item in findings if item.fingerprint == fingerprint)
        if len(matching) != 1:
            raise ConfigError("Fingerprint inválido, ausente ou repetido na execução.")
        return matching
    priority = {"high": 0, "medium": 1, "low": 2, "informational": 3}
    return tuple(sorted(findings, key=lambda item: priority.get(item.proposed_severity, 4))[:limit])


def classify_authz_confirmation(finding: AuthzFinding) -> VerificationEntry:
    """Reconhece comparação guardada entre contas somente com estados e identidades válidos."""
    horizontal = (
        finding.technique == "authz_horizontal"
        and "com corpo equivalente para o mesmo pedido." in finding.evidence
    )
    vertical = (
        finding.technique == "authz_vertical"
        and finding.actor_role is not None
        and finding.owner_role is not None
        and finding.actor_role != finding.owner_role
        and "menor) recebeu" in finding.evidence
    )
    if (
        (horizontal or vertical)
        and finding.owner_account is not None
        and finding.owner_account != finding.actor_account
        and finding.baseline_status is not None
        and 200 <= finding.baseline_status < 300
        and finding.observed_status is not None
        and 200 <= finding.observed_status < 300
    ):
        return VerificationEntry(
            fingerprint=finding.fingerprint,
            level="reproduced",
            recipe="authz_recorded",
            reason="Comparação guardada entre contas distintas mostra respostas de sucesso.",
            attack=f"HTTP {finding.observed_status}",
            control=f"HTTP {finding.baseline_status}",
        )
    return VerificationEntry(
        fingerprint=finding.fingerprint,
        level="not_verifiable",
        reason="A comparação guardada não contém estados e identidades suficientes.",
    )


def merge_confirmation_entries(
    existing: tuple[VerificationEntry, ...], updates: tuple[VerificationEntry, ...]
) -> tuple[VerificationEntry, ...]:
    """Substitui apenas resultados selecionados, preservando os demais e sua ordem."""
    by_fingerprint = {item.fingerprint: item for item in updates}
    merged = [by_fingerprint.pop(item.fingerprint, item) for item in existing]
    merged.extend(item for item in updates if item.fingerprint in by_fingerprint)
    return tuple(merged)

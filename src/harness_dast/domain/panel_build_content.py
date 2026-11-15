"""Peças de conteúdo do painel: funções, falhas graves, o que ficou de fora e próximos passos.

Funções puras sobre os modelos que os arquivos da execução já têm. Cada decisão de estado (o que
é "atacada", "com falha grave", "proibida pela carta") mora aqui e nunca na página. Nada altera
severidade, apaga achado ou diz "seguro". Módulo puro.
"""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Final

from harness_dast.domain.api_model import Operation
from harness_dast.domain.authz_result import AuthzFinding, AuthzResult
from harness_dast.domain.finding import Finding
from harness_dast.domain.finding_confidence import confidence_step
from harness_dast.domain.manual_repro import build_manual_repro
from harness_dast.domain.panel_format import (
    FunctionStateKind,
    capitalize_first,
    count_word,
    pick,
    plural,
)
from harness_dast.domain.panel_model import (
    FindingCounts,
    PanelExplanation,
    PanelFinding,
    PanelFunction,
    PanelGroup,
    PanelLeftOut,
    PanelStep,
)
from harness_dast.domain.probe_result import OperationResult, ProbeResult
from harness_dast.domain.report_labels import seeded_scans_notice
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.report_traffic import path_shape_warning
from harness_dast.domain.scan_plan import ScanSkip
from harness_dast.domain.scan_result import ScanEntry, ScanResult

OTHER_AREA: Final = "Outras"
STRONG: Final = 2
_STEP_LEVEL: Final[dict[str, int]] = {"a confirmar": 1, "prova forte": STRONG, "confirmada": 3}
_NOT_ATTACKED: Final = frozenset({"refused"})
_FORBIDDEN_OUTCOMES: Final = {
    "skipped_scope": "Fora do escopo da carta.",
    "skipped_denied": "Caminho que a carta proíbe, na lista `deny_paths`.",
    "skipped_destructive": "Função que apaga dados (DELETE): a ferramenta nunca a ataca.",
}
_FORBIDDEN_SKIPS: Final = {
    "scope": "Fora do escopo da carta.",
    "denied": "Caminho que a carta proíbe, na lista `deny_paths`.",
    "delete": "Função que apaga dados (DELETE): a ferramenta nunca a ataca.",
    "login": "Entrada (login): não é atacada, para não bloquear a conta de teste.",
}
_NOT_TRIED_SKIPS: Final = {
    "mutating": "Altera dados de um recurso que o teste não criou: só entra com autorização.",
    "not_selected": "Fora da seleção pedida para esta varredura.",
    "not_planned": "Não estava no plano da varredura.",
    "not_run": "A varredura parou antes de chegar a esta função.",
}
_FAILED_SKIPS: Final = {
    "not_success": "Não respondeu como esperado no alcance, então não foi atacada.",
    "not_learned": "O ZAP não guardou o pedido desta função, então não foi atacada.",
}
_OUTCOME_WORDS: Final = {
    "logical_failure": "a resposta diz que falhou, mesmo com status de sucesso",
    "validation_error": "o sistema recusou os dados enviados (400 ou 422)",
    "conflict": "o sistema acusou conflito de dados (409)",
    "auth_error": "a conta de teste não teve permissão (401 ou 403)",
    "csrf_error": "o sistema recusou o pedido por proteção CSRF",
    "not_found": "o recurso não foi encontrado (404)",
    "rate_limited": "o sistema pediu para ir mais devagar (429)",
    "server_error": "o sistema deu erro interno (5xx)",
    "client_error": "o sistema recusou o pedido (4xx)",
    "redirect": "o sistema mandou para outro endereço (não seguido)",
    "timeout": "o sistema não respondeu a tempo",
    "skipped_dependency": "depende de outra função que não respondeu",
    "build_error": "a ferramenta não conseguiu montar o pedido",
}
_BLIND: Final = (
    "Este tipo de teste não vê falha de lógica de negócio nem dado a mais em respostas legítimas.",
    "Sem falha grave não é atestado: só vale para as funções e os ataques que rodaram.",
)


def _confidence(item: Finding) -> int:
    """Degrau do medidor (1 a confirmar, 2 prova forte, 3 confirmada), pela regra única.

    A regra mora em `finding_confidence.confidence_step` (ADR 0032, item 8). Aqui só vira
    número. Nenhum arquivo da execução registra confirmação por pessoa, então o degrau 3 não
    sai deste cálculo.
    """
    return _STEP_LEVEL[confidence_step(item)]


def _zap_finding(
    item: Finding,
    names: Mapping[str, str],
    explanations: Mapping[str, PanelExplanation],
    accounts: Mapping[str, str],
    paths: Mapping[str, str],
) -> PanelFinding:
    note = item.triage
    return PanelFinding(
        finding_id=item.finding_id,
        origin="zap",
        title=item.title,
        severity=item.proposed_severity,
        confidence=_confidence(item),
        proposed_confidence=item.proposed_confidence,
        method=item.method,
        path_template=restore_path(item.path_template, item.operation_id, paths),
        operation_id=item.operation_id,
        function_name=names.get(item.operation_id or ""),
        parameter=item.parameter,
        input_vector=item.input_vector,
        occurrences=item.occurrences,
        cwe=item.classification.cwe,
        owasp=item.classification.owasp_api_2023,
        description=item.description,
        solution=item.solution,
        evidence=item.evidence,
        reproduce_curl=item.reproduce_curl,
        repro=build_manual_repro(item, account=accounts.get(item.operation_id or "")),
        comparison=item.comparison,
        suspected_false_positive=None if note is None else note.suspected_false_positive,
        triage_note=(note.note or None) if note else None,
        explanation=explanations.get(item.finding_id),
    )


def _authz_finding(
    item: AuthzFinding,
    names: Mapping[str, str],
    explanations: Mapping[str, PanelExplanation],
    paths: Mapping[str, str],
) -> PanelFinding:
    return PanelFinding(
        finding_id=item.finding_id,
        origin="authz",
        title=item.title,
        severity=item.proposed_severity,
        confidence=STRONG,
        method=item.method,
        path_template=restore_path(item.path_template, item.operation_id, paths),
        operation_id=item.operation_id,
        function_name=names.get(item.operation_id),
        parameter=", ".join(item.fields),
        cwe=item.cwe,
        owasp=item.owasp_api_2023,
        description=item.description,
        solution=item.solution,
        authz_evidence=item.evidence,
        explanation=explanations.get(item.finding_id),
    )


def build_severe(
    report: FindingsReport | None,
    authz: AuthzResult | None,
    names: Mapping[str, str],
    explanations: Mapping[str, PanelExplanation],
    probe: ProbeResult | None = None,
    paths: Mapping[str, str] | None = None,
) -> tuple[PanelFinding, ...]:
    """Falhas graves (severidade proposta `high`), da prova mais forte para a mais fraca.

    O `probe` dá o apelido da conta que enviou cada operação (para "Como reproduzir à mão");
    `paths` devolve o nome dos parâmetros do endereço.
    """
    known = paths or {}
    accounts = {
        result.operation_id: result.account
        for result in (probe.operations if probe else ())
        if result.account
    }
    found = [
        _zap_finding(item, names, explanations, accounts, known)
        for item in (report.findings if report else ())
        if item.proposed_severity == "high"
    ]
    found += [
        _authz_finding(item, names, explanations, known)
        for item in (authz.findings if authz else ())
        if item.proposed_severity == "high"
    ]
    return tuple(sorted(found, key=lambda item: (-item.confidence, item.finding_id)))


def build_counts(report: FindingsReport | None, authz: AuthzResult | None) -> FindingCounts | None:
    """Achados por severidade proposta (ZAP mais autorização entre contas), ou `None`."""
    if report is None:
        return None
    counts = Counter(item.proposed_severity for item in report.findings)
    counts.update(item.proposed_severity for item in (authz.findings if authz else ()))
    return FindingCounts(
        high=counts["high"],
        medium=counts["medium"],
        low=counts["low"],
        informational=counts["informational"],
        unknown=counts["unknown"],
        groups=len(report.groups),
    )


def build_groups(
    report: FindingsReport | None, paths: Mapping[str, str] | None = None
) -> tuple[PanelGroup, ...]:
    """Grupos do `findings.json` (cada achado em exatamente um)."""
    if report is None:
        return ()
    operation_of = {item.finding_id: item.operation_id for item in report.findings}
    known = paths or {}
    return tuple(
        PanelGroup(
            group_id=group.group_id,
            title=group.title,
            severity=group.proposed_severity,
            findings_count=group.findings_count,
            occurrences=group.occurrences,
            cwe=group.cwe,
            locations=tuple(
                (
                    loc.method,
                    restore_path(loc.path_template, operation_of.get(loc.finding_id), known),
                    loc.finding_id,
                )
                for loc in group.locations
            ),
            expected_note=group.expected_note,
            parameter=group.parameter,
        )
        for group in report.groups
    )


_NAME_CAP: Final = 40
_PLACEHOLDER: Final = re.compile(r"\{[^{}]*\}")


def function_paths(operations: Sequence[Operation]) -> dict[str, str]:
    """Caminho do Swagger por `operation_id` (com o nome de cada parâmetro: `{crm}`)."""
    return {item.operation_id: item.path for item in operations}


def restore_path(template: str, operation_id: str | None, paths: Mapping[str, str]) -> str:
    """Devolve o nome do parâmetro que o relatório apagou (`/crm/{}` vira `/crm/{crm}`).

    O relatório guarda o endereço com chaves vazias. Só troca quando o caminho do Swagger da
    mesma operação, com as chaves esvaziadas, é exatamente o gravado: senão fica o que foi
    gravado.
    """
    real = paths.get(operation_id or "")
    if real is None or "{}" not in template:
        return template
    return real if _PLACEHOLDER.sub("{}", real) == template else template


def function_names(operations: Sequence[Operation]) -> dict[str, str]:
    """Nome simples por `operation_id`: o `summary` do OpenAPI, senão o próprio id.

    Duas funções com o mesmo nome ganham o método e o caminho ao lado, para a lista nunca ter
    linhas idênticas.
    """
    plain = {item.operation_id: item.summary or item.operation_id for item in operations}
    repeated = {name for name, count in Counter(plain.values()).items() if count > 1}
    return {
        item.operation_id: (
            f"{_shorten(plain[item.operation_id])} ({item.method.upper()} {item.path})"
            if plain[item.operation_id] in repeated
            else plain[item.operation_id]
        )
        for item in operations
    }


def _shorten(name: str) -> str:
    return name if len(name) <= _NAME_CAP else name[: _NAME_CAP - 1].rstrip() + "…"


def _decide(
    result: OperationResult | None,
    entry: ScanEntry | None,
    skip: ScanSkip | None,
    severe: bool,
) -> tuple[FunctionStateKind, str | None]:
    if entry is not None and entry.outcome not in _NOT_ATTACKED:
        cut = {
            "truncated": "A varredura foi cortada antes do fim.",
            "stopped": "Parada antes do fim.",
        }
        return ("severe" if severe else "tested", cut.get(entry.outcome))
    if entry is not None:
        return "failed", "O ZAP recusou iniciar a varredura desta função."
    if result is None:
        if skip is not None:
            return _decide_skip(skip)
        return "not_tried", "O alcance não tentou esta função."
    return _decide_probe(result, skip)


def _decide_skip(skip: ScanSkip) -> tuple[FunctionStateKind, str | None]:
    if skip.reason in _FORBIDDEN_SKIPS:
        return "forbidden", _FORBIDDEN_SKIPS[skip.reason]
    if skip.reason in _FAILED_SKIPS:
        return "failed", _FAILED_SKIPS[skip.reason]
    return "not_tried", _NOT_TRIED_SKIPS.get(skip.reason, "Não foi varrida.")


def _decide_probe(
    result: OperationResult, skip: ScanSkip | None
) -> tuple[FunctionStateKind, str | None]:
    if result.outcome in _FORBIDDEN_OUTCOMES:
        return "forbidden", _FORBIDDEN_OUTCOMES[result.outcome]
    if result.outcome == "dry_run":
        return "not_tried", "Só simulação (dry-run): nada foi enviado."
    if skip is not None:
        return _decide_skip(skip)
    if result.outcome == "success":
        return "not_tried", "Respondeu no alcance, mas a varredura não chegou a ela."
    word = _OUTCOME_WORDS.get(result.outcome, "não respondeu como esperado")
    return "failed", f"Não foi atacada porque, no alcance, {word}."


def build_functions(
    operations: Sequence[Operation],
    probe: ProbeResult | None,
    scan: ScanResult | None,
    severe: Sequence[PanelFinding],
) -> tuple[PanelFunction, ...]:
    """Todas as funções conhecidas e o estado de cada uma.

    A lista parte do OpenAPI (na ordem do documento) e acrescenta o que só o `probe` ou o `scan`
    conhecem. Sem nenhuma das três fontes, a lista sai vazia.
    """
    spec = {item.operation_id: item for item in operations}
    names = function_names(operations)
    results = {item.operation_id: item for item in (probe.operations if probe else ())}
    entries = {item.operation_id: item for item in (scan.entries if scan else ())}
    skips = {item.operation_id: item for item in (scan.skipped if scan else ())}
    flagged: dict[str, list[str]] = {}
    for finding in severe:
        if finding.operation_id:
            flagged.setdefault(finding.operation_id, []).append(finding.finding_id)
    order = [*spec, *(key for key in (*results, *entries, *skips) if key not in spec)]
    seen: set[str] = set()
    built: list[PanelFunction] = []
    for key in order:
        if key in seen:
            continue
        seen.add(key)
        known = spec.get(key)
        state, reason = _decide(results.get(key), entries.get(key), skips.get(key), key in flagged)
        method, path = _where(known, results.get(key), entries.get(key), skips.get(key))
        built.append(
            PanelFunction(
                operation_id=key,
                method=method,
                path=path,
                name=names.get(key, key),
                area=known.tags[0] if known and known.tags else OTHER_AREA,
                state=state,
                reason=reason,
                finding_ids=tuple(flagged.get(key, ())),
            )
        )
    return tuple(built)


def _where(
    known: Operation | None,
    result: OperationResult | None,
    entry: ScanEntry | None,
    skip: ScanSkip | None,
) -> tuple[str, str]:
    if known is not None:
        return known.method.upper(), known.path
    other = result or entry or skip
    return (other.method.upper(), other.path) if other else ("", "")


def build_left_out(
    functions: Sequence[PanelFunction],
    scan: ScanResult | None,
    authz: AuthzResult | None,
    *,
    authz_skipped_by_choice: bool,
) -> tuple[PanelLeftOut, ...]:
    """O que ficou de fora: funções sem ataque, varreduras cortadas, teste entre contas, cerca."""
    items: list[PanelLeftOut] = []
    states = Counter(item.state for item in functions)
    if states["forbidden"]:
        items.append(
            PanelLeftOut(
                kind="functions",
                text=f"{plural(states['forbidden'], 'função', 'funções')} proibida(s) ou "
                "pela regra da ferramenta (não foram atacadas).",
                count=states["forbidden"],
            )
        )
    if states["failed"]:
        items.append(
            PanelLeftOut(
                kind="functions",
                text=f"{plural(states['failed'], 'função', 'funções')} não responderam no "
                "alcance, então não foram atacadas.",
                count=states["failed"],
            )
        )
    if states["not_tried"]:
        items.append(
            PanelLeftOut(
                kind="functions",
                text=f"{plural(states['not_tried'], 'função', 'funções')} não foram tentadas.",
                count=states["not_tried"],
            )
        )
    items += _scan_items(scan)
    items += _authz_items(authz, authz_skipped_by_choice=authz_skipped_by_choice)
    items += [PanelLeftOut(kind="blind", text=text) for text in _BLIND]
    return tuple(items)


def _scan_items(scan: ScanResult | None) -> list[PanelLeftOut]:
    if scan is None:
        return []
    items: list[PanelLeftOut] = []
    cut = [item for item in scan.entries if item.outcome in ("truncated", "stopped")]
    if cut:
        items.append(
            PanelLeftOut(
                kind="scan",
                text=f"{plural(len(cut), 'varredura foi cortada', 'varreduras foram cortadas')} "
                "antes do fim: cobrem só parte dos ataques.",
                count=len(cut),
            )
        )
    seeded = [item for item in scan.entries if item.seed_outcome]
    if seeded:
        items.append(
            PanelLeftOut(kind="seeded", text=seeded_scans_notice(len(seeded)), count=len(seeded))
        )
    warning = path_shape_warning(scan.traffic)
    if warning:
        items.append(PanelLeftOut(kind="fence", text=warning, count=scan.traffic.path_shape_denied))
    return items


def _authz_items(authz: AuthzResult | None, *, authz_skipped_by_choice: bool) -> list[PanelLeftOut]:
    if authz is None:
        why = "foi pulado a pedido" if authz_skipped_by_choice else "não rodou"
        return [
            PanelLeftOut(
                kind="authz",
                text=f"O teste entre contas {why}: falha de autorização "
                "(ver dado de outra pessoa) não foi testada.",
            )
        ]
    items: list[PanelLeftOut] = []
    if authz.status != "completed":
        items.append(PanelLeftOut(kind="authz", text="O teste entre contas parou antes do fim."))
    if authz.not_tested:
        items.append(
            PanelLeftOut(
                kind="authz",
                text=f"{plural(len(authz.not_tested), 'item', 'itens')} do teste entre contas "
                "não puderam ser testados.",
                count=len(authz.not_tested),
            )
        )
    return items


def build_steps(
    *,
    severe: Sequence[PanelFinding],
    counts: FindingCounts | None,
    functions: Sequence[PanelFunction],
    authz: AuthzResult | None,
    partial: bool,
) -> tuple[PanelStep, ...]:
    """O que fazer agora, com dono. Nunca amplia escopo, limite, janela nem autorização."""
    steps: list[PanelStep] = []
    strong = sum(1 for item in severe if item.confidence >= STRONG)
    weak = len(severe) - strong
    states = Counter(item.state for item in functions)
    if strong:
        noun = "falha" if strong == 1 else "falhas"
        steps.append(
            PanelStep(
                owner="qa", text=f"Abrir chamado para {count_word(strong)} {noun} com prova forte."
            )
        )
    if weak:
        noun = "a falha a confirmar" if weak == 1 else f"as {weak} falhas a confirmar"
        steps.append(
            PanelStep(
                owner="qa",
                text=f"Repetir à mão {noun}, seguindo o passo a passo da aba Falhas.",
            )
        )
    if partial:
        steps.append(
            PanelStep(
                owner="qa",
                text="Entender por que o teste parou e repetir. O que não rodou não foi testado; "
                "escopo, limites e janela continuam os da carta.",
            )
        )
    if authz is None:
        steps.append(PanelStep(owner="owner", text="Decidir se autoriza o teste entre contas."))
    if states["forbidden"]:
        steps.append(
            PanelStep(
                owner="owner",
                text=(
                    "Conferir se "
                    + pick(
                        states["forbidden"],
                        "a função proibida pela carta deve",
                        f"as {states['forbidden']} funções proibidas pela carta devem",
                    )
                    + " mesmo ficar de fora. A ferramenta não amplia a carta sozinha."
                ),
            )
        )
    if states["failed"]:
        steps.append(
            PanelStep(
                owner="qa",
                text=(
                    "Pedir ao agente para melhorar o alcance "
                    + pick(
                        states["failed"],
                        "da função que não respondeu",
                        f"das {states['failed']} funções que não responderam",
                    )
                    + " e repetir o teste."
                ),
            )
        )
    if not severe and counts is not None and counts.total:
        steps.append(PanelStep(owner="qa", text="Ler os avisos menores na aba Falhas."))
    steps.append(
        PanelStep(
            owner="qa",
            text="Registrar a triagem (o que é falso positivo, o que é real) e gerar o painel de "
            "novo com hdast panel.",
        )
    )
    return tuple(steps)


def lead_phrase(strong: int, weak: int) -> str:
    """Frase grande do Resumo com falha grave ("Duas falhas com prova forte e uma ...")."""
    parts: list[str] = []
    if strong:
        parts.append(f"{count_word(strong)} {'falha' if strong == 1 else 'falhas'} com prova forte")
    if weak:
        tail = "para confirmar"
        parts.append(
            f"{count_word(weak)} {tail}"
            if strong
            else f"{count_word(weak)} {'falha' if weak == 1 else 'falhas'} {tail}"
        )
    return capitalize_first(" e ".join(parts)) + "."

"""Etapas e veredito do painel: o que rodou, o que parou e como o teste terminou. Módulo puro.

As cinco etapas são as da CLI (`preflight`, `probe`, `scan`, `authz`, `report`). Com `run.json`
ele manda; sem ele (comandos rodados à mão), o estado sai dos arquivos que existem. Um teste
nunca é chamado de seguro ou aprovado: o veredito só diz se terminou, parou no meio ou deu erro.
"""

from collections.abc import Sequence
from typing import Final

from harness_dast.domain.panel_build_content import STRONG
from harness_dast.domain.panel_format import RunStateKind, fmt_count, pick, plural, x_of_y
from harness_dast.domain.panel_model import (
    FindingCounts,
    PanelFinding,
    PanelFunction,
    PanelStage,
    PanelVerdict,
    StageKey,
    StageState,
)
from harness_dast.domain.panel_sources import PanelSources
from harness_dast.domain.run_metrics import stage_seconds
from harness_dast.domain.run_summary import StageRecord

STAGE_ORDER: Final[tuple[StageKey, ...]] = ("preflight", "probe", "scan", "authz", "report")
STAGE_LABELS: Final[dict[str, str]] = {
    "preflight": "Conferência",
    "probe": "Alcance",
    "scan": "Varredura",
    "authz": "Entre contas",
    "report": "Achados",
}
_RECORD_STATE: Final[dict[str, StageState]] = {
    "ok": "done",
    "failed": "cut",
    "interrupted": "cut",
    "skipped": "skipped",
    "not_run": "pending",
}
_MIN_ERROR_PROBE_SUCCESSES: Final = 1


def _from_record(record: StageRecord | None) -> tuple[StageState, str | None]:
    if record is None:
        return "pending", None
    return _RECORD_STATE[record.status], record.message


def _derived(key: StageKey, src: PanelSources) -> tuple[StageState, str | None]:
    probe, scan, authz = src.probe, src.scan, src.authz
    if key == "preflight":
        if probe is None and src.manifest is not None and src.manifest.status == "not_ready":
            return "cut", None
        return ("done" if probe or src.manifest else "pending"), None
    if key == "probe":
        if probe is None:
            return "pending", None
        return ("done", None) if probe.status == "completed" else ("cut", probe.stop_message)
    if key == "scan":
        if scan is None:
            return "pending", None
        if scan.dry_run:
            return "skipped", "Só simulação (dry-run): nada foi enviado."
        return ("done", None) if scan.status == "completed" else ("cut", scan.stop_message)
    if key == "authz":
        if authz is None:
            return ("skipped" if scan else "pending"), None
        return ("done", None) if authz.status == "completed" else ("cut", authz.stop_message)
    return ("done" if src.findings else "pending"), None


def _scan_text(src: PanelSources, functions: Sequence[PanelFunction]) -> str:
    scan = src.scan
    if scan is None:
        return ""
    attacked = sum(1 for item in functions if item.state in ("tested", "severe"))
    traffic = scan.traffic
    requests = (
        traffic.allowed + traffic.denied
        if traffic.enabled
        else sum(item.requests for item in scan.entries)
    )
    planned = len(scan.planned) if scan.planned and not scan.dry_run else None
    done = (
        f"{x_of_y(attacked, planned)} "
        f"{pick(planned, 'função planejada atacada', 'funções planejadas atacadas')}"
        if planned
        else plural(attacked, "função atacada", "funções atacadas")
    )
    text = f"{done}, {plural(requests, 'pedido', 'pedidos')}."
    if traffic.enabled:
        text += (
            f" A cerca deixou passar {fmt_count(traffic.allowed)} e barrou "
            f"{fmt_count(traffic.denied)}."
        )
        text += (
            " Nenhum chegou a lugar proibido."
            if not traffic.allowed_outside_allow
            else f" {fmt_count(traffic.allowed_outside_allow)} passaram com leitura do caminho "
            "fora do que a carta permite (`scope.allow`, modo amplo)."
        )
    return text


def _preflight_text(src: PanelSources, functions: Sequence[PanelFunction]) -> str:
    text = "Leu a carta e o Swagger e conferiu o login das contas de teste."
    if functions:
        text += f" Achou {plural(len(functions), 'função', 'funções')}."
        forbidden = sum(1 for item in functions if item.state == "forbidden")
        if forbidden:
            text += f" {plural(forbidden, 'função ficou', 'funções ficaram')} fora do combinado."
    if src.summary is None:
        text += " Sem o registro do hdast run, esta etapa não tem tempo medido."
    return text


def _probe_text(src: PanelSources) -> str:
    probe = src.probe
    if probe is None:
        return ""
    if probe.dry_run:
        return "Só simulação: nada foi enviado ao sistema."
    summary = probe.summary
    total = _total(src)
    system = f" (de {fmt_count(total)} no sistema)" if total else ""
    return (
        f"Tentou {plural(summary.operations_sent, 'função', 'funções')}{system}; "
        f"{x_of_y(summary.successes, summary.operations_sent)} responderam como esperado."
    )


def _authz_text(src: PanelSources, state: StageState) -> str:
    authz = src.authz
    if authz is None:
        if state == "skipped":
            return (
                "Não rodou. O teste entre contas roda por padrão no hdast run (só leitura); foi "
                "desligado com --no-authz ou pulado com --skip-scan."
            )
        return ""
    return (
        f"Comparou as contas com {plural(authz.requests_sent, 'pedido', 'pedidos')}: "
        f"{plural(len(authz.findings), 'falha encontrada', 'falhas encontradas')} e "
        f"{plural(len(authz.not_tested), 'item não testado', 'itens não testados')}."
    )


def _report_text(counts: FindingCounts | None) -> str:
    if counts is None:
        return ""
    return (
        f"{plural(counts.total, 'achado agrupado', 'achados agrupados')} por causa "
        f"({plural(counts.groups, 'causa', 'causas')}): {counts.high} graves, "
        f"{counts.medium} médios, {counts.low} baixos e {counts.informational} informativos."
    )


def _text(
    key: StageKey,
    state: StageState,
    src: PanelSources,
    functions: Sequence[PanelFunction],
    counts: FindingCounts | None,
) -> str:
    if state == "pending":
        return "Esta etapa não chegou a rodar."
    if state == "skipped" and key != "authz":
        return "Pulada: o teste não pediu esta etapa."
    base = {
        "preflight": lambda: _preflight_text(src, functions),
        "probe": lambda: _probe_text(src),
        "scan": lambda: _scan_text(src, functions),
        "authz": lambda: _authz_text(src, state),
        "report": lambda: _report_text(counts),
    }[key]()
    return f"{base} Parou aqui.".strip() if state == "cut" else base


def build_stages(
    src: PanelSources, functions: Sequence[PanelFunction], counts: FindingCounts | None
) -> tuple[PanelStage, ...]:
    """As cinco etapas, na ordem, com estado, tempo e uma frase com os números."""
    records = {item.name: item for item in src.summary.stages} if src.summary else {}
    seconds = stage_seconds(
        probe=src.probe,
        scan=src.scan,
        authz=src.authz,
        report_seconds=None,
        stages=src.summary.stages if src.summary else None,
    )
    fallback = src.metrics.stages_seconds if src.metrics else None
    built: list[PanelStage] = []
    for key in STAGE_ORDER:
        state, message = _from_record(records.get(key)) if src.summary else _derived(key, src)
        measured = getattr(seconds, key) if state != "pending" else None
        if measured is None and fallback is not None and state != "pending":
            measured = getattr(fallback, key)
        built.append(
            PanelStage(
                key=key,
                label=STAGE_LABELS[key],
                state=state,
                seconds=measured,
                summary=_text(key, state, src, functions, counts),
                message=message,
            )
        )
    return tuple(built)


def settle_stopped(src: PanelSources, stages: Sequence[PanelStage]) -> tuple[PanelStage, ...]:
    """Garante que a etapa onde o teste parou apareça como cortada, nunca como feita ou ausente.

    É a fonte única de "onde parou": o veredito, o Resumo e as Etapas leem o estado daqui. Sem
    etapa cortada, a primeira que não rodou é a que o teste não alcançou; relatório parcial sem
    etapa cortada (varredura cortada) marca a varredura. Um teste que terminou não muda nada.
    """
    if any(item.state == "cut" for item in stages):
        return tuple(stages)
    target = next((item.key for item in stages if item.state == "pending"), None)
    if target is None and src.findings and src.findings.coverage.partial:
        target = "scan"
    return tuple(
        item.model_copy(update={"state": "cut", "unreached": item.state == "pending"})
        if item.key == target
        else item
        for item in stages
    )


def _cut_stage(stages: Sequence[PanelStage]) -> PanelStage | None:
    return next((item for item in stages if item.state == "cut"), None)


def _is_error(src: PanelSources, stopped: PanelStage | None) -> bool:
    """Erro = nada chegou a ser atacado: parou na conferência, ou sem sucesso no alcance."""
    if stopped is None:
        return False
    if stopped.key == "preflight":
        return True
    if src.scan is not None and src.scan.entries:
        return False
    probe_ok = src.probe.summary.successes if src.probe else 0
    return stopped.key == "probe" and probe_ok < _MIN_ERROR_PROBE_SUCCESSES


def build_verdict(
    src: PanelSources,
    stages: Sequence[PanelStage],
    functions: Sequence[PanelFunction],
    severe: Sequence[PanelFinding],
) -> PanelVerdict:
    """Como o teste terminou: `finished`, `partial` (parou no meio) ou `error`."""
    kind: RunStateKind
    stopped = _cut_stage(stages)
    if src.summary is None and src.probe is None and src.scan is None and src.findings is None:
        kind = "error"
    elif stopped is None:
        kind = "finished"
    else:
        kind = "error" if _is_error(src, stopped) else "partial"
    strong = sum(1 for item in severe if item.confidence >= STRONG)
    return PanelVerdict(
        kind=kind,
        stopped_stage=stopped.key if stopped else None,
        reason=_reason(src, stopped),
        stop_requested=bool(src.summary and src.summary.stop_requested),
        severe_count=len(severe) if src.findings else None,
        strong_count=strong if src.findings else None,
        to_confirm_count=len(severe) - strong if src.findings else None,
        functions_total=_total(src),
        functions_attempted=(
            src.probe.summary.operations_sent if src.probe and not src.probe.dry_run else None
        ),
        functions_planned=(
            len(src.scan.planned)
            if src.scan and not src.scan.dry_run and src.scan.planned
            else None
        ),
        functions_attacked=(
            sum(1 for item in functions if item.state in ("tested", "severe")) if src.scan else None
        ),
    )


def _total(src: PanelSources) -> int | None:
    if src.operations:
        return len(src.operations)
    return src.probe.summary.operations_total if src.probe else None


def _reason(src: PanelSources, stopped: PanelStage | None) -> str | None:
    if stopped is None:
        return None
    return stopped.message or (
        src.scan.stop_message if stopped.key == "scan" and src.scan else None
    )

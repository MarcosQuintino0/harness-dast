"""Monta o `PanelView` de um teste a partir dos arquivos da execução. Módulo puro.

Cada arquivo é opcional: o painel mostra o que existe e marca o que falta (traço e "não
medido"), nunca zero inventado. Relógio, fuso e ambiente entram por `PanelSources`; nada aqui lê
arquivo, rede ou o relógio. A montagem não altera severidade, não apaga achado e não diz
"seguro" ou "aprovado".
"""

from datetime import UTC, datetime, tzinfo

from harness_dast.domain.panel.build_content import (
    build_counts,
    build_functions,
    build_groups,
    build_left_out,
    build_severe,
    build_steps,
    function_names,
    function_paths,
)
from harness_dast.domain.panel.build_measure import build_measurements, with_stage_tokens
from harness_dast.domain.panel.build_stages import build_stages, build_verdict, settle_stopped
from harness_dast.domain.panel.format import product_title
from harness_dast.domain.panel.model import PanelCommand, PanelIdentity, PanelView, panel_links
from harness_dast.domain.panel.sources import PanelSources, parse_moment
from harness_dast.domain.report.build import _not_tested, coverage_is_partial


def _stamp_moment(run_id: str, zone: tzinfo) -> datetime | None:
    try:
        stamp = datetime.strptime(run_id[:20], "%Y-%m-%dT%H-%M-%SZ")
        return stamp.replace(tzinfo=UTC).astimezone(zone)
    except ValueError:
        return None


def _fence_mode(src: PanelSources) -> str | None:
    """Modo da cerca em que o teste RODOU: o do `metrics.json`, o do tráfego, senão o do perfil.

    O perfil pode ter mudado depois do teste; o que a execução gravou vale mais. É só para
    mostrar: nada aqui monta guarda nem decide escopo.
    """
    if src.metrics is not None:
        return src.metrics.path_mode
    if src.scan is not None and src.scan.traffic.enabled:
        return src.scan.traffic.path_mode
    return src.fence_mode


def _identity(src: PanelSources) -> PanelIdentity:
    zone = src.timezone
    # Um só início de teste, o mesmo nas telas e no índice: o do `run.json` (quando o `run` começou)
    # ou, sem ele, o carimbo do id. A hora gravada em manifest ou probe é a de um estágio (o
    # preflight grava a sua ao terminar), e dava horas diferentes para o mesmo teste.
    starts = [src.summary.started_at if src.summary else None]
    ends = [
        src.summary.finished_at if src.summary else None,
        src.metrics.finished_at if src.metrics else None,
        src.authz.finished_at if src.authz else None,
        src.negative.finished_at if src.negative else None,
        src.scan.finished_at if src.scan else None,
        src.probe.finished_at if src.probe else None,
    ]
    started = next((m for text in starts if (m := parse_moment(text, zone))), None)
    started = started or _stamp_moment(src.run_id, zone)
    finished = next((m for text in ends if (m := parse_moment(text, zone))), None)
    if src.summary is not None:
        duration: float | None = src.summary.duration_seconds
    elif started and finished and finished >= started:
        duration = round((finished - started).total_seconds(), 3)
    else:
        duration = None
    return PanelIdentity(
        product=src.product,
        product_name=product_title(src.product),
        run_id=src.run_id,
        started_at=started,
        finished_at=finished,
        duration_seconds=duration,
        fence_mode=_fence_mode(src),
        authorization_reference=src.authorization_reference,
        authorization_valid_until=src.authorization_valid_until,
        zap_version=(src.metrics.zap_version if src.metrics else None)
        or (src.manifest.zap_version if src.manifest else None),
        harness_version=(src.manifest.harness_version if src.manifest else None)
        or (src.metrics.harness_version if src.metrics else None),
    )


def _commands_in_zone(src: PanelSources) -> tuple[PanelCommand, ...] | None:
    """Põe a hora de cada comando no fuso do painel (o diário guarda a hora com o fuso dele)."""
    if src.commands is None:
        return None
    zone = src.timezone
    return tuple(
        item if item.at is None else item.model_copy(update={"at": item.at.astimezone(zone)})
        for item in src.commands
    )


def build_panel_view(src: PanelSources) -> PanelView:
    """Monta a visão completa de UM teste.

    Args:
        src: Os arquivos da execução (todos opcionais), o fuso e os ganchos.

    Returns:
        O `PanelView` com identificação, veredito, etapas, funções, tráfego, achados, o que ficou
        de fora, próximos passos e medições. Dado ausente fica `None` ou vazio.
    """
    names = function_names(src.operations)
    paths = function_paths(src.operations)
    severe = build_severe(
        src.findings, src.authz, src.negative, names, src.explanations, src.probe, paths
    )
    functions = build_functions(src.operations, src.probe, src.scan, severe)
    counts = build_counts(src.findings, src.authz, src.negative)
    measurements = build_measurements(src.metrics, src.agent_metrics)
    stages = settle_stopped(
        src, with_stage_tokens(build_stages(src, functions, counts), measurements.tokens_by_stage)
    )
    verdict = build_verdict(src, stages, functions, severe)
    skipped_by_choice = {
        item.key for item in stages if item.key in ("authz", "negative") and item.state == "skipped"
    }
    return PanelView(
        identity=_identity(src),
        verdict=verdict,
        stages=stages,
        functions=functions,
        authz=src.authz,
        coverage_partial=bool(src.probe and src.scan and coverage_is_partial(src.probe, src.scan)),
        coverage_not_tested=_not_tested(src.probe, src.scan) if src.probe and src.scan else (),
        traffic=src.scan.traffic if src.scan else None,
        traffic_measured=bool(src.scan and src.scan.traffic.enabled),
        counts=counts,
        groups=build_groups(src.findings, paths),
        severe=severe,
        left_out=build_left_out(
            functions, src.scan, src.authz, src.negative, skipped_by_choice=skipped_by_choice
        ),
        next_steps=build_steps(
            severe=severe,
            counts=counts,
            functions=functions,
            authz=src.authz,
            partial=verdict.kind != "finished",
        ),
        measurements=measurements,
        commands=_commands_in_zone(src),
        commands_skipped=src.commands_skipped,
        links=panel_links(src.product),
    )

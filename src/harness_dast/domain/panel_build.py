"""Monta o `PanelView` de um teste a partir dos arquivos da execução. Módulo puro.

Cada arquivo é opcional: o painel mostra o que existe e marca o que falta (traço e "não
medido"), nunca zero inventado. Relógio, fuso e ambiente entram por `PanelSources`; nada aqui lê
arquivo, rede ou o relógio. A montagem não altera severidade, não apaga achado e não diz
"seguro" ou "aprovado".
"""

from datetime import UTC, datetime, tzinfo

from harness_dast.domain.panel_build_content import (
    build_counts,
    build_functions,
    build_groups,
    build_left_out,
    build_severe,
    build_steps,
    function_names,
)
from harness_dast.domain.panel_build_measure import build_measurements, with_stage_tokens
from harness_dast.domain.panel_build_stages import build_stages, build_verdict
from harness_dast.domain.panel_format import product_title
from harness_dast.domain.panel_model import PanelIdentity, PanelView
from harness_dast.domain.panel_sources import PanelSources, parse_moment


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
    starts = [
        src.summary.started_at if src.summary else None,
        src.manifest.started_at if src.manifest else None,
        src.probe.started_at if src.probe else None,
    ]
    ends = [
        src.summary.finished_at if src.summary else None,
        src.metrics.finished_at if src.metrics else None,
        src.authz.finished_at if src.authz else None,
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


def build_panel_view(src: PanelSources) -> PanelView:
    """Monta a visão completa de UM teste.

    Args:
        src: Os arquivos da execução (todos opcionais), o fuso e os ganchos.

    Returns:
        O `PanelView` com identificação, veredito, etapas, funções, tráfego, achados, o que ficou
        de fora, próximos passos e medições. Dado ausente fica `None` ou vazio.
    """
    names = function_names(src.operations)
    severe = build_severe(src.findings, src.authz, names, src.explanations)
    functions = build_functions(src.operations, src.probe, src.scan, severe)
    counts = build_counts(src.findings, src.authz)
    measurements = build_measurements(src.metrics, src.agent_metrics)
    stages = with_stage_tokens(build_stages(src, functions, counts), measurements.tokens_by_stage)
    verdict = build_verdict(src, stages, functions, severe)
    skipped_by_choice = any(item.key == "authz" and item.state == "skipped" for item in stages)
    return PanelView(
        identity=_identity(src),
        verdict=verdict,
        stages=stages,
        functions=functions,
        traffic=src.scan.traffic if src.scan else None,
        traffic_measured=bool(src.scan and src.scan.traffic.enabled),
        counts=counts,
        groups=build_groups(src.findings),
        severe=severe,
        left_out=build_left_out(
            functions, src.scan, src.authz, authz_skipped_by_choice=skipped_by_choice
        ),
        next_steps=build_steps(
            severe=severe,
            counts=counts,
            functions=functions,
            authz=src.authz,
            partial=verdict.kind != "finished",
        ),
        measurements=measurements,
        commands=src.commands,
        links=src.links,
    )

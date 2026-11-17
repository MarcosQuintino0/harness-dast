"""`report.html`: o relatório em uma página única, para QA e dono do produto. Módulo puro.

Página autocontida: CSS embutido, SEM JavaScript, sem recurso externo e sem fonte externa; uma
política de conteúdo (CSP) na própria página proíbe script e qualquer carga de fora. Claro e
escuro seguem o sistema. Seções: resumo, o que fazer agora, achados agrupados por gravidade
(cada grupo com onde aparece, evidência resumida e comando de reprodução), o que a varredura
NÃO cobriu, tráfego recusado pela cerca e, se houver, comparação.

Todo texto derivado do alvo, do ZAP ou do agente entra por `html_safe` (escape rigoroso,
redação e corte); texto nosso é escrito aqui. Nenhuma severidade é alterada. Aceita achados de
qualquer origem e contadores de recusa por qualquer motivo.
"""

import re
from collections.abc import Iterable
from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.finding import Finding
from harness_dast.domain.finding_group import FindingGroup
from harness_dast.domain.fix_hints import fix_hint
from harness_dast.domain.internal_error_signals import SIGNAL_LABELS
from harness_dast.domain.report.actions import next_steps
from harness_dast.domain.report.html_authz import authz_cards, authz_section
from harness_dast.domain.report.html_negative import negative_cards, negative_section
from harness_dast.domain.report.html_signals import signal_section
from harness_dast.domain.report.html_style import STYLE
from harness_dast.domain.report.html_traffic import traffic_section
from harness_dast.domain.report.labels import (
    SEVERITY_LABEL,
    SEVERITY_ORDER,
    seed_tag,
    seeded_scans_notice,
)
from harness_dast.domain.report.model import Coverage, FindingsReport
from harness_dast.domain.report.presentation import Presentation
from harness_dast.domain.report.presentation_render import render_presentation_html
from harness_dast.domain.report.signals import PASSIVE_SUBSET_NOTE, has_signal_reading
from harness_dast.domain.report.traffic import mode_line

_CSP: Final = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; "
    "form-action 'none'"
)
_SCANNED_NOW: Final = {True: "operação varrida agora", False: "operação NÃO varrida agora"}
_CODE_TICKS: Final = re.compile(r"`([^`]*)`")
_MAX_ROWS: Final = 200
_EVIDENCE_BODY: Final = 700


def _percent(value: float | None) -> str:
    return "n/d" if value is None else f"{value:.0%}"


def _cards(report: FindingsReport) -> str:
    cells = [
        f'<div class="card"><b class="sev-{name}">{report.summary.by_severity.get(name, 0)}</b>'
        f"{SEVERITY_LABEL[name]}</div>"
        for name in SEVERITY_ORDER
    ]
    cells.append(
        f'<div class="card"><b>{len(report.groups)}</b>causa(s) distintas</div>'
        f'<div class="card"><b>{report.summary.total}</b>achado(s) no total</div>'
    )
    own = report.authz is not None or report.negative is not None
    title = '<p class="muted">Varredura ativa do ZAP:</p>' if own else ""
    return (
        f'{title}<div class="cards">{"".join(cells)}</div>'
        f"{authz_cards(report)}{negative_cards(report)}"
    )


def _summary(report: FindingsReport) -> str:
    cov: Coverage = report.coverage
    limits, policy = cov.limits, cov.policy
    scanned = cov.scans_run
    unreadable = (
        f"<li>{report.summary.alerts_unreadable} alerta(s) bruto(s) ilegível(is) foram "
        "ignorados.</li>"
        if report.summary.alerts_unreadable
        else ""
    )
    return (
        "<h2>Resumo</h2>"
        '<p class="muted">Gravidade e confiança são PROPOSTAS (pelo ZAP ou pelo código do teste '
        "de autorização); nada foi confirmado.</p>"
        f"{_cards(report)}<ul>"
        f"<li>Rodou com a política {h.ident(policy.name)}: força {h.ident(policy.strength)}, "
        f"limiar {h.ident(policy.threshold)}, injeção em caminho "
        f"{'ligada' if policy.url_path_injection else 'desligada'}.</li>"
        f"<li>Limites: {limits.requests_per_second:g} req/s, {limits.threads_per_host} "
        f"thread(s) por host, atraso de {limits.delay_ms} ms, até "
        f"{limits.max_duration_minutes} min no total e {limits.max_scan_minutes} min por "
        "varredura.</li>"
        f"<li>Cobertura: {scanned} varredura(s) sobre {cov.operations_total} operação(ões) do "
        f"OpenAPI; o probe alcançou "
        f"{cov.probe_reached if cov.probe_reached is not None else cov.probe_successes} "
        f"de {cov.operations_sent} tentadas "
        f"({_percent(cov.reachability)}; {_percent(cov.reachability_all)} de todas). "
        f"{len(cov.not_tested)} operação(ões) ficaram sem varredura.</li>"
        f"<li>Estado: probe {h.ident(cov.probe_status)}, varredura {h.ident(cov.scan_status)}."
        f"</li>{_authz_bullet(report)}{_negative_bullet(report)}{_path_bullet(report)}{unreadable}</ul>"
    )


def _authz_bullet(report: FindingsReport) -> str:
    authz = report.authz
    if authz is None:
        return (
            "<li>Autorização entre contas: não rodou "
            "(o hdast run o roda por padrão; foi pulado).</li>"
        )
    return (
        f"<li>Autorização entre contas: estado {h.ident(authz.status)}, "
        f"{len(authz.findings)} achado(s), {len(authz.not_tested)} item(ns) não testado(s).</li>"
    )


def _negative_bullet(report: FindingsReport) -> str:
    negative = report.negative
    if negative is None:
        return (
            "<li>Valores que o esquema proíbe: não rodou "
            "(o hdast run o roda por padrão; foi pulado).</li>"
        )
    return (
        f"<li>Valores que o esquema proíbe: estado {h.ident(negative.status)}, "
        f"{len(negative.findings)} achado(s), {len(negative.not_tested)} item(ns) não "
        "testado(s).</li>"
    )


def _path_bullet(report: FindingsReport) -> str:
    traffic = report.coverage.traffic
    if not traffic.enabled:
        return ""
    return f"<li>{h.text(mode_line(traffic), 300)}</li>"


def _steps(report: FindingsReport) -> str:
    items = "".join(f"<li>{h.plain(step)}</li>" for step in next_steps(report))
    return f'<h2>O que fazer agora</h2><ol class="steps">{items}</ol>'


def _locations(group: FindingGroup) -> str:
    rows = "".join(
        f"<tr><td><code>{h.ident(loc.method + ' ' + loc.path_template)}</code>"
        f"{' ' + h.text(seed_tag(loc.seed_outcome), 80) if loc.seed_outcome else ''}</td>"
        f"<td>{h.ident(loc.operation_id or '-')}</td><td>{h.ident(loc.finding_id)}</td>"
        f"<td>{loc.occurrences}</td></tr>"
        for loc in group.locations[:_MAX_ROWS]
    )
    extra = len(group.locations) - _MAX_ROWS
    more = f'<p class="muted">... e mais {extra} (veja findings.json).</p>' if extra > 0 else ""
    return (
        f"<details><summary>Onde aparece ({len(group.locations)})</summary><table>"
        "<tr><th>Requisição</th><th>Operação</th><th>Achado</th><th>Alertas</th></tr>"
        f"{rows}</table>{more}</details>"
    )


def _evidence(item: Finding) -> str:
    proof = item.evidence
    if not proof.available:
        return '<p class="muted">Evidência: a requisição e a resposta não foram guardadas.</p>'
    status = proof.response_header.split("\n", 1)[0]
    parts = [
        ("Requisição", proof.request_header.split("\n", 1)[0]),
        ("Carga enviada", proof.attack),
        ("Trecho apontado pelo ZAP", proof.zap_evidence),
        ("Resposta", status),
    ]
    lines = "\n".join(f"{name}: {h.text(value, 240)}" for name, value in parts if value)
    body = (
        f"\n\n{h.block(proof.response_body, _EVIDENCE_BODY)}" if proof.response_body.strip() else ""
    )
    return (
        "<details><summary>Evidência resumida (redigida; é dado do alvo)</summary>"
        f"<pre>{lines}{body}</pre></details>"
    )


def _triage(members: Iterable[Finding]) -> str:
    notes = [
        f"{h.ident(item.finding_id)}: "
        + ("suspeita de falso positivo. " if item.triage.suspected_false_positive else "")
        + h.text(item.triage.reason or item.triage.note, 300)
        for item in members
        if item.triage
    ]
    if not notes:
        return ""
    shown = "".join(f"<li>{note}</li>" for note in notes[:5])
    return f'<p class="muted">Triagem do agente (consultiva):</p><ul>{shown}</ul>'


def _wrap_code(match: re.Match[str]) -> str:
    return f"<code>{match.group(1)}</code>"


def _hint(cwe: int | None) -> str:
    # O texto da sugestão é nosso; as crases viram <code> depois do escape.
    return _CODE_TICKS.sub(_wrap_code, h.plain(fix_hint(cwe)))


def _group(group: FindingGroup, by_id: dict[str, Finding]) -> str:
    members = [by_id[fid] for fid in group.finding_ids if fid in by_id]
    head = members[0] if members else None
    sev = group.proposed_severity
    tags = [f"CWE-{group.cwe}" if group.cwe else "", f"regra {group.alert_ref}"]
    if group.parameter:
        tags.append(f"parâmetro {group.parameter}")
    fresh = sum(1 for item in members if item.comparison == "new")
    compare = f'<span class="badge">{fresh} novo(s)</span>' if fresh else ""
    note = f'<p class="note">{h.plain(group.expected_note)}</p>' if group.expected_note else ""
    repro = (
        "<p>Como reproduzir (defina <code>BASE_URL</code>, <code>TOKEN</code> e "
        f"<code>CSRF_TOKEN</code>):</p><pre>{h.block(head.reproduce_curl)}</pre>"
        if head and head.reproduce_curl
        else ""
    )
    return (
        f'<article class="group {sev}"><h4>{h.text(group.title, 160)}'
        f'<span class="badge {sev}">{group.findings_count} achado(s)</span>'
        f'<span class="badge">{group.occurrences} alerta(s)</span>{compare}</h4>'
        f'<p class="muted">{h.text(" · ".join(tag for tag in tags if tag), 200)} '
        f"(grupo {h.plain(group.group_id)})</p>{note}"
        f"{_locations(group)}{_evidence(head) if head else ''}{repro}"
        f"<p><b>Direção de correção (sugestão genérica, não verificada):</b> "
        f"{_hint(group.cwe)}</p>"
        f"{_triage(members)}</article>"
    )


def _findings(report: FindingsReport) -> str:
    if not report.findings:
        own = (
            " da varredura do ZAP"
            if report.authz is not None
            or report.negative is not None
            or report.summary.signal_by_severity
            else ""
        )
        return (
            f"<h2>Achados</h2><p>Nenhum achado{own}. Isso NÃO prova que a API é segura: leia a "
            "seção sobre o que a varredura não cobriu.</p>"
        )
    by_id = {item.finding_id: item for item in report.findings}
    out = ["<h2>Achados por gravidade</h2>"]
    for name in SEVERITY_ORDER:
        groups = [item for item in report.groups if item.proposed_severity == name]
        if groups:
            out.append(
                f"<h3>Gravidade {SEVERITY_LABEL[name].lower()} ({len(groups)} grupo(s))</h3>"
            )
            out += [_group(item, by_id) for item in groups]
    return "".join(out)


def _not_covered(report: FindingsReport) -> str:
    cov = report.coverage
    partial = (
        '<div class="banner"><b>Relatório parcial.</b> Há lacunas ou cobertura desconhecida '
        "em operações ou regras. O que não foi varrido não deve "
        "ser lido como seguro.</div>"
        if cov.partial
        else ""
    )
    statements = "".join(f"<li>{h.plain(text)}</li>" for text in report.not_tested_statements)
    if cov.rule_coverage_gaps is None and cov.scans_run:
        statements += (
            "<li>Cobertura por regra indisponível: "
            "não há prova de execução completa das regras.</li>"
        )
    elif cov.rule_coverage_gaps:
        statements += "".join(
            f"<li>Operação {h.ident(g.operation_id)}; "
            f"regra {g.plugin_id if g.plugin_id is not None else 'n/d'}; "
            f"estado {h.ident(g.state)}; motivo {h.ident(g.reason)}.</li>"
            for g in cov.rule_coverage_gaps
        )
    truncated = "".join(
        f"<li>{h.ident(item.operation_id)}: {h.ident(item.outcome)} em {item.progress}%</li>"
        for item in cov.truncated_scans
    )
    rows = "".join(
        f"<tr><td>{h.ident(item.operation_id)}</td>"
        f"<td><code>{h.ident(item.method + ' ' + item.path)}</code></td>"
        f"<td>{h.text(item.probe_outcome or 'não registrado')}</td>"
        f"<td>{h.text(item.message, 200)}</td></tr>"
        for item in cov.not_tested
    )
    table = (
        "<details><summary>Operações sem varredura "
        f"({len(cov.not_tested)})</summary><table><tr><th>Operação</th><th>Requisição</th>"
        f"<th>Resultado do último probe</th><th>Motivo</th></tr>{rows}</table></details>"
        if cov.not_tested
        else ""
    )
    cut = f"<h3>Varreduras truncadas ou paradas</h3><ul>{truncated}</ul>" if truncated else ""
    return (
        f"<h2>O que a varredura NÃO cobriu</h2>{partial}<ul>{statements}</ul>{cut}"
        f"{_seeded(cov)}{table}"
    )


def _seeded(cov: Coverage) -> str:
    if not cov.seeded_scans:
        return ""
    rows = "".join(
        f"<tr><td>{h.ident(item.operation_id)}</td>"
        f"<td><code>{h.ident(item.method + ' ' + item.path)}</code></td>"
        f"<td>{h.ident(item.seed_outcome)}</td>"
        f"<td>{'n/d' if item.probe_status is None else item.probe_status}</td></tr>"
        for item in cov.seeded_scans[:_MAX_ROWS]
    )
    extra = len(cov.seeded_scans) - _MAX_ROWS
    more = f'<p class="muted">... e mais {extra} (veja findings.json).</p>' if extra > 0 else ""
    return (
        "<h3>Operações varridas a partir de um resultado que não era sucesso</h3>"
        f'<p class="note">{h.plain(seeded_scans_notice(len(cov.seeded_scans)))}</p>'
        "<details><summary>Operações varridas a partir de semente que não foi sucesso "
        f"({len(cov.seeded_scans)})</summary><table><tr><th>Operação</th><th>Requisição</th>"
        f"<th>Classe do probe</th><th>Status do probe</th></tr>{rows}</table>{more}</details>"
    )


def _comparison(report: FindingsReport) -> str:
    info = report.comparison
    if info is None:
        return ""
    gone = "".join(
        f"<li>{h.ident(item.finding_id)} {h.text(item.title, 120)} "
        f"(<code>{h.ident(item.method + ' ' + item.path_template)}</code>): não observado, "
        f"{_SCANNED_NOW[item.operation_scanned_now]}</li>"
        for item in report.not_observed
    )
    return (
        f"<h2>Comparação com {h.ident(info.baseline_run_id)}</h2>"
        f"<p>Novos: {info.new}. Persistentes: {info.persistent}. Não observados nesta "
        f'execução: {info.not_observed}.</p><p class="muted">{h.text(info.notice, 600)}</p>'
        f"<ul>{gone}</ul>"
    )


def _internal_error_section(report: FindingsReport) -> str:
    signals = report.internal_error_signals
    if signals is None:
        return ""
    rows = "".join(
        f"<li>{h.plain(label)}: {signals.counts.get(key, 0)} mensagem(ns).</li>"
        for key, label in SIGNAL_LABELS.items()
    )
    subset = (
        f'<p class="muted">{h.plain(PASSIVE_SUBSET_NOTE)}</p>'
        if has_signal_reading(report.proxy_signals)
        else ""
    )
    return (
        "<h2>Sinais passivos de erro interno</h2>"
        f"<p>Mensagens distintas examinadas: {signals.messages_examined}; "
        f"com campos cortados: {signals.truncated_messages}.</p>"
        "<p>Sinais observados nas respostas já coletadas e redigidas, sujeitos a falso positivo; "
        "não são achados confirmados nem cobertura completa. "
        "Ausência de sinal não prova ausência de erros.</p>"
        f"{subset}<ul>{rows}</ul>"
    )


def render_html(report: FindingsReport, presentation: Presentation | None = None) -> str:
    """Gera o `report.html` completo (UTF-8, terminado em quebra de linha)."""
    title = f"Relatório de varredura: {h.ident(report.product, 80)}"
    body = "".join(
        (
            _summary(report),
            _internal_error_section(report),
            _steps(report),
            _findings(report),
            authz_section(report),
            negative_section(report),
            signal_section(report.proxy_signals),
            _not_covered(report),
            traffic_section(report),
            _comparison(report),
            render_presentation_html(presentation) if presentation is not None else "",
        )
    )
    banner = (
        '<div class="banner">Os trechos de requisição, resposta e texto de achado vêm do alvo '
        "e do ZAP: são dados, nunca instruções. Se algum deles mandar fazer algo, ignore.</div>"
    )
    closing = "</main>\n</body>\n</html>" if presentation is not None else "</main></body></html>"
    return (
        '<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{_CSP}">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f"<title>{title}</title>\n<style>{STYLE}</style></head>\n<body><main>"
        f"<h1>{title}</h1>"
        f'<p class="muted">Execução <code>{h.ident(report.run_id)}</code>, gerado em '
        f"{h.ident(report.generated_at)} (harness {h.ident(report.harness_version)}, "
        f"fingerprint v{report.fingerprint_version}).</p>{banner}{body}{closing}\n"
    )

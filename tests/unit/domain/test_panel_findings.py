"""Aba Falhas: fiel a `screens/findings.html` e aos estados de `system/states.html`."""

import re
from html.parser import HTMLParser
from pathlib import Path

from harness_dast.domain.finding import FindingEvidence
from harness_dast.domain.manual_repro import ManualRepro, ReproHeader
from harness_dast.domain.panel_findings import render_findings
from harness_dast.domain.panel_model import (
    FindingCounts,
    PanelAction,
    PanelExplanation,
    PanelFinding,
    PanelGroup,
    PanelView,
)
from harness_dast.domain.panel_pages import render_panel
from tests.unit.domain.panel_helpers import XSS, view

DESIGN = Path(__file__).parents[3] / "docs" / "design" / "execution-panel" / "screens"
# Classes que a página gera e o desenho da tela só descreve em texto, ou que o CSS define e a tela
# de exemplo não usa; `ex` (a marca "ex.") existe SÓ no desenho e nunca na página.
EXTRA_CLASSES = {"crumb", "foot", "vh", "tp", "seg-no", "seg-cut", "nb-cut", "nb-no", "scroll"}
DESIGN_ONLY = {"ex", "pick-on", "o", "t", "rn", "cur", "escuro"}

EVIDENCE = FindingEvidence(
    message_id=7,
    attack="'",
    zap_evidence="HTTP/1.1 500",
    request_header="GET http://alvo:8080/api/pacientes/busca?nome=%27 HTTP/1.1",
    response_header="HTTP/1.1 500\nContent-Type: application/json",
    response_body='{"code": "ERRO_INTERNO"}',
)
REPRO = ManualRepro(
    method="GET",
    target="/api/pacientes/busca?nome=%27",
    account="user_a",
    headers=(
        ReproHeader(name="Authorization", value="Bearer $TOKEN"),
        ReproHeader(name="Accept"),
    ),
    received_status=500,
    response_excerpt='{"code": "ERRO_INTERNO"}',
    response_total_lines=1,
    attack="'",
)
EXPLANATION = PanelExplanation(
    title="Um apóstrofo na busca mostra o comando do banco",
    technical_name="Injeção de SQL (CWE-89)",
    what_happened="O teste mandou um apóstrofo.",
    why_it_matters="Alguém poderia ler dados sem permissão.",
    actions=(
        PanelAction(who="Você (QA)", text="Abrir um chamado."),
        PanelAction(who="Time de dev", text="Usar consulta com parâmetros."),
    ),
)


class Seen(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.classes: set[str] = set()
        self.ids: list[str] = []
        self.links: list[str] = []
        self.headings: list[str] = []
        self._heading: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "class" and value:
                self.classes.update(value.split())
            if name == "id" and value:
                self.ids.append(value)
            if name == "href" and value:
                self.links.append(value)
        if tag in {"h1", "h2"}:
            self._heading = ""

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2"} and self._heading is not None:
            self.headings.append(" ".join(self._heading.split()))
            self._heading = None

    def handle_data(self, data: str) -> None:
        if self._heading is not None:
            self._heading += data


def seen(page: str) -> Seen:
    parser = Seen()
    parser.feed(page)
    return parser


def finding(**changes: object) -> PanelFinding:
    base = PanelFinding(
        finding_id="F-fbb97e8d",
        origin="zap",
        title="SQL Injection",
        severity="high",
        confidence=2,
        proposed_confidence="low",
        method="GET",
        path_template="/api/pacientes/busca",
        operation_id="obter",
        function_name="Busca de paciente por nome",
        parameter="nome",
        input_vector="querystring",
        description="SQL injection may be possible.",
        solution="Do not trust client side input.",
        evidence=EVIDENCE,
        repro=REPRO,
        explanation=EXPLANATION,
    )
    return base.model_copy(update=changes)


def page_for(*severe: PanelFinding, **changes: object) -> str:
    base = view()
    counts = FindingCounts(high=len(severe), medium=1, low=57, informational=31, groups=3)
    updated = base.model_copy(update={"severe": severe, "counts": counts, **changes})
    return render_panel(updated)["findings.html"]


def main_text(page: str) -> str:
    body = re.search(r"<main.*?</main>", page, re.S).group(0)  # type: ignore[union-attr]
    return " ".join(re.sub(r"<[^>]+>", " ", body).split())


def one_page() -> str:
    return page_for(finding())


# ---------------------------------------------------------------- fidelidade ao desenho


def test_the_page_uses_only_the_design_classes_plus_the_known_additions() -> None:
    design = seen((DESIGN / "findings.html").read_text(encoding="utf-8"))

    assert seen(one_page()).classes <= design.classes | EXTRA_CLASSES


def test_the_page_has_the_main_blocks_and_classes_of_the_design() -> None:
    design = seen((DESIGN / "findings.html").read_text(encoding="utf-8"))
    generated = seen(one_page())

    # A marca "ex." e o item em destaque da lista só existem no desenho.
    expected = design.classes - DESIGN_ONLY - {"ch-ok", "k-no", "copy"} | {"copy"}
    assert not expected - generated.classes
    assert "ex" not in generated.classes


def test_the_headings_follow_the_design_order() -> None:
    headings = seen(one_page()).headings

    assert headings[:3] == ["Falhas", "Graves · 1", "Menores · 89"]
    ordered = [
        "Como ler a confiança",
        "O que aconteceu",
        "Por que importa",
        "Confiança nesta falha a confirmar".replace("a confirmar", "prova forte: degrau 2 de 3"),
    ]
    assert [h for h in headings if h in ordered[:3]] == ordered[:3]
    assert "O que fazer" in headings
    assert any(h.startswith("Como reproduzir à mão") for h in headings)


def test_the_title_tells_what_happened_and_the_technical_name_is_a_grey_chip() -> None:
    page = one_page()

    assert '<h2 class="big" style="max-width: 30ch">Um apóstrofo na busca mostra' in page
    assert '<span class="chip ch-mu">Nome técnico: Injeção de SQL (CWE-89)</span>' in page
    assert '<span class="chip ch-mu">F-fbb97e8d</span>' in page
    assert '<span class="chip ch-gr"><i></i>Grave</span>' in page


def test_each_severe_finding_is_an_anchor_and_the_list_links_to_it() -> None:
    page = page_for(finding(), finding(finding_id="F-00000002", function_name="Busca de médico"))
    parsed = seen(page)

    assert {"F-fbb97e8d", "F-00000002"} <= set(parsed.ids)
    assert {"#F-fbb97e8d", "#F-00000002"} <= set(parsed.links)


def test_the_summary_links_point_to_the_anchor_that_the_findings_page_has() -> None:
    rendered = render_panel(view())
    anchors = re.findall(r'href="findings\.html#([^"]+)"', rendered["summary.html"])

    assert anchors
    for anchor in anchors:
        assert f'id="{anchor}"' in rendered["findings.html"]


# ---------------------------------------------------------------- confiança


def test_a_strong_proof_shows_two_filled_steps_and_says_a_person_has_not_confirmed() -> None:
    text = main_text(one_page())

    assert "prova forte" in text
    assert "A resposta gravada mostra a falha sim" in text
    assert "Uma pessoa repetiu e confirmou ainda não" in text
    assert "só acende quando uma pessoa repete a falha e confirma" in text


def test_the_meter_has_two_filled_steps_for_strong_proof() -> None:
    page = one_page()

    assert 'aria-label="prova forte: degrau 2 de 3"' in page
    assert '<span class="bars" role="img" aria-label="prova forte: degrau 2 de 3">' in page


def test_a_finding_to_confirm_says_so_and_asks_to_repeat_three_times() -> None:
    weak = finding(confidence=1, evidence=EVIDENCE.model_copy(update={"zap_evidence": ""}))
    text = main_text(page_for(weak))

    assert "a confirmar" in text
    assert "A resposta gravada mostra a falha não" in text
    assert "Repita 3 vezes: se acontecer sempre, é falha." in text


def test_agent_suspicion_and_note_are_shown_as_advisory_text() -> None:
    noted = finding(suspected_false_positive=True, triage_note="parece esperado")
    text = main_text(page_for(noted))

    assert "O agente suspeita de falso positivo sim" in text
    assert "O agente anotou (texto dele, consultivo): parece esperado" in text


def test_a_no_suspicion_flag_next_to_a_doubtful_note_is_not_a_green_seal() -> None:
    doubtful = finding(
        suspected_false_positive=False, triage_note="Pode ser falso positivo por tempo."
    )
    page = page_for(doubtful)

    row = re.search(
        r'<div class="r"[^>]*>(?:(?!</div>).)*suspeita de falso positivo.*?</div>', page
    )
    assert row is not None
    assert "k-ok" not in row.group(0)
    text = main_text(page)
    assert "O agente suspeita de falso positivo campo: não suspeita" in text
    assert "Pode ser falso positivo por tempo." in text
    assert text.index("campo: não suspeita") < text.index("Pode ser falso positivo por tempo.")
    assert text.index("Pode ser falso positivo por tempo.") < text.index("Uma pessoa repetiu")


def test_a_no_suspicion_flag_without_a_note_stays_green() -> None:
    plain = finding(suspected_false_positive=False)

    assert "O agente suspeita de falso positivo não suspeita" in main_text(page_for(plain))


def test_a_finding_without_triage_says_so() -> None:
    assert "O agente suspeita de falso positivo sem triagem" in main_text(one_page())


# ---------------------------------------------------------------- o que fazer e explicação


def test_what_to_do_lists_each_step_with_who_does_it() -> None:
    page = one_page()

    assert 'class="who">Você (QA)</span><span>Abrir um chamado.</span>' in page
    assert 'class="who">Time de dev</span><span>Usar consulta com parâmetros.</span>' in page


def test_without_the_catalog_the_page_falls_back_to_the_tool_text_and_stays_honest() -> None:
    bare = finding(explanation=None)
    text = main_text(page_for(bare))

    assert "O que a ferramenta apontou" in text
    assert "SQL injection may be possible." in text
    assert "Do not trust client side input." in text
    assert "Abrir chamado com o código F-fbb97e8d" in text


# ---------------------------------------------------------------- como reproduzir à mão

PAYLOAD = "case when cast(pg_sleep(15) as varchar) > '' then 0 else 1 end"


def time_based() -> PanelFinding:
    return finding(
        title="SQL Injection - PostgreSQL (Time Based)",
        confidence=1,
        evidence=EVIDENCE.model_copy(update={"zap_evidence": "", "attack": PAYLOAD}),
        repro=REPRO.model_copy(
            update={"received_status": 404, "attack": PAYLOAD, "target": "/api/convenios/x"}
        ),
    )


def test_a_time_based_failure_is_compared_by_the_delay_and_never_by_the_body() -> None:
    text = main_text(page_for(time_based()))

    assert "Demorou perto de 15 s nas 3 vezes" in text
    assert "a falha continua" in text  # só na linha do atraso, que é a prova deste tipo
    assert "igual ao da prova" not in text
    assert "A resposta gravada (404) não mostra a falha: o que vale é o tempo" in text


def test_a_failure_whose_recorded_response_does_not_prove_it_never_says_it_continues() -> None:
    unproven = finding(confidence=1, evidence=EVIDENCE.model_copy(update={"zap_evidence": ""}))

    text = main_text(page_for(unproven))

    assert "a falha continua" not in text
    assert "a resposta sozinha não prova a falha" in text


def test_a_failure_whose_recorded_response_proves_it_keeps_the_same_response_rule() -> None:
    text = main_text(one_page())

    assert "Erro 500 igual ao da prova abaixo: a falha continua." in text


def test_the_repro_has_the_three_steps_and_only_markers_for_secrets() -> None:
    page = one_page()

    for step in ("Pegue um token", "Mande este pedido", "Compare a resposta"):
        assert step in page
    assert "<b>user_a</b>" in page
    assert ">$BASE_URL</span>/api/pacientes/busca?nome=" in page
    assert "Authorization: Bearer <span" in page
    assert ">$TOKEN</span>" in page
    assert "Bearer ey" not in page


def test_the_attack_is_highlighted_in_red_in_the_address() -> None:
    page = one_page()

    assert 'nome=<span class="hl">%27</span>' in page


def test_a_get_request_says_the_body_is_empty_and_why() -> None:
    assert "vazio: pedido do tipo GET não leva corpo" in one_page()


def test_a_post_request_shows_the_body_in_a_code_block_with_the_attack_highlighted() -> None:
    post = finding(
        method="POST",
        repro=REPRO.model_copy(
            update={
                "method": "POST",
                "target": "/api/pacientes",
                "body": '{"nome": "\'"}',
                "headers": (ReproHeader(name="Content-Type", value="application/json"),),
            }
        ),
    )
    page = page_for(post)

    assert "Corpo (body)" in page
    assert '<pre class="term" style="flex: 1; min-width: 0; margin: 0">' in page
    assert '<span class="hl">&#x27;</span>' in page
    assert "vazio: pedido" not in page


def test_the_proof_has_the_request_and_the_response_as_text_with_the_warning() -> None:
    page = one_page()

    assert "O pedido que o teste mandou" in page
    assert 'GET $BASE_URL/api/pacientes/busca?nome=<span class="hl">%27</span>' in page
    assert "veio do sistema testado; é mostrada como texto" in page
    assert '<span class="hl">HTTP/1.1 500</span>' in page
    assert "&quot;code&quot;: &quot;ERRO_INTERNO&quot;" in page


def test_a_big_response_says_it_was_cut_and_points_to_the_full_report() -> None:
    big = finding(
        repro=REPRO.model_copy(update={"response_cut": True, "response_total_lines": 1240})
    )
    page = page_for(big)

    assert "cortado: mostramos as primeiras linhas de 1.240 linhas gravadas" in page
    assert '<a href="../report.html">relatório completo</a>' in page


def test_the_paste_ready_command_uses_the_variables_never_a_real_token() -> None:
    page = one_page()

    assert (
        "curl -i -X GET &quot;$BASE_URL/api/pacientes/busca?nome=%27&quot; "
        "-H &quot;Authorization: Bearer $TOKEN&quot;"
    ) in page
    assert "curl.exe" in page


def test_no_command_is_offered_when_the_address_would_break_the_quotes() -> None:
    odd = finding(repro=REPRO.model_copy(update={"target": '/x?a="b"'}))

    assert "Não montamos o comando" in page_for(odd)


def test_a_damaged_address_is_flagged_for_the_reader() -> None:
    damaged = finding(repro=REPRO.model_copy(update={"target_damaged": True}))

    assert "o endereço gravado perdeu um pedaço" in page_for(damaged)


def test_masked_personal_data_is_explained() -> None:
    masked = finding(repro=REPRO.model_copy(update={"personal_data_masked": True}))

    assert "foram trocados por máscaras" in page_for(masked)


def test_a_finding_without_recorded_evidence_has_no_step_by_step() -> None:
    page = page_for(finding(repro=None, evidence=None, confidence=1))
    text = main_text(page)

    assert "não guardou o pedido e a resposta desta falha" in text
    assert "Pegue um token" not in text


def test_an_authorization_finding_has_no_manual_repro_and_says_why_in_one_sentence() -> None:
    authz = finding(
        finding_id="A-12345678",
        origin="authz",
        title="Acesso a recurso de outra conta",
        repro=None,
        evidence=None,
        proposed_confidence=None,
        authz_evidence="A conta user_b leu o recurso da conta user_a (200).",
        explanation=None,
    )
    page = page_for(authz)
    text = main_text(page)

    assert "não há passo a passo para reproduzir à mão aqui" in text
    assert "A conta user_b leu o recurso da conta user_a (200)." in text
    assert "Pegue um token" not in text
    assert "O programa repetiu o pedido com outra conta e comparou as respostas sim" in text


# ---------------------------------------------------------------- estados sem falha


def test_no_severe_finding_says_so_without_saying_safe_and_links_the_minor_warnings() -> None:
    page = page_for()
    text = main_text(page)

    assert "Nenhuma falha grave" in text
    assert "Isto não é um atestado de segurança" in text
    assert 'href="#menores"' in page
    assert 'id="menores"' in page
    assert not re.search(r"\b(seguro|segura|aprovad[oa])\b", text.replace("segurança", ""), re.I)


def test_without_findings_json_the_page_says_there_is_no_report_and_not_zero_failures() -> None:
    page = render_panel(view(findings=None))["findings.html"]
    text = main_text(page)

    assert "Esta execução não tem relatório de falhas" in text
    assert "Graves ·" not in text
    assert "não quer dizer que não houve" in text


def test_minor_warnings_are_counted_by_severity_and_grouped_with_a_link_to_the_report() -> None:
    groups = tuple(
        PanelGroup(
            group_id=f"G-{n}",
            title=f"Cabeçalho ausente {n}",
            severity="low",
            findings_count=n + 1,
            occurrences=n + 1,
            expected_note="Costuma ser esperado." if n == 0 else None,
        )
        for n in range(12)
    )
    page = page_for(finding(), groups=groups)
    text = main_text(page)

    assert "Avisos de gravidade média 1" in text
    assert "Avisos de gravidade baixa 57" in text
    assert "Informativos 31" in text
    assert "Cabeçalho ausente 0" in text
    assert "Mais 2 causas no relatório completo." in text
    assert 'href="../report.html"' in page


def test_how_to_read_the_confidence_has_the_three_steps() -> None:
    text = main_text(one_page())

    assert "a confirmar: a ferramenta desconfia" in text
    assert "prova forte: a resposta mostra a falha" in text
    assert "confirmada: uma pessoa repetiu e viu" in text


# ---------------------------------------------------------------- segurança


def hostile() -> PanelFinding:
    evil = XSS + "‮evil\x1b[31m"
    return finding(
        finding_id='F-"><script>x</script>',
        title=evil,
        function_name=evil,
        path_template=f"/x/{evil}",
        parameter=evil,
        description=evil,
        solution=evil,
        triage_note=evil,
        explanation=None,
        evidence=EVIDENCE.model_copy(
            update={"zap_evidence": XSS, "response_header": f"HTTP/1.1 500 {XSS}"}
        ),
        repro=REPRO.model_copy(
            update={
                "target": f"/x?a={XSS}",
                "attack": XSS,
                "account": XSS,
                "response_excerpt": XSS,
                "body": XSS,
                "headers": (ReproHeader(name="X-A", value=XSS),),
            }
        ),
    )


def test_hostile_target_text_never_becomes_markup() -> None:
    page = page_for(hostile())

    assert "<script" not in page
    assert "<img" not in page
    assert "onerror=alert" not in page.replace("onerror=alert(1)&gt;", "")
    assert "‮" not in page
    assert "\x1b" not in page
    assert '"><script' not in page
    assert "&lt;script&gt;" in page


def test_the_page_has_no_script_external_resource_or_event_handler() -> None:
    for page in (one_page(), page_for(hostile()), page_for()):
        assert "<script" not in page.lower()
        assert "onclick" not in page.lower()
        assert not re.search(r"https?://", page)


def test_a_token_that_slipped_into_the_response_is_redacted_again_by_the_page() -> None:
    leaked = finding(
        repro=REPRO.model_copy(
            update={"response_excerpt": "token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghij"}
        )
    )

    assert "eyJhbGciOiJIUzI1NiJ9" not in page_for(leaked)


def test_render_findings_is_a_pure_function_of_the_view() -> None:
    panel_view: PanelView = view()

    assert render_findings(panel_view) == render_findings(panel_view)


def test_two_groups_with_the_same_title_say_what_tells_them_apart() -> None:
    groups = (
        PanelGroup(
            group_id="G-1",
            title="Session Management Response Identified",
            severity="informational",
            findings_count=29,
            occurrences=30,
            parameter="XSRF-TOKEN",
        ),
        PanelGroup(
            group_id="G-2",
            title="Session Management Response Identified",
            severity="informational",
            findings_count=1,
            occurrences=1,
            parameter="token",
        ),
        PanelGroup(
            group_id="G-3",
            title="Cookie No HttpOnly Flag",
            severity="low",
            findings_count=30,
            occurrences=30,
            parameter="XSRF-TOKEN",
        ),
    )

    text = main_text(page_for(finding(), groups=groups))

    assert "Session Management Response Identified (campo XSRF-TOKEN) 29 achados" in text
    assert "Session Management Response Identified (campo token) 1 achado" in text
    assert "Cookie No HttpOnly Flag 30 achados" in text

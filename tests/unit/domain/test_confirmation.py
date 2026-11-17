"""Testes das decisões puras de confirmação."""

import pytest

from harness_dast.domain.confirmation import (
    ConfirmationPlan,
    judge_confirmation,
    plan_confirmation,
    recipe_targets,
)
from harness_dast.domain.finding import Classification, Finding, FindingEvidence
from harness_dast.domain.http_messages import HttpResponse
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.scan_result import ScanEntry
from harness_dast.domain.verification import VerificationEntry

FINGERPRINT = "a" * 64
MARKER = "0123456789abcdef"


def finding(plugin: str = "40018", method: str = "GET") -> Finding:
    return Finding(
        finding_id="F-aaaaaaaa",
        fingerprint=FINGERPRINT,
        title="teste",
        plugin_id=plugin,
        alert_ref=plugin,
        classification=Classification(),
        proposed_severity="high",
        proposed_confidence="medium",
        operation_id="search",
        method=method,
        path_template="/items",
        attribution="source_message",
        input_vector="query",
        parameter="q",
        occurrences=1,
        evidence=FindingEvidence(),
    )


def exchange(method: str = "GET") -> ExchangeRecord:
    return ExchangeRecord(
        operation_id="search",
        method=method,
        path="/items",
        target="/items?q=normal",
        account="user_a",
        status=200,
    )


def scan() -> ScanEntry:
    return ScanEntry(
        operation_id="search",
        method="GET",
        path="/items",
        message_id=1,
        scan_id="1",
        outcome="completed",
        requests=1,
    )


def plan(plugin: str = "40018") -> ConfirmationPlan:
    result = plan_confirmation(finding(plugin), (exchange(),), (scan(),), MARKER)
    assert isinstance(result, ConfirmationPlan)
    return result


def response(
    body: bytes = b"ok", status: int = 200, elapsed: int = 20, content_type: str = "text/html"
) -> HttpResponse:
    return HttpResponse(status=status, body=body, elapsed_ms=elapsed, content_type=content_type)


def test_refusa_escrita_quando_metodo_nao_e_get() -> None:
    result = plan_confirmation(finding(method="POST"), (exchange("POST"),), (scan(),), MARKER)
    assert isinstance(result, VerificationEntry)
    assert result.level == "not_verifiable"


def test_refusa_semente_quando_nao_foi_varrida() -> None:
    result = plan_confirmation(finding(), (exchange(),), (), MARKER)
    assert isinstance(result, VerificationEntry)
    assert result.level == "not_verifiable"


def test_recusa_travessia_quando_nao_existe_oraculo() -> None:
    result = plan_confirmation(finding("6"), (exchange(),), (scan(),), MARKER)
    assert isinstance(result, VerificationEntry)
    assert result.level == "not_verifiable"


def test_preserva_caminho_quando_gera_receita() -> None:
    assert all(target.startswith("/items?") for target in recipe_targets(plan()))


def test_sql_booleano_reproduz_quando_controle_diverge_repetidamente() -> None:
    result = judge_confirmation(
        plan(), (response(), response(), response(b"no"), response(), response(b"no")), FINGERPRINT
    )
    assert result.level == "reproduced"


def test_sql_igual_nao_refuta_quando_respostas_sao_iguais() -> None:
    result = judge_confirmation(plan(), (response(),) * 5, FINGERPRINT)
    assert result.level == "inconclusive"


def test_sql_instavel_quando_repeticoes_divergem() -> None:
    result = judge_confirmation(
        plan(),
        (response(), response(), response(b"no"), response(b"varia"), response(b"no")),
        FINGERPRINT,
    )
    assert result.level == "inconclusive"


def test_sql_tempo_reproduz_quando_atraso_excede_variacao() -> None:
    values = (20, 30, 2050, 25, 2100, 30)
    assert (
        judge_confirmation(
            plan("40022"), tuple(response(elapsed=n) for n in values), FINGERPRINT
        ).level
        == "reproduced"
    )


def test_sql_tempo_inconclusivo_quando_controle_instavel() -> None:
    values = (20, 900, 2050, 25, 2100, 30)
    assert (
        judge_confirmation(
            plan("40022"), tuple(response(elapsed=n) for n in values), FINGERPRINT
        ).level
        == "inconclusive"
    )


def test_xss_reproduz_reflexao_html_sem_dizer_execucao() -> None:
    marker = f"<hdast-{MARKER}>".encode()
    control = response(f"hdast-{MARKER}".encode())
    result = judge_confirmation(
        plan("40012"), (control, response(marker), control, response(marker)), FINGERPRINT
    )
    assert result.level == "reproduced"
    assert "não prova execução" in result.reason


def test_xss_nao_confirma_quando_conteudo_nao_e_html() -> None:
    marker = f"<hdast-{MARKER}>".encode()
    samples = (
        response(),
        response(marker, content_type="application/json"),
        response(),
        response(marker, content_type="application/json"),
    )
    assert judge_confirmation(plan("40012"), samples, FINGERPRINT).level == "inconclusive"


def test_erro_detalhado_reproduz_quando_controle_e_valido() -> None:
    bad = response(b"Traceback (most recent call last)", status=500)
    assert (
        judge_confirmation(plan("90022"), (response(), bad, response(), bad), FINGERPRINT).level
        == "reproduced"
    )


@pytest.mark.parametrize("plugin", ["40018", "40022", "40012", "90022"])
def test_falha_de_rede_e_inconclusiva_quando_receita_incompleta(plugin: str) -> None:
    assert judge_confirmation(plan(plugin), (None,), FINGERPRINT).level == "inconclusive"


@pytest.mark.parametrize("plugin", ["40018", "40022", "40012", "90022"])
def test_receita_nao_reproduz_quando_nao_ha_efeito(plugin: str) -> None:
    current = plan(plugin)
    samples = tuple(response() for _ in recipe_targets(current))
    assert judge_confirmation(current, samples, FINGERPRINT).level == "inconclusive"


@pytest.mark.parametrize("plugin", ["40018", "40022", "40012", "90022"])
def test_receita_inconclusiva_quando_transporte_falha_no_meio(plugin: str) -> None:
    current = plan(plugin)
    samples = (response(), None, *(response() for _ in recipe_targets(current)[2:]))
    assert judge_confirmation(current, samples, FINGERPRINT).level == "inconclusive"


def test_xss_instavel_quando_reflexao_nao_se_repete() -> None:
    marker = f"<hdast-{MARKER}>".encode()
    result = judge_confirmation(
        plan("40012"), (response(), response(marker), response(), response()), FINGERPRINT
    )
    assert result.level == "inconclusive"


def test_erro_interno_instavel_quando_detalhe_nao_se_repete() -> None:
    result = judge_confirmation(
        plan("90022"),
        (
            response(),
            response(b"Traceback (most recent call last)", status=500),
            response(),
            response(status=500),
        ),
        FINGERPRINT,
    )
    assert result.level == "inconclusive"


def test_erro_interno_nao_confirma_quando_controle_tambem_tem_detalhe() -> None:
    bad = response(b"Traceback (most recent call last)", status=500)
    assert (
        judge_confirmation(plan("90022"), (bad, bad, bad, bad), FINGERPRINT).level == "inconclusive"
    )


def test_recusa_outcome_nao_sucesso_ainda_que_exista_seed() -> None:
    item = finding().model_copy(update={"seed_outcome": "not_found"})
    result = plan_confirmation(item, (exchange(),), (scan(),), MARKER)
    assert isinstance(result, VerificationEntry)
    assert result.level == "not_verifiable"


def test_recusa_semente_com_parametro_repetido() -> None:
    seed = exchange().model_copy(update={"target": "/items?q=a&q=b"})
    result = plan_confirmation(finding(), (seed,), (scan(),), MARKER)
    assert isinstance(result, VerificationEntry)
    assert result.level == "not_verifiable"


@pytest.mark.parametrize("bad", ["", "XYZ", "12345678901234567"])
def test_marcador_invalido_recusado_quando_entrada_malformada(bad: str) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        plan_confirmation(finding(), (exchange(),), (scan(),), bad)


def test_authz_usa_comparacao_guardada_quando_contas_e_status_sao_validos() -> None:
    from harness_dast.domain.authz.result import AuthzFinding
    from harness_dast.domain.confirmation import classify_authz_confirmation

    item = AuthzFinding(
        finding_id="A-aaaaaaaa",
        fingerprint=FINGERPRINT,
        technique="authz_horizontal",
        title="Acesso",
        proposed_severity="high",
        cwe=639,
        owasp_api_2023="API1",
        operation_id="search",
        method="GET",
        path_template="/items",
        actor_account="user_a",
        owner_account="user_b",
        baseline_status=200,
        observed_status=200,
        evidence="com corpo equivalente para o mesmo pedido.",
        description="",
        solution="",
    )
    assert classify_authz_confirmation(item).level == "reproduced"
    assert (
        classify_authz_confirmation(item.model_copy(update={"owner_account": "user_a"})).level
        == "not_verifiable"
    )
    assert (
        classify_authz_confirmation(item.model_copy(update={"evidence": ""})).level
        == "not_verifiable"
    )


def test_cabecalho_usa_somente_evidencia_guardada() -> None:
    item = finding("10020").model_copy(
        update={"method": "POST", "evidence": FindingEvidence(zap_evidence="cabeçalho ausente")}
    )
    result = plan_confirmation(item, (), (), MARKER)
    assert isinstance(result, VerificationEntry)
    assert result.level == "likely"


def test_teto_de_cada_receita_nunca_passa_de_doze() -> None:
    for plugin in ("40018", "40022", "40012", "90022"):
        assert len(recipe_targets(plan(plugin))) <= 12


def test_recusa_semente_com_corpo_quando_nao_pode_repetir_fielmente() -> None:
    seed = exchange().model_copy(update={"body": "{}"})
    result = plan_confirmation(finding(), (seed,), (scan(),), MARKER)
    assert isinstance(result, VerificationEntry)
    assert result.level == "not_verifiable"


def test_recusa_scan_sem_pedidos_quando_nao_prova_varredura() -> None:
    unfinished = scan().model_copy(update={"requests": 0})
    result = plan_confirmation(finding(), (exchange(),), (unfinished,), MARKER)
    assert isinstance(result, VerificationEntry)
    assert result.level == "not_verifiable"


def test_selecao_prioriza_altos_e_medios_quando_limite_reduz() -> None:
    from harness_dast.domain.confirmation import select_confirmation_findings

    low = finding().model_copy(update={"fingerprint": "b" * 64, "proposed_severity": "low"})
    medium = finding().model_copy(update={"fingerprint": "c" * 64, "proposed_severity": "medium"})
    high = finding().model_copy(update={"fingerprint": "d" * 64, "proposed_severity": "high"})
    assert select_confirmation_findings((low, medium, high), 2, None) == (high, medium)


def test_selecao_recusa_fingerprint_duplicado() -> None:
    from harness_dast.domain.confirmation import select_confirmation_findings
    from harness_dast.domain.errors import ConfigError

    with pytest.raises(ConfigError):
        select_confirmation_findings((finding(), finding()), 2, None)

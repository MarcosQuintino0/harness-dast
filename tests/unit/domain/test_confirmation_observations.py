"""Provas locais das observações passivas, sem rede."""

import pytest
from pydantic import ValidationError

from harness_dast.domain.authz.findings import (
    MassObservation,
    excessive_data_finding,
    horizontal_finding,
    mass_assignment_finding,
    vertical_finding,
)
from harness_dast.domain.authz.findings_access import anonymous_finding, tampered_finding
from harness_dast.domain.authz.findings_matrix import matrix_finding
from harness_dast.domain.authz.findings_write import horizontal_write_finding
from harness_dast.domain.authz.matrix_cells import MatrixTask
from harness_dast.domain.confirmation_observations import (
    classify_authz_confirmation,
    classify_recorded_finding,
)
from harness_dast.domain.cors import cors_finding
from harness_dast.domain.finding import Classification, Finding, FindingEvidence
from harness_dast.domain.probe_exchange import ExchangeRecord


def finding(plugin: str, response: str = "", request: str = "") -> Finding:
    return Finding(
        finding_id="F-aaaaaaaa",
        fingerprint="a" * 64,
        title="teste",
        plugin_id=plugin,
        alert_ref=plugin,
        classification=Classification(),
        proposed_severity="medium",
        proposed_confidence="medium",
        method="GET",
        path_template="/",
        attribution="source_message",
        occurrences=1,
        evidence=FindingEvidence(response_header=response, request_header=request),
    )


@pytest.mark.parametrize("plugin", ["10020", "10021", "10038"])
def test_ausencia_em_html_e_observada(plugin: str) -> None:
    result = classify_recorded_finding(
        finding(plugin, "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n")
    )
    assert result is not None
    assert result.level == "reproduced"


@pytest.mark.parametrize("plugin", ["10020", "10021", "10038"])
def test_json_nao_prova_interface_html(plugin: str) -> None:
    result = classify_recorded_finding(
        finding(plugin, "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n")
    )
    assert result is not None
    assert result.level == "not_verifiable"


@pytest.mark.parametrize(
    ("plugin", "header"),
    [("10020", "X-Frame-Options: DENY"), ("10021", "X-Content-Type-Options: nosniff")],
)
def test_protecao_especifica_contradiz_ausencia(plugin: str, header: str) -> None:
    result = classify_recorded_finding(
        finding(plugin, f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n{header}\r\n")
    )
    assert result is not None
    assert result.level == "likely_false_positive"


def test_csp_presente_nao_prova_eficacia() -> None:
    result = classify_recorded_finding(
        finding(
            "10038",
            "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
            "Content-Security-Policy: default-src *\r\n",
        )
    )
    assert result is not None
    assert result.level == "inconclusive"


def test_cors_usa_headers_reais_sem_expor_valores() -> None:
    result = classify_recorded_finding(
        finding(
            "10098",
            "HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: https://example.invalid\r\n"
            "Access-Control-Allow-Credentials: true\r\n",
            "GET / HTTP/1.1\r\nOrigin: https://example.invalid\r\nCookie: segredo\r\n",
        )
    )
    assert result is not None
    assert result.level == "reproduced"
    assert "segredo" not in str(result)
    assert "example.invalid" not in str(result)


@pytest.mark.parametrize(
    "header",
    ["", "malformado", "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Type: text/html\r\n"],
)
def test_cabecalho_invalido_nao_prova_ausencia(header: str) -> None:
    result = classify_recorded_finding(finding("10020", header))
    assert result is not None
    assert result.level == "not_verifiable"


def test_cors_sem_origin_e_recusado() -> None:
    result = classify_recorded_finding(
        finding("10098", "HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\n")
    )
    assert result is not None
    assert result.level == "not_verifiable"


def test_receita_ativa_fica_para_consumidor() -> None:
    assert classify_recorded_finding(finding("40018")) is None


def test_cabecalho_sem_quebra_final_como_arquivo_do_zap() -> None:
    result = classify_recorded_finding(
        finding("10020", "HTTP/1.1 200 OK\nContent-Type: text/html\nConnection: close")
    )
    assert result is not None
    assert result.level == "reproduced"


def test_horizontal_compara_corpos_e_papeis() -> None:
    item = horizontal_finding(
        product="p",
        operation_id="op",
        method="GET",
        path_template="/x/{id}",
        actor=("a", "user"),
        owner=("b", "user"),
        statuses=(200, 200),
    )
    assert classify_authz_confirmation(item).level == "reproduced"
    assert (
        classify_authz_confirmation(
            item.model_copy(update={"evidence": "duas respostas 200"})
        ).level
        == "not_verifiable"
    )


def test_vertical_exige_contexto_do_papel() -> None:
    item = vertical_finding(
        product="p",
        operation_id="op",
        method="GET",
        path_template="/x",
        actor=("a", "user"),
        owner=("b", "admin"),
        statuses=(200, 200),
    )
    assert classify_authz_confirmation(item).level == "reproduced"
    assert (
        classify_authz_confirmation(item.model_copy(update={"actor_role": "admin"})).level
        == "not_verifiable"
    )


def test_escrita_horizontal_exige_leitura_posterior() -> None:
    item = horizontal_write_finding(
        product="p",
        operation_id="op",
        method="PATCH",
        path_template="/x/{id}",
        actor=("a", "user"),
        owner=("b", "user"),
        status=200,
        field="name",
        restored=True,
    )
    assert classify_authz_confirmation(item).level == "reproduced"
    assert (
        classify_authz_confirmation(item.model_copy(update={"evidence": "status 200"})).level
        == "not_verifiable"
    )


def test_atribuicao_post_sem_readback_nao_comprova_estado() -> None:
    def make(observed: MassObservation) -> str:
        item = mass_assignment_finding(
            product="p",
            operation_id="op",
            method="POST",
            path_template="/x",
            actor=("a", "user"),
            sent_field="role",
            changed=("role",),
            status=201,
            restored=None,
            observed_in=observed,
        )
        return classify_authz_confirmation(item).level

    assert make("post_response") == "not_verifiable"
    assert make("created_read") == "reproduced"


def test_exposicao_exige_campos_e_sucesso() -> None:
    item = excessive_data_finding(
        product="p",
        operation_id="op",
        method="GET",
        path_template="/x",
        actor=("a", "user"),
        status=200,
        fields=("internal",),
    )
    assert classify_authz_confirmation(item).level == "reproduced"
    assert (
        classify_authz_confirmation(item.model_copy(update={"fields": ()})).level
        == "not_verifiable"
    )


def test_token_exige_variante_e_corpo_equivalente() -> None:
    item = tampered_finding(
        product="p",
        operation_id="op",
        method="GET",
        path_template="/x",
        actor=("a", "user"),
        variants=("scrambled",),
        statuses=(200, 200),
    )
    assert classify_authz_confirmation(item).level == "reproduced"
    assert (
        classify_authz_confirmation(item.model_copy(update={"variants": ()})).level
        == "not_verifiable"
    )


def test_modelo_rejeita_dado_malformado() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate({"plugin_id": "10020"})


def test_cors_receipt_nao_afirma_captura_de_headers() -> None:
    exchange = ExchangeRecord(
        operation_id="op", method="GET", path="/x", target="/x", account="a", status=200
    )
    item = cors_finding("p", exchange, "user", 200, "wildcard")
    result = classify_authz_confirmation(item)
    assert result.level == "reproduced"
    assert result.attack is not None
    assert "cabeçalhos originais não foram guardados" in result.attack
    assert (
        classify_authz_confirmation(item.model_copy(update={"fields": ()})).level
        == "not_verifiable"
    )


def test_anonimo_exige_equivalencia_registrada() -> None:
    item = anonymous_finding(
        product="p",
        operation_id="op",
        method="GET",
        path_template="/x",
        actor=("a", "user"),
        operation=None,
        statuses=(200, 200),
    )
    assert classify_authz_confirmation(item).level == "reproduced"
    assert (
        classify_authz_confirmation(item.model_copy(update={"observed_status": 403})).level
        == "not_verifiable"
    )


def test_matriz_mostra_resposta_para_papel_proibido_sem_provar_escrita() -> None:
    exchange = ExchangeRecord(
        operation_id="op", method="POST", path="/x", target="/x", account="b", status=201
    )
    task = MatrixTask(row=0, col=0, role="user", exchange=exchange, actor="a", owner=("b", "admin"))
    item = matrix_finding(product="p", task=task, status=201, source="replay")
    result = classify_authz_confirmation(item)
    assert result.level == "reproduced"
    assert result.attack is not None
    assert "efeito da escrita não foi provado" in result.attack
    assert (
        classify_authz_confirmation(item.model_copy(update={"fields": ("admin",)})).level
        == "not_verifiable"
    )


@pytest.mark.parametrize("origin", ["", "https://example.invalid/path", "https://bad.invalid:bad"])
def test_cors_origem_ausente_ou_invalida_nao_prova_politica(origin: str) -> None:
    item = finding(
        "10098",
        "HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\n",
        f"GET / HTTP/1.1\r\nOrigin: {origin}\r\n",
    )
    result = classify_recorded_finding(item)
    assert result is not None
    assert result.level == "not_verifiable"


def test_observacao_truncada_nao_prova_ausencia() -> None:
    item = finding("10020", "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n")
    item = item.model_copy(
        update={"evidence": item.evidence.model_copy(update={"truncated": True})}
    )
    result = classify_recorded_finding(item)
    assert result is not None
    assert result.level == "not_verifiable"


@pytest.mark.parametrize(
    ("request_header", "response", "expected"),
    [
        ("GET https://example.invalid/x HTTP/1.1\r\n", "HTTP/1.1 200 OK\r\n", "reproduced"),
        ("GET /x HTTP/1.1\r\n", "HTTP/1.1 200 OK\r\n", "not_verifiable"),
        (
            "GET https://example.invalid/x HTTP/1.1\r\n",
            "HTTP/1.1 200 OK\r\nStrict-Transport-Security: max-age=123\r\n",
            "likely_false_positive",
        ),
        (
            "GET https://example.invalid/x HTTP/1.1\r\n",
            "HTTP/1.1 200 OK\r\nStrict-Transport-Security: max-age=0\r\n",
            "inconclusive",
        ),
    ],
)
def test_hsts_exige_https_comprovado(request_header: str, response: str, expected: str) -> None:
    result = classify_recorded_finding(finding("10035", response, request_header))
    assert result is not None
    assert result.level == expected

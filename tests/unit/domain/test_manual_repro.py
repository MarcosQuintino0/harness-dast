from harness_dast.domain.finding import Classification, Finding, FindingEvidence
from harness_dast.domain.manual_repro import (
    CPF_MASK,
    EMAIL_MASK,
    PHONE_MASK,
    RESPONSE_LINE_CAP,
    build_manual_repro,
    mask_personal_data,
)

_REQUEST = (
    "GET http://alvo.local:8080/api/pacientes/busca?nome=%27 HTTP/1.1\n"
    "Host: alvo.local:8080\n"
    "Authorization: Bearer abc.def.ghi\n"
    "Accept: application/json\n"
    "X-XSRF-TOKEN: csrfvalor123\n"
    "Cookie: SESSION=segredo\n"
    "User-Agent: zap\n"
    "Content-Type: application/json\n"
    "X-Custom: valor-qualquer"
)


def _finding(**evidence: object) -> Finding:
    values: dict[str, object] = {
        "request_header": _REQUEST,
        "response_header": "HTTP/1.1 500 Internal Server Error\nContent-Type: application/json",
        "response_body": '{"code": "ERRO_INTERNO"}',
    }
    values.update(evidence)
    return Finding(
        finding_id="F-fbb97e8d",
        fingerprint="a" * 64,
        title="SQL Injection",
        plugin_id="40018",
        alert_ref="40018",
        classification=Classification(cwe=89),
        proposed_severity="high",
        proposed_confidence="high",
        method="GET",
        path_template="/api/pacientes/busca",
        attribution="source_message",
        occurrences=1,
        evidence=FindingEvidence.model_validate(values),
    )


def test_build_manual_repro_monta_metodo_endereco_relativo_e_base_marcada() -> None:
    repro = build_manual_repro(_finding(), account="user_a")

    assert repro is not None
    assert repro.method == "GET"
    assert repro.base_url == "$BASE_URL"
    assert repro.target == "/api/pacientes/busca?nome=%27"
    assert repro.account == "user_a"
    assert "alvo.local" not in repro.model_dump_json()


def test_build_manual_repro_troca_credenciais_por_marcadores() -> None:
    repro = build_manual_repro(_finding())

    assert repro is not None
    by_name = {header.name: header.value for header in repro.headers}
    assert by_name["Authorization"] == "Bearer $TOKEN"
    assert by_name["X-XSRF-TOKEN"] == "$CSRF_TOKEN"
    assert by_name["Cookie"] == "$TOKEN"
    dumped = repro.model_dump_json()
    for leaked in ("abc.def.ghi", "csrfvalor123", "segredo"):
        assert leaked not in dumped


def test_build_manual_repro_mostra_so_o_nome_de_cabecalho_comum_e_o_content_type() -> None:
    repro = build_manual_repro(_finding())

    assert repro is not None
    by_name = {header.name: header.value for header in repro.headers}
    assert by_name["Content-Type"] == "application/json"
    assert by_name["X-Custom"] is None
    assert "Host" not in by_name
    assert "User-Agent" not in by_name


def test_build_manual_repro_resume_a_resposta_recebida() -> None:
    repro = build_manual_repro(_finding())

    assert repro is not None
    assert repro.received_status == 500
    assert repro.response_excerpt == '{"code": "ERRO_INTERNO"}'
    assert (repro.response_total_lines, repro.response_cut) == (1, False)


def test_build_manual_repro_corta_resposta_longa_em_40_linhas_e_diz_o_total() -> None:
    body = "\n".join(f"linha {i}" for i in range(100))

    repro = build_manual_repro(_finding(response_body=body))

    assert repro is not None
    assert len(repro.response_excerpt.splitlines()) == RESPONSE_LINE_CAP
    assert repro.response_total_lines == 100
    assert repro.response_cut is True


def test_build_manual_repro_herda_o_corte_feito_na_gravacao() -> None:
    repro = build_manual_repro(_finding(truncated=True))

    assert repro is not None
    assert repro.response_cut is True


def test_build_manual_repro_mascara_cpf_email_e_telefone_em_tudo() -> None:
    request = "POST http://alvo/api/x?cpf=123.456.789-09 HTTP/1.1\nContent-Type: application/json"
    repro = build_manual_repro(
        _finding(
            request_header=request,
            request_body='{"email": "ana@exemplo.com", "tel": "(11) 91234-5678"}',
            response_body='{"cpf": "98765432100", "contato": "ana@exemplo.com"}',
        )
    )

    assert repro is not None
    assert repro.personal_data_masked is True
    assert CPF_MASK in repro.target
    assert repro.body is not None
    assert EMAIL_MASK in repro.body
    assert PHONE_MASK in repro.body
    dumped = repro.model_dump_json()
    for leaked in ("123.456.789-09", "ana@exemplo.com", "91234-5678", "98765432100"):
        assert leaked not in dumped


def test_build_manual_repro_sem_dado_pessoal_nao_marca_mascaramento() -> None:
    repro = build_manual_repro(_finding())

    assert repro is not None
    assert repro.personal_data_masked is False


def test_build_manual_repro_de_post_leva_o_corpo() -> None:
    request = "POST http://alvo/api/x HTTP/1.1\nContent-Type: application/json"

    repro = build_manual_repro(_finding(request_header=request, request_body='{"a": 1}'))

    assert repro is not None
    assert (repro.method, repro.body) == ("POST", '{"a": 1}')


def test_build_manual_repro_de_get_sem_corpo_devolve_corpo_none() -> None:
    repro = build_manual_repro(_finding())

    assert repro is not None
    assert repro.body is None


def test_build_manual_repro_sem_evidencia_devolve_none() -> None:
    assert build_manual_repro(_finding(available=False)) is None


def test_build_manual_repro_com_linha_de_requisicao_ilegivel_devolve_none() -> None:
    assert build_manual_repro(_finding(request_header="lixo sem forma")) is None
    assert build_manual_repro(_finding(request_header="")) is None


def test_build_manual_repro_nao_confia_em_nome_de_cabecalho_hostil() -> None:
    request = "GET /x HTTP/1.1\nX-Evil<script>: valor\nX-Ok: v"

    repro = build_manual_repro(_finding(request_header=request))

    assert repro is not None
    assert [header.name for header in repro.headers] == ["X-Ok"]


def test_build_manual_repro_remove_controle_do_endereco() -> None:
    request = "GET /a\x1b[31mb HTTP/1.1"

    repro = build_manual_repro(_finding(request_header=request))

    # A linha com ESC não casa com a forma da requisição: sem dados, nunca texto perigoso.
    assert repro is None or "\x1b" not in repro.target


def test_mask_personal_data_deixa_numero_solto_que_nao_e_cpf() -> None:
    text, changed = mask_personal_data("id 1234567890 e 2026-11-14T10-00-00Z")

    assert (text, changed) == ("id 1234567890 e 2026-11-14T10-00-00Z", False)

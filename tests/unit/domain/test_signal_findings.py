"""Achados de sinal de erro interno a partir da auditoria da cerca (ADR 0049)."""

from datetime import UTC, datetime, timedelta

import pytest

from harness_dast.domain.error_signal_catalog import SIGNAL_RULES
from harness_dast.domain.finding_build import AlertResolver, OperationRef
from harness_dast.domain.signal_findings import (
    build_proxy_signals,
    parse_instant,
    signal_fingerprint,
    signal_window,
)
from harness_dast.domain.signal_result import MAX_SIGNAL_FINDINGS, MAX_STATUSES, ProxySignals
from harness_dast.domain.traffic import ProxyRow

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
WINDOW = (T0, T0 + timedelta(minutes=10))
RESOLVER = AlertResolver(
    {},
    {},
    (
        OperationRef(operation_id="getUser", method="GET", path="/users/{id}"),
        OperationRef(operation_id="search", method="GET", path="/search"),
    ),
)


def row(
    path: str = "/users/12",
    *,
    method: str = "GET",
    status: int | None = 500,
    signals: tuple[str, ...] = (),
    skip: str | None = None,
    at: datetime = T0 + timedelta(minutes=1),
    decision: str = "allow",
    query: tuple[str, ...] = (),
) -> ProxyRow:
    return ProxyRow(
        at=at,
        decision=decision,
        reason="allowed" if decision == "allow" else "path_not_allowed",
        method=method,
        path=path,
        status=status,
        signals=signals,
        signal_skip=skip,
        query_params=query,
    )


def build(rows: list[ProxyRow]) -> ProxySignals:
    return build_proxy_signals(rows, product="vampi", window=WINDOW, resolver=RESOLVER)


def test_zero_linhas_devolve_contagens_zeradas_de_todas_as_categorias() -> None:
    result = build([])

    assert result.enabled is True
    assert result.responses_total == 0
    assert result.findings == ()
    assert result.counts == {rule.category: 0 for rule in SIGNAL_RULES}


def test_agrupa_por_fingerprint_e_junta_ocorrencias() -> None:
    rows = [
        row("/users/1", signals=("sql_error",), query=("q",)),
        row("/users/2", signals=("sql_error",), status=400, query=("outro",)),
        row("/users/3", signals=("sql_error",)),
    ]

    result = build(rows)

    (finding,) = result.findings
    assert finding.occurrences == 3
    assert finding.statuses == (500, 400)
    assert finding.query_params == ("q",)
    assert finding.operation_id == "getUser"
    assert finding.path_template == "/users/{}"
    assert finding.finding_id == f"S-{finding.fingerprint[:8]}"
    assert result.responses_with_signal == 3
    assert result.counts["sql_error"] == 3


def test_fingerprint_igual_para_ids_diferentes_e_diferente_por_categoria_e_metodo() -> None:
    a = build([row("/users/1", signals=("sql_error",))]).findings[0]
    b = build([row("/users/99999", signals=("sql_error",), status=200)]).findings[0]
    other_category = build([row("/users/1", signals=("debug_page",))]).findings[0]
    other_method = build(
        [
            row(
                "/users/1",
                method="GET",
                signals=("sql_error",),
            )
        ]
    ).findings[0]
    put = build_proxy_signals(
        [row("/users/1", method="PUT", signals=("sql_error",))],
        product="vampi",
        window=WINDOW,
        resolver=AlertResolver(
            {}, {}, (OperationRef(operation_id="putUser", method="PUT", path="/users/{id}"),)
        ),
    ).findings[0]

    assert a.fingerprint == b.fingerprint == other_method.fingerprint
    assert a.fingerprint != other_category.fingerprint
    assert a.fingerprint != put.fingerprint


def test_fingerprint_depende_do_produto_e_nao_do_host_nem_do_status() -> None:
    one = signal_fingerprint(
        product="a", method="get", path_template="/x/{id}", category="sql_error"
    )
    two = signal_fingerprint(product="b", method="GET", path_template="/x/{}", category="sql_error")
    same = signal_fingerprint(
        product="a", method="GET", path_template="/x/{}", category="sql_error"
    )

    assert one == same
    assert one != two
    assert len(one) == 64


def test_categorias_diferentes_na_mesma_resposta_viram_achados_separados() -> None:
    result = build([row(signals=("sql_error", "stack_trace_java"))])

    assert {item.category for item in result.findings} == {"sql_error", "stack_trace_java"}
    assert result.responses_with_signal == 1
    assert result.counts["sql_error"] == result.counts["stack_trace_java"] == 1


def test_caminho_sem_operacao_usa_modelo_generico_e_nunca_a_url_concreta() -> None:
    result = build([row("/legado/pedidos/123456/itens", signals=("sql_error",))])

    (finding,) = result.findings
    assert finding.operation_id is None
    assert finding.path_template == "/fora-do-contrato"
    assert "123456" not in result.model_dump_json()


def test_severidade_e_confianca_vem_do_catalogo_e_ordem_e_da_mais_grave() -> None:
    result = build([row(signals=("stack_trace_java",)), row("/search", signals=("sql_error",))])

    assert [item.category for item in result.findings] == ["sql_error", "stack_trace_java"]
    assert result.findings[0].proposed_severity == "medium"
    assert result.findings[0].cwe == 209
    assert result.findings[1].proposed_severity == "low"
    assert all(item.status == "needs_triage" and item.origin == "proxy" for item in result.findings)


def test_janela_so_conta_linhas_dentro_do_intervalo_inclusive() -> None:
    rows = [
        row(signals=("sql_error",), at=T0 - timedelta(seconds=1)),
        row(signals=("sql_error",), at=T0),
        row(signals=("sql_error",), at=WINDOW[1]),
        row(signals=("sql_error",), at=WINDOW[1] + timedelta(seconds=1)),
    ]

    result = build(rows)

    assert result.responses_with_signal == 2
    assert result.responses_total == 2


def test_so_linhas_liberadas_com_status_entram_na_base() -> None:
    rows = [
        row(signals=("sql_error",)),
        row(decision="deny", status=403),
        row(status=None),
        row(skip="type"),
    ]

    result = build(rows)

    assert result.responses_total == 2
    assert result.responses_examined == 1
    assert result.responses_skipped == {"type": 1}


def test_lidas_mais_nao_lidas_fecham_com_as_linhas_liberadas_com_status() -> None:
    rows = [
        row(),
        row(signals=("sql_error",)),
        row(skip="encoding"),
        row(skip="empty"),
        row(skip="empty"),
    ]

    result = build(rows)

    assert result.responses_examined == 2
    assert result.responses_skipped == {"empty": 2, "encoding": 1}
    assert result.responses_total == len(rows)


def test_statuses_e_nomes_de_consulta_ficam_limitados() -> None:
    rows = [
        row(signals=("sql_error",), status=500 + index, query=tuple(f"p{n}" for n in range(30)))
        for index in range(20)
    ]

    (finding,) = build(rows).findings

    assert len(finding.statuses) == MAX_STATUSES
    assert len(finding.query_params) == 10
    assert finding.occurrences == 20


def test_categoria_desconhecida_na_linha_e_ignorada_e_nao_vira_achado() -> None:
    result = build([row(signals=("categoria_futura",))])

    assert result.findings == ()
    assert result.responses_with_signal == 0


def test_muitas_linhas_com_caminhos_diferentes_respeitam_o_teto_de_achados() -> None:
    rows = [
        row(f"/legado/rota{index}x/a", signals=("sql_error",))
        for index in range(MAX_SIGNAL_FINDINGS + 30)
    ]

    result = build(rows)

    assert len(result.findings) == 1
    assert result.findings_omitted == 0
    assert result.counts["sql_error"] == MAX_SIGNAL_FINDINGS + 30


def test_o_resultado_nao_depende_da_ordem_das_linhas() -> None:
    rows = [row("/users/1", signals=("sql_error",)), row("/search", signals=("debug_page",)), row()]

    assert build(rows) == build(list(reversed(rows)))


def test_nenhum_valor_de_resposta_ou_de_consulta_entra_no_resultado() -> None:
    result = build([row("/users/1", signals=("sql_error",), query=("q",))])

    assert "ORA-" not in result.model_dump_json()
    assert "Traceback" not in result.model_dump_json()


def test_parse_instant_aceita_iso_com_e_sem_fuso_e_recusa_lixo() -> None:
    assert parse_instant("2026-11-14T12:00:00+00:00") == T0
    assert parse_instant("2026-11-14T12:00:00") == T0
    assert parse_instant("ontem") is None
    assert parse_instant("") is None


@pytest.mark.parametrize(
    ("started", "ends"),
    [
        ("lixo", ["2026-11-14T12:10:00+00:00"]),
        ("2026-11-14T12:00:00+00:00", [None, "lixo", ""]),
        ("2026-11-14T12:00:00+00:00", []),
        ("2026-11-14T12:00:00+00:00", ["2026-11-14T11:00:00+00:00"]),
    ],
)
def test_signal_window_devolve_none_quando_o_intervalo_nao_existe(
    started: str, ends: list[str | None]
) -> None:
    assert signal_window(started, ends) is None


def test_signal_window_vai_do_inicio_do_probe_ao_ultimo_fim_gravado() -> None:
    window = signal_window(
        "2026-11-14T12:00:00+00:00",
        [
            "2026-11-14T12:05:00+00:00",
            None,
            "2026-11-14T12:20:00+00:00",
            "2026-11-14T12:10:00+00:00",
        ],
    )

    assert window == (T0, T0 + timedelta(minutes=20))


def test_identificador_alterado_pelo_zap_casa_com_modelo_da_operacao() -> None:
    result = build(
        [
            row("/users/123", signals=("sql_error",)),
            row("/users/ataque-mutado", signals=("sql_error",)),
        ]
    )

    assert len(result.findings) == 1
    assert result.findings[0].operation_id == "getUser"
    assert result.findings[0].occurrences == 2


def test_caminhos_e_metodos_fora_do_contrato_agrupam_por_categoria() -> None:
    result = build(
        [
            row("/nao-previsto/1", signals=("sql_error",)),
            row("/outro/valor", method="POST", signals=("sql_error", "debug_page")),
        ]
    )

    assert len(result.findings) == 2
    sql = next(f for f in result.findings if f.category == "sql_error")
    assert (sql.operation_id, sql.method, sql.path_template, sql.occurrences) == (
        None,
        "",
        "/fora-do-contrato",
        2,
    )


def test_modelos_ambiguos_nao_atribuem_operacao() -> None:
    resolver = AlertResolver(
        {},
        {},
        (
            OperationRef(operation_id="a", method="GET", path="/users/{id}"),
            OperationRef(operation_id="b", method="GET", path="/users/{nome}"),
        ),
    )
    result = build_proxy_signals(
        [row(signals=("sql_error",))], product="vampi", window=WINDOW, resolver=resolver
    )

    assert result.findings[0].operation_id is None
    assert result.findings[0].path_template == "/fora-do-contrato"


def test_fingerprint_distingue_identificadores_de_operacao() -> None:
    args = dict(product="p", method="GET", path_template="/users/{id}", category="sql_error")
    assert signal_fingerprint(**args, operation_id="a") != signal_fingerprint(
        **args, operation_id="b"
    )


def test_rota_literal_precede_parametro() -> None:
    resolver = AlertResolver(
        {},
        {},
        (
            OperationRef(operation_id="detalhe", method="GET", path="/users/{id}"),
            OperationRef(operation_id="busca", method="GET", path="/users/busca"),
        ),
    )
    result = build_proxy_signals(
        [row("/users/busca", signals=("sql_error",))],
        product="vampi",
        window=WINDOW,
        resolver=resolver,
    )

    assert result.findings[0].operation_id == "busca"

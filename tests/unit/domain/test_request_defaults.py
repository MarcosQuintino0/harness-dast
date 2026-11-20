"""Tabela de padrões do pedido mínimo e seus comentários de cabeçalho (ADR 0120)."""

from datetime import date

import pytest

from harness_dast.domain.request_defaults import (
    NOTE_PREFIX,
    OUTCOME_CLASSES,
    REQUEST_DEFAULTS,
    DefaultValue,
    RequestDefault,
    read_request_notes,
    request_notes,
)

EXPECTED = {
    "environment.name": "teste",
    "scope.path_mode": "strict",
    "limits.requests_per_second": 10,
    "limits.max_duration_minutes": 30,
    "limits.zap_threads_per_host": 2,
    "auth.login_max_per_minute": 5,
    "scan.strength": "LOW",
    "scan.include_outcomes": OUTCOME_CLASSES,
    "scan.inject_headers": True,
    "scan.oast": True,
    "extra_checks.allow_rate_tests": True,
    "extra_checks.experimental_rules": True,
    "extra_checks.inventory": True,
    "extra_checks.nuclei": True,
    "extra_checks.nuclei_login": True,
    "scan.pacing": "proxy",
}


def test_tabela_tem_os_valores_do_adr_quando_consultada() -> None:
    assert {field: item.value for field, item in REQUEST_DEFAULTS.items()} == EXPECTED


def test_tabela_nao_liga_os_caminhos_amplos_do_nuclei() -> None:
    assert "extra_checks.nuclei_wide_paths" not in REQUEST_DEFAULTS


def test_tabela_documenta_o_motivo_de_cada_padrao() -> None:
    assert all(item.reason.strip() for item in REQUEST_DEFAULTS.values())


def test_tabela_nao_liga_nenhuma_das_tres_escritas() -> None:
    forbidden = {"authz.allow_writes", "negative.allow_writes", "scan.allow_upload_scan"}

    assert forbidden.isdisjoint(REQUEST_DEFAULTS)


def test_classes_de_resposta_cobrem_as_cinco_do_adr() -> None:
    assert set(OUTCOME_CLASSES) == {
        "not_found",
        "validation_error",
        "conflict",
        "logical_failure",
        "client_error",
    }


@pytest.mark.parametrize(
    ("value", "shown", "answer"),
    [
        (True, "true", True),
        (False, "false", False),
        (10, "10", 10),
        ("LOW", "LOW", "LOW"),
        (date(2026, 12, 18), "2026-12-18", date(2026, 12, 18)),
        (("a", "b"), "a, b", ["a", "b"]),
    ],
)
def test_valor_aparece_como_texto_e_como_resposta_quando_o_tipo_varia(
    value: DefaultValue, shown: str, answer: object
) -> None:
    item = RequestDefault(field="x.y", value=value, reason="motivo")

    assert item.shown == shown
    assert item.answer_value == answer


def test_notas_do_cabecalho_voltam_como_campo_e_valor_quando_lidas() -> None:
    items = (
        RequestDefault(field="limits.requests_per_second", value=10, reason="carga moderada"),
        RequestDefault(
            field="authorization.windows",
            value="seg-dom 00:00-24:00 America/Sao_Paulo",
            reason="o dia inteiro",
        ),
    )

    text = request_notes(items)

    assert text.count(NOTE_PREFIX) == 2
    assert read_request_notes(text + "schema_version: 1\n") == (
        "limits.requests_per_second = 10",
        "authorization.windows = seg-dom 00:00-24:00 America/Sao_Paulo",
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "# comentário qualquer\n",
        "# Padrão mínimo da CLI: limits.max_duration_minutes = 30 (resposta não sei)\n",
        f"{NOTE_PREFIX}sem separador de motivo\n",
    ],
)
def test_leitura_ignora_o_que_nao_e_nota_quando_o_texto_e_outro(text: str) -> None:
    assert read_request_notes(text) == ()

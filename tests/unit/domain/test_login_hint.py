"""Dica do login recusado: o código HTTP escolhe o conselho (rodada cega de 2026-11-15)."""

import pytest

from harness_dast.domain.login_hint import login_refused_hint


def test_login_refused_hint_aponta_o_formato_quando_o_alvo_responde_415() -> None:
    hint = login_refused_hint(415, "form")

    assert "HTTP 415" in hint
    assert "auth.request_encoding para json" in hint


def test_login_refused_hint_sugere_form_quando_o_perfil_ja_envia_json() -> None:
    assert "auth.request_encoding para form" in login_refused_hint(415, "json")


@pytest.mark.parametrize("status", [400, 422])
def test_login_refused_hint_cita_o_formato_quando_o_corpo_pode_nao_ter_sido_entendido(
    status: int,
) -> None:
    assert "auth.request_encoding" in login_refused_hint(status, "form")


@pytest.mark.parametrize("status", [401, 403])
def test_login_refused_hint_aponta_credenciais_quando_o_alvo_nega(status: int) -> None:
    hint = login_refused_hint(status, "form")

    assert "secret_ref" in hint
    assert "request_encoding para" not in hint


@pytest.mark.parametrize("status", [404, 405])
def test_login_refused_hint_aponta_o_caminho_quando_o_login_nao_existe(status: int) -> None:
    assert "auth.token_path" in login_refused_hint(status, "json")


def test_login_refused_hint_manda_esperar_quando_o_alvo_limita() -> None:
    assert "auth.login_limit" in login_refused_hint(429, "form")


def test_login_refused_hint_nao_fala_de_formato_quando_o_login_nao_e_por_senha() -> None:
    assert "request_encoding para" not in login_refused_hint(415, None)


def test_login_refused_hint_tem_texto_generico_para_outros_codigos() -> None:
    hint = login_refused_hint(500, "form")

    assert "HTTP 500" in hint
    assert "auth.request_encoding" in hint

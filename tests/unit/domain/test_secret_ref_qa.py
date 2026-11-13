# ruff: noqa: RUF001
"""QA independente de `SecretRef` (`domain/secret_ref.py`).

Contrato: só `env:NOME` (maiúsculas, dígitos e `_`) é aceito; um valor literal nunca passa e
nunca é repetido na mensagem. O perfil é escrito pelo agente: o nome apontado por `secret_ref`
é lido do ambiente e enviado ao alvo (senha de login, chave de API). Por isso uma referência às
variáveis do PRÓPRIO harness (`HDAST_ZAP_API_KEY`) não pode ser aceita: o agente (ou um texto
plantado que o engane) a enviaria ao alvo como se fosse a senha de uma conta.
"""

import pytest
from pydantic import ValidationError

from harness_dast.domain.secret_ref import SecretRef


@pytest.mark.parametrize(
    "value", ["env:A", "env:MEU_PRODUTO_USER_A_SENHA", "env:X1_2", "env:" + "A" * 128]
)
def test_secret_ref_accepts_the_documented_format(value: str) -> None:
    assert SecretRef(secret_ref=value).env_name == value.removeprefix("env:")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "env:",
        "env:a",
        "env:1A",
        "env:_A",
        "env:A-B",
        "env:A B",
        "env:A\n",
        "env:A\nenv:B",
        "env: A",
        " env:A",
        "ENV:A",
        "file:/etc/passwd",
        "file:A",
        "vault:A",
        "env:${HOME}",
        "env:$(id)",
        "env:A;B",
        "env:" + "A" * 129,
        "env:А",
        "senha-literal-123",
        "hunter2",
    ],
)
def test_secret_ref_refuses_anything_that_is_not_an_environment_variable_name(value: str) -> None:
    with pytest.raises(ValidationError):
        SecretRef(secret_ref=value)


def test_secret_ref_error_never_echoes_a_literal_secret_typed_in_the_wrong_place() -> None:
    literal = "SenhaSuperSecreta!2026"

    with pytest.raises(ValidationError) as caught:
        SecretRef(secret_ref=literal)

    assert literal not in str(caught.value)


@pytest.mark.parametrize(
    "name",
    ["HDAST_ZAP_API_KEY", "HDAST_STATE_DIR", "HDAST_AUTH_PROXY_URL", "HDAST_ANYTHING"],
)
def test_secret_ref_refuses_a_reference_to_the_harness_own_variables(name: str) -> None:
    # Defeito: nada impede `secret_ref: env:HDAST_ZAP_API_KEY` como senha de uma conta; o login
    # enviaria a chave da API do ZAP ao alvo. O mesmo vale para qualquer variável do ambiente do
    # operador (tokens de nuvem, de IA, do GitHub): o formato aceita todas.
    with pytest.raises(ValidationError):
        SecretRef(secret_ref=f"env:{name}")

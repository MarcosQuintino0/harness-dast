import pytest

from harness_dast.domain.placeholders import (
    is_placeholder_host,
    is_placeholder_reference,
    is_placeholder_secret_name,
    is_placeholder_text,
)


@pytest.mark.parametrize(
    "host", ["exemplo.com.br", "api.exemplo.com.br", "EXAMPLE.com", "a.b.example.org"]
)
def test_is_placeholder_host_is_true_for_example_domains(host: str) -> None:
    assert is_placeholder_host(host)


@pytest.mark.parametrize("host", ["acme-teste.net.br", "notexample.com", "clinica-piloto", ""])
def test_is_placeholder_host_is_false_for_real_looking_hosts(host: str) -> None:
    assert not is_placeholder_host(host)


@pytest.mark.parametrize("reference", ["SEC-0000", " sec-0000 ", "CHANGE_ME"])
def test_is_placeholder_reference_is_true_for_template_references(reference: str) -> None:
    assert is_placeholder_reference(reference)


def test_is_placeholder_reference_is_false_for_a_real_reference() -> None:
    assert not is_placeholder_reference("CHG-4821")


@pytest.mark.parametrize("name", ["MEU_PRODUTO_USER_A_SENHA", "CHANGE_ME_X"])
def test_is_placeholder_secret_name_is_true_for_template_names(name: str) -> None:
    assert is_placeholder_secret_name(name)


def test_is_placeholder_secret_name_is_false_for_a_product_name() -> None:
    assert not is_placeholder_secret_name("PILOT_ADMIN_PASSWORD")


@pytest.mark.parametrize(
    "text",
    [
        "https://meu-produto.hml.exemplo.com.br",
        "http://api.example.com:8080/x",
        "env:MEU_PRODUTO_USER_A_LOGIN",
        "keyring:MEU_PRODUTO_X",
        "um CHANGE_ME qualquer",
        "SEC-0000",
        "api.exemplo.com.br",
    ],
)
def test_is_placeholder_text_is_true_for_template_values(text: str) -> None:
    assert is_placeholder_text(text)


@pytest.mark.parametrize(
    "text", ["http://clinica-piloto:8080", "env:PILOT_ADMIN_PASSWORD", "/api/**", "LAB-1", ""]
)
def test_is_placeholder_text_is_false_for_real_values(text: str) -> None:
    assert not is_placeholder_text(text)

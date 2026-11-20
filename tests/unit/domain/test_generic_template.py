"""`generic_template`: o modelo aproximado de caminho dos alertas e sinais sem operação."""

import pytest

from harness_dast.domain.finding import generic_template


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/users/12345/orders", "/api/users/{}/orders"),
        ("/api/users/3f2504e0-4f89-11d3-9a0c-0305e82c3301", "/api/users/{}"),
        ("/api/files/ZXhhbXBsZS10b2tlbi1zZWNyZXRv", "/api/files/{}"),
        ("/api/files/0123456789ab", "/api/files/{}"),
        ("/api/produtos", "/api/produtos"),
        ("/api/v1.2/items", "/api/v1.2/items"),
        ("/api/report-2024", "/api/report-2024"),
        ("/api/produtos?id=1", "/api/produtos"),
    ],
)
def test_generic_template_keeps_the_outputs_that_already_worked(path: str, expected: str) -> None:
    assert generic_template(path) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/u/maria.silva@example.com", "/api/u/{}"),
        ("/api/cpf/123.456.789-09", "/api/cpf/{}"),
        ("/api/dia/2026-11-14", "/api/dia/{}"),
    ],
)
def test_generic_template_generalises_emails_and_punctuated_numbers(
    path: str, expected: str
) -> None:
    assert generic_template(path) == expected

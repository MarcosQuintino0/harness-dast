"""Fingerprint do achado: estável sob o que muda a cada execução, sensível ao que importa."""

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from harness_dast.domain.finding import (
    FINGERPRINT_VERSION,
    compute_fingerprint,
    generic_template,
    normalize_path_template,
)

BASE: dict[str, Any] = {
    "product": "agenda",
    "method": "GET",
    "path_template": "/users/v1/{username}",
    "input_vector": "urlpath",
    "parameter": "",
    "plugin_id": "40018",
    "alert_ref": "40018",
    "cwe": 89,
}


def fp(**changes: Any) -> str:
    return compute_fingerprint(**{**BASE, **changes})


def test_fingerprint_is_a_64_hex_sha256_and_the_version_is_one() -> None:
    value = fp()

    assert len(value) == 64
    assert set(value) <= set("0123456789abcdef")
    assert FINGERPRINT_VERSION == 1


def test_fingerprint_is_deterministic() -> None:
    assert fp() == fp()


def test_renaming_a_path_parameter_does_not_change_the_fingerprint() -> None:
    assert fp(path_template="/users/v1/{username}") == fp(path_template="/users/v1/{login}")


def test_trailing_slash_double_slash_and_query_do_not_change_the_fingerprint() -> None:
    assert fp(path_template="/users/v1/{x}/") == fp(path_template="//users//v1/{x}?a=1")


def test_every_ingredient_changes_the_fingerprint() -> None:
    base = fp()
    changes: list[dict[str, Any]] = [
        {"product": "outro"},
        {"method": "POST"},
        {"path_template": "/users/v1/{username}/email"},
        {"input_vector": "json"},
        {"parameter": "email"},
        {"plugin_id": "40012"},
        {"alert_ref": "40018-2"},
        {"cwe": 79},
        {"cwe": None},
    ]

    assert all(fp(**change) != base for change in changes)
    assert len({fp(**change) for change in changes}) == len(changes)


def test_method_and_vector_are_case_insensitive() -> None:
    assert fp(method="get", input_vector="URLPATH") == fp()


@given(
    template=st.from_regex(r"/[a-z]{1,8}(/(\{[a-z]{1,6}\}|[a-z]{1,8})){0,4}", fullmatch=True),
    rename=st.text(alphabet="abcdefgh", min_size=1, max_size=6),
)
def test_renaming_any_placeholder_keeps_the_fingerprint(template: str, rename: str) -> None:
    renamed = "/".join(
        "{" + rename + "}" if part.startswith("{") else part for part in template.split("/")
    )

    assert fp(path_template=template) == fp(path_template=renamed)


def test_template_normalisation_is_canonical() -> None:
    assert normalize_path_template("/a/{id}/b/") == "/a/{}/b"
    assert normalize_path_template("") == "/"
    assert normalize_path_template("/a?x=1#f") == "/a"


def test_generic_template_replaces_ids_but_keeps_words() -> None:
    assert generic_template("/users/v1/12345") == "/users/v1/{}"
    assert generic_template("/books/550e8400-e29b-41d4-a716-446655440000/x") == "/books/{}/x"
    assert generic_template("/c/0123456789abcdef0123/x") == "/c/{}/x"
    assert generic_template("/files/abcdefghijklmnopqrst1/x") == "/files/{}/x"
    assert generic_template("/users/v1/name1") == "/users/v1/name1"
    assert generic_template("/a?x=1") == "/a"

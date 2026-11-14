import copy
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from harness_dast.adapters.storage.letter_reader import FileLetterReader
from harness_dast.adapters.storage.strict_yaml import parse_profile_yaml
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import LetterReview, review_letter
from harness_dast.domain.profile import ProductProfile
from tests.fakes.letter_data import answer, valid_letter_data

FIXTURES = Path(__file__).parents[2] / "fixtures" / "letter"
TODAY = date(2026, 11, 14)


def _review(data: dict[str, Any], product: str = "demo") -> LetterReview:
    return review_letter(Letter.from_data(data), product, TODAY)


def _issues(review: LetterReview) -> dict[str, str]:
    return {issue.field: issue.code for issue in review.issues}


def _drop(data: dict[str, Any], dotted: str) -> dict[str, Any]:
    *parents, last = dotted.split(".")
    node = data
    for key in parents:
        node = node[key]
    del node[last]
    return data


def _reversed_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _reversed_keys(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reversed_keys(item) for item in value]
    return value


def _generated_profile(review: LetterReview) -> ProductProfile:
    assert review.profile_text is not None
    return ProductProfile.from_data(parse_profile_yaml(review.profile_text))


# ------------------------------------------------------------------ carta válida


def test_review_is_ready_and_profile_validates_when_the_letter_is_complete() -> None:
    review = _review(valid_letter_data())

    assert review.ready
    assert review.issues == ()
    profile = _generated_profile(review)
    assert profile.product == "demo"
    assert profile.environment.base_url == "https://api.hml.acme-teste.net.br"
    assert profile.scope.authorization.reference == "CHG-4821"
    assert profile.limits.requests_per_second == 5
    assert [a.alias for a in profile.auth.accounts] == ["user_a"]


def test_review_matches_the_golden_profile_when_the_clinica_piloto_letter_is_used() -> None:
    raw = FileLetterReader().read(FIXTURES / "clinica-piloto.carta.yml")

    review = review_letter(Letter.from_data(raw), "clinica-piloto", TODAY)

    golden = (FIXTURES / "clinica-piloto.target.golden.yml").read_text(encoding="utf-8")
    assert review.profile_text == golden
    assert review.blocks == ("environment", "openapi", "scope", "limits", "auth", "scan.strength")
    assert [item["field"] for item in review.example_data] == ["nome", "crm"]


def test_review_generates_the_same_text_when_the_key_order_of_the_letter_changes() -> None:
    data = valid_letter_data()
    data["attack"] = {"strength": answer("MEDIUM", "pessoa")}

    first = _review(data)
    second = _review(_reversed_keys(data))

    assert first.profile_text == second.profile_text
    assert first.profile_text is not None


def test_review_does_not_change_the_letter_it_receives() -> None:
    data = valid_letter_data()
    letter = Letter.from_data(data)
    before = copy.deepcopy(letter.model_dump())

    review_letter(letter, "demo", TODAY)

    assert letter.model_dump() == before


def test_review_generated_text_carries_the_gates_but_never_secret_values() -> None:
    review = _review(valid_letter_data())

    assert review.profile_text is not None
    assert "env:ACME_USER_A_SENHA" in review.profile_text
    assert "Dona do Produto" not in review.profile_text


def test_review_emits_strict_path_mode_when_the_letter_does_not_say() -> None:
    profile = _generated_profile(_review(valid_letter_data()))

    assert profile.scope.path_mode == "strict"


def test_review_keeps_the_profile_default_strength_when_the_letter_has_none() -> None:
    review = _review(valid_letter_data())

    assert review.profile_text is not None
    assert "scan:" not in review.profile_text
    assert "scan.strength" not in review.blocks
    assert _generated_profile(review).scan.strength == "LOW"


def test_review_emits_the_strength_when_the_letter_has_it() -> None:
    data = valid_letter_data()
    data["attack"] = {"strength": answer("MEDIUM", "pessoa")}

    review = _review(data)

    assert _generated_profile(review).scan.strength == "MEDIUM"
    assert "scan.strength" in review.blocks


def test_review_ignores_an_unknown_strength_answer() -> None:
    data = valid_letter_data()
    data["attack"] = {"strength": {"source": "desconhecido"}}

    review = _review(data)

    assert review.ready
    assert review.profile_text is not None
    assert "scan:" not in review.profile_text


def test_review_rejects_a_strength_outside_the_closed_list() -> None:
    data = valid_letter_data()
    data["attack"] = {"strength": answer("INSANE", "pessoa")}

    assert _issues(_review(data)) == {"attack.strength": "INVALID_VALUE"}


def test_review_supports_api_key_authentication() -> None:
    data = valid_letter_data()
    data["auth"] = {
        "type": answer("api_key", "pessoa"),
        "header_name": answer("X-API-Key", "pessoa"),
        "accounts": answer(
            [{"alias": "svc_a", "role": "servico", "api_key": {"secret_ref": "env:ACME_SVC_KEY"}}]
        ),
    }

    profile = _generated_profile(_review(data))

    assert profile.auth.type == "api_key"


def test_review_accepts_a_keyring_secret_name() -> None:
    data = valid_letter_data()
    data["auth"]["accounts"]["value"][0]["password"] = {"secret_ref": "keyring:ACME_USER_A_SENHA"}

    assert _review(data).ready


def test_review_accepts_an_empty_deny_list_when_the_person_answered() -> None:
    data = valid_letter_data()
    data["scope"]["deny_paths"] = answer([], "pessoa")

    review = _review(data)

    assert review.ready
    assert _generated_profile(review).scope.deny_paths == ()


# ------------------------------------------------------------------ portões


@pytest.mark.parametrize("gate", ["test_environment", "synthetic_data", "authorization_in_force"])
def test_review_refuses_everything_when_a_gate_is_answered_no(gate: str) -> None:
    data = valid_letter_data()
    data["gates"][gate] = answer(False)
    data["limits"]["requests_per_second"] = answer(-1)  # não deve nem ser lido

    review = _review(data)

    assert _issues(review) == {f"gates.{gate}": "GATE_DENIED"}
    assert review.profile_text is None
    assert not review.ready


@pytest.mark.parametrize("gate", ["test_environment", "synthetic_data", "authorization_in_force"])
def test_review_refuses_everything_when_a_gate_is_unknown(gate: str) -> None:
    data = valid_letter_data()
    data["gates"][gate] = {"source": "desconhecido"}

    review = _review(data)

    assert _issues(review) == {f"gates.{gate}": "UNKNOWN"}
    assert review.profile_text is None


@pytest.mark.parametrize(
    "gate", ["test_environment", "synthetic_data", "authorization_in_force", "product_owner"]
)
def test_review_refuses_everything_when_a_gate_is_missing(gate: str) -> None:
    data = _drop(valid_letter_data(), f"gates.{gate}")

    review = _review(data)

    assert _issues(review) == {f"gates.{gate}": "MISSING"}


@pytest.mark.parametrize("value", ["sim", 1, "true", []])
def test_review_refuses_a_gate_that_is_not_a_boolean(value: object) -> None:
    data = valid_letter_data()
    data["gates"]["test_environment"] = answer(value)

    assert _issues(_review(data)) == {"gates.test_environment": "INVALID_VALUE"}


def test_review_refuses_when_the_letter_is_of_another_product() -> None:
    review = _review(valid_letter_data("outro"), product="demo")

    assert _issues(review) == {"product": "PRODUCT_MISMATCH"}
    assert review.profile_text is None


# ------------------------------------------------------------------ campos obrigatórios

REQUIRED = [
    "environment.name",
    "environment.base_url",
    "environment.openapi",
    "scope.allow",
    "scope.deny_paths",
    "authorization.reference",
    "authorization.valid_until",
    "authorization.windows",
    "limits.requests_per_second",
    "limits.max_duration_minutes",
    "limits.zap_threads_per_host",
    "auth.type",
]


@pytest.mark.parametrize("field", REQUIRED)
def test_review_reports_a_missing_required_field_by_its_path(field: str) -> None:
    review = _review(_drop(valid_letter_data(), field))

    assert _issues(review)[field] == "MISSING"
    assert review.profile_text is None


@pytest.mark.parametrize("field", REQUIRED)
def test_review_reports_an_unknown_answer_on_a_required_field(field: str) -> None:
    data = valid_letter_data()
    section, name = field.split(".")
    data[section][name] = {"source": "desconhecido", "quote": "não está na carta"}

    review = _review(data)

    assert _issues(review)[field] == "UNKNOWN"
    assert "pessoa" in review.issues[0].message


@pytest.mark.parametrize("field", REQUIRED)
def test_review_reports_a_null_value_as_missing(field: str) -> None:
    data = valid_letter_data()
    section, name = field.split(".")
    data[section][name] = {"value": None, "source": "carta"}

    assert _issues(_review(data))[field] == "MISSING"


def test_review_reports_every_missing_field_at_once() -> None:
    data = _drop(_drop(valid_letter_data(), "limits.requests_per_second"), "scope.deny_paths")

    assert _issues(_review(data)) == {
        "limits.requests_per_second": "MISSING",
        "scope.deny_paths": "MISSING",
    }


def test_review_reports_missing_accounts_and_login_path() -> None:
    data = _drop(_drop(valid_letter_data(), "auth.accounts"), "auth.token_path")

    assert _issues(_review(data)) == {"auth.accounts": "MISSING", "auth.token_path": "MISSING"}


def test_review_reports_a_missing_api_key_header() -> None:
    data = valid_letter_data()
    data["auth"] = {
        "type": answer("api_key", "pessoa"),
        "accounts": answer(
            [{"alias": "svc_a", "role": "servico", "api_key": {"secret_ref": "env:ACME_SVC_KEY"}}]
        ),
    }

    assert _issues(_review(data)) == {"auth.header_name": "MISSING"}


def test_review_refuses_login_fields_on_an_api_key_letter() -> None:
    data = valid_letter_data()
    data["auth"]["type"] = answer("api_key", "pessoa")
    data["auth"]["header_name"] = answer("X-API-Key", "pessoa")
    data["auth"]["accounts"] = answer(
        [{"alias": "svc_a", "role": "servico", "api_key": {"secret_ref": "env:ACME_SVC_KEY"}}]
    )

    assert _issues(_review(data)) == {"auth.token_path": "INVALID_VALUE"}


# ------------------------------------------------------------------ valores-modelo


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("environment.base_url", "https://api.exemplo.com.br"),
        ("environment.base_url", "https://api.example.com"),
        ("environment.name", "CHANGE_ME"),
        ("authorization.reference", "SEC-0000"),
        ("authorization.reference", "sec-0000"),
        ("authorization.reference", "CHANGE_ME"),
        ("environment.openapi", "CHANGE_ME/openapi.json"),
    ],
)
def test_review_refuses_a_template_value(path: str, value: str) -> None:
    data = valid_letter_data()
    section, name = path.split(".")
    data[section][name] = answer(value)

    review = _review(data)

    assert _issues(review)[path] == "PLACEHOLDER"
    assert review.profile_text is None


def test_review_refuses_a_template_host_in_a_scope_rule() -> None:
    data = valid_letter_data()
    data["scope"]["allow"]["value"][0]["host"] = "meu-produto.hml.exemplo.com.br"

    assert _issues(_review(data)) == {"scope.allow[0]": "PLACEHOLDER"}


def test_review_refuses_a_template_secret_name() -> None:
    data = valid_letter_data()
    data["auth"]["accounts"]["value"][0]["password"] = {
        "secret_ref": "env:MEU_PRODUTO_USER_A_SENHA"
    }

    assert _issues(_review(data)) == {"auth.accounts[0]": "PLACEHOLDER"}


def test_review_refuses_a_template_value_among_the_windows() -> None:
    data = valid_letter_data()
    data["authorization"]["windows"] = answer(["CHANGE_ME"])

    assert _issues(_review(data)) == {"authorization.windows": "PLACEHOLDER"}


# ------------------------------------------------------------------ segredo no lugar do nome


def test_review_refuses_a_literal_secret_in_place_of_the_secret_name() -> None:
    data = valid_letter_data()
    data["auth"]["accounts"]["value"][0]["password"] = {"secret_ref": "SenhaLiteral-Forte-123!"}

    review = _review(data)

    assert _issues(review) == {"auth.accounts[0].password.secret_ref": "INVALID_VALUE"}
    assert "SenhaLiteral" not in review.issues[0].message


def test_review_refuses_a_bare_secret_where_a_secret_reference_is_expected() -> None:
    data = valid_letter_data()
    data["auth"]["accounts"]["value"][0]["password"] = "SenhaLiteral-Forte-123!"  # noqa: S105 - sentinela

    review = _review(data)

    assert "auth.accounts[0].password" in _issues(review)
    assert all("SenhaLiteral" not in issue.message for issue in review.issues)


def test_review_refuses_a_secret_name_reserved_to_the_harness() -> None:
    data = valid_letter_data()
    data["auth"]["accounts"]["value"][0]["password"] = {"secret_ref": "env:HDAST_ZAP_API_KEY"}

    assert _issues(_review(data)) == {"auth.accounts[0].password.secret_ref": "INVALID_VALUE"}


def test_review_refuses_a_duplicated_account_alias() -> None:
    data = valid_letter_data()
    account = copy.deepcopy(data["auth"]["accounts"]["value"][0])
    data["auth"]["accounts"]["value"].append(account)

    review = _review(data)

    assert [issue.code for issue in review.issues] == ["PROFILE_REJECTED"]


# ------------------------------------------------------------------ path_mode


def test_review_refuses_wide_when_the_source_is_not_the_letter() -> None:
    data = valid_letter_data()
    data["scope"]["path_mode"] = answer("wide", "pessoa", "a pessoa disse que pode")

    review = _review(data)

    assert _issues(review) == {"scope.path_mode": "WIDE_NEEDS_LETTER"}
    assert review.profile_text is None


def test_review_refuses_wide_when_the_letter_answer_has_no_quote() -> None:
    data = valid_letter_data()
    data["scope"]["path_mode"] = answer("wide", "carta")

    assert _issues(_review(data)) == {"scope.path_mode": "WIDE_NEEDS_LETTER"}


def test_review_refuses_wide_when_the_quote_is_blank() -> None:
    data = valid_letter_data()
    data["scope"]["path_mode"] = answer("wide", "carta", "   ")

    assert _issues(_review(data)) == {"scope.path_mode": "WIDE_NEEDS_LETTER"}


def test_review_accepts_wide_only_with_the_letter_as_source_and_a_quote() -> None:
    data = valid_letter_data()
    data["scope"]["path_mode"] = answer("wide", "carta", "Modo amplo: risco aceito pelo dono.")

    review = _review(data)

    assert _generated_profile(review).scope.path_mode == "wide"


def test_review_falls_back_to_strict_when_the_path_mode_is_unknown() -> None:
    data = valid_letter_data()
    data["scope"]["path_mode"] = {"source": "desconhecido"}

    assert _generated_profile(_review(data)).scope.path_mode == "strict"


@pytest.mark.parametrize("value", ["WIDE", "amplo", 1, True, []])
def test_review_refuses_a_path_mode_outside_the_closed_list(value: object) -> None:
    data = valid_letter_data()
    data["scope"]["path_mode"] = answer(value, "carta", "x")

    assert _issues(_review(data)) == {"scope.path_mode": "INVALID_VALUE"}


# ------------------------------------------------------------------ valores inválidos


def test_review_refuses_a_local_host_without_allow_local() -> None:
    data = valid_letter_data()
    data["scope"]["allow"]["value"][0]["host"] = "clinica-piloto"
    data["environment"]["base_url"] = answer("http://clinica-piloto:8080")

    review = _review(data)

    assert list(_issues(review)) == ["scope.allow[0]"]
    assert "allow_local" in review.issues[0].message


def test_review_refuses_a_scope_rule_with_an_unknown_key() -> None:
    data = valid_letter_data()
    data["scope"]["allow"]["value"][0]["wildcard"] = True

    assert _issues(_review(data)) == {"scope.allow[0].wildcard": "INVALID_VALUE"}


def test_review_refuses_a_scope_rule_without_methods() -> None:
    data = valid_letter_data()
    del data["scope"]["allow"]["value"][0]["methods"]

    assert _issues(_review(data)) == {"scope.allow[0].methods": "INVALID_VALUE"}


def test_review_refuses_a_scope_rule_that_is_not_a_map() -> None:
    data = valid_letter_data()
    data["scope"]["allow"]["value"] = ["/api/**"]

    assert _issues(_review(data)) == {"scope.allow[0]": "INVALID_VALUE"}


def test_review_refuses_an_empty_allow_list() -> None:
    data = valid_letter_data()
    data["scope"]["allow"] = answer([])

    assert _issues(_review(data)) == {"scope.allow": "INVALID_VALUE"}


def test_review_refuses_a_deny_pattern_that_is_not_text() -> None:
    data = valid_letter_data()
    data["scope"]["deny_paths"] = answer([1])

    assert _issues(_review(data)) == {"scope.deny_paths": "INVALID_VALUE"}


def test_review_refuses_a_deny_pattern_with_an_ambiguous_path() -> None:
    data = valid_letter_data()
    data["scope"]["deny_paths"] = answer(["/api/../admin"])

    assert _issues(_review(data)) == {"scope.deny_paths": "INVALID_VALUE"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("requests_per_second", 0),
        ("requests_per_second", -3),
        ("requests_per_second", 100000),
        ("requests_per_second", "rápido"),
        ("requests_per_second", True),
        ("max_duration_minutes", 0),
        ("max_duration_minutes", 5.5),
        ("zap_threads_per_host", 0),
        ("zap_threads_per_host", 10_000),
    ],
)
def test_review_refuses_an_invalid_limit(field: str, value: object) -> None:
    data = valid_letter_data()
    data["limits"][field] = answer(value)

    assert _issues(_review(data)) == {f"limits.{field}": "INVALID_VALUE"}


@pytest.mark.parametrize("window", ["sempre", "seg-sex 25:00-06:00 UTC", "seg 20:00-20:00 UTC", 5])
def test_review_refuses_an_invalid_window(window: object) -> None:
    data = valid_letter_data()
    data["authorization"]["windows"] = answer([window])

    assert _issues(_review(data)) == {"authorization.windows[0]": "INVALID_VALUE"}


def test_review_refuses_an_empty_window_list() -> None:
    data = valid_letter_data()
    data["authorization"]["windows"] = answer([])

    assert _issues(_review(data)) == {"authorization.windows": "INVALID_VALUE"}


@pytest.mark.parametrize("value", ["31/12/2027", "2027-12-31T10:00:00", 20271231, "amanhã"])
def test_review_refuses_a_validity_date_in_the_wrong_format(value: object) -> None:
    data = valid_letter_data()
    data["authorization"]["valid_until"] = answer(value)

    assert _issues(_review(data)) == {"authorization.valid_until": "INVALID_VALUE"}


def test_review_refuses_a_base_url_with_a_query() -> None:
    data = valid_letter_data()
    data["environment"]["base_url"] = answer("https://api.hml.acme-teste.net.br/?x=1")

    assert _issues(_review(data)) == {"environment.base_url": "INVALID_VALUE"}


def test_review_refuses_a_base_url_that_the_scope_does_not_cover() -> None:
    data = valid_letter_data()
    data["environment"]["base_url"] = answer("https://outro.hml.acme-teste.net.br")

    review = _review(data)

    assert [issue.code for issue in review.issues] == ["PROFILE_REJECTED"]
    assert review.issues[0].field == "(perfil gerado)"
    assert review.profile_text is None


def test_review_refuses_an_openapi_path_that_escapes_the_product_folder() -> None:
    data = valid_letter_data()
    data["environment"]["openapi"] = answer("../../etc/passwd", "pessoa")

    assert [issue.code for issue in _review(data).issues] == ["PROFILE_REJECTED"]


def test_review_refuses_a_login_path_that_the_scope_does_not_allow() -> None:
    data = valid_letter_data()
    data["auth"]["token_path"] = answer("/login-fora-do-escopo", "pessoa")

    assert [issue.code for issue in _review(data).issues] == ["PROFILE_REJECTED"]


@pytest.mark.parametrize("value", ["oauth2", "form", 3])
def test_review_refuses_an_unknown_auth_type(value: object) -> None:
    data = valid_letter_data()
    data["auth"]["type"] = answer(value, "pessoa")

    assert "auth.type" in _issues(_review(data))


def test_review_refuses_an_unknown_login_option() -> None:
    data = valid_letter_data()
    data["auth"]["login_options"] = answer({"verify_ssl": "false"}, "pessoa")

    assert _issues(_review(data)) == {"auth.login_options": "INVALID_VALUE"}


def test_review_refuses_an_invalid_login_limit() -> None:
    data = valid_letter_data()
    data["auth"]["login_max_per_minute"] = answer(0)

    assert _issues(_review(data)) == {"auth.login_max_per_minute.max_per_minute": "INVALID_VALUE"}


def test_review_generates_the_login_limit_when_the_letter_has_it() -> None:
    data = valid_letter_data()
    data["auth"]["login_max_per_minute"] = answer(5)
    data["auth"]["login_options"] = answer({"request_encoding": "json"}, "pessoa")

    profile = _generated_profile(_review(data))

    assert profile.login_limit is not None
    assert profile.login_limit.max_per_minute == 5


def test_review_refuses_example_data_that_is_not_a_list_of_maps() -> None:
    data = valid_letter_data()
    data["example_data"] = answer("laudo-0001.txt")

    assert _issues(_review(data)) == {"example_data": "INVALID_VALUE"}


def test_review_keeps_example_data_as_information_only() -> None:
    data = valid_letter_data()
    data["example_data"] = answer([{"field": "crm", "value": "12345-SP"}])

    review = _review(data)

    assert review.example_data == ({"field": "crm", "value": "12345-SP"},)
    assert review.profile_text is not None
    assert "12345-SP" not in review.profile_text


def test_review_never_widens_the_scope_beyond_what_the_letter_lists() -> None:
    data = valid_letter_data()

    profile = _generated_profile(_review(data))

    assert [rule.methods for rule in profile.scope.allow] == [("GET", "POST")]
    assert profile.scope.allow[0].paths == ("/api/**",)
    assert profile.scope.deny_paths == ("/api/admin/**",)

import pytest
from pydantic import ValidationError

from harness_dast.domain.api_model import (
    ApiSpec,
    MediaBody,
    Operation,
    Parameter,
    RequestBody,
    SecurityRequirement,
    SuccessResponse,
    safe_identifier,
    synthesize_operation_id,
)
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import ConfigError


def op(operation_id: str = "a", path: str = "/a", **kwargs: object) -> Operation:
    return Operation.model_validate(
        {"operation_id": operation_id, "method": "get", "path": path, **kwargs}
    )


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/users/v1/{username}/email", "get_users_v1_by_username_email"),
        ("post", "/", "post_root"),
        ("get", "/a-b/c.d", "get_a_b_c_d"),
        ("delete", "/x/{id}", "delete_x_by_id"),
        ("get", "//a//b/", "get_a_b"),
    ],
)
def test_synthesize_operation_id_is_deterministic_and_readable(
    method: str, path: str, expected: str
) -> None:
    assert synthesize_operation_id(method, path) == expected


def test_synthesize_operation_id_is_capped_at_120_characters() -> None:
    assert len(synthesize_operation_id("get", "/" + "a" * 500)) == 120


def test_safe_identifier_quotes_and_neutralises_control_characters() -> None:
    assert safe_identifier("a\nb\x1b[31m") == "'a?b?[31m'"


def test_safe_identifier_truncates_long_text() -> None:
    shown = safe_identifier("x" * 500)

    assert len(shown) == 62
    assert shown.endswith("...'")


def test_operation_rejects_path_without_leading_slash() -> None:
    with pytest.raises(ValidationError):
        op(path="a")


def test_operation_rejects_control_characters_in_the_identifier() -> None:
    with pytest.raises(ValidationError):
        op(operation_id="a\nb")


def test_operation_rejects_repeated_parameter_with_same_name_and_location() -> None:
    parameter = {"name": "q", "location": "query"}

    with pytest.raises(ValidationError):
        op(parameters=[parameter, parameter])


def test_operation_allows_same_name_in_different_locations() -> None:
    operation = op(
        parameters=[{"name": "id", "location": "query"}, {"name": "id", "location": "header"}]
    )

    assert len(operation.parameters) == 2


def test_operation_exposes_path_placeholders_in_order() -> None:
    assert op(path="/a/{x}/b/{y}").path_placeholders == ("x", "y")


def test_operation_success_codes_follow_declared_responses() -> None:
    operation = op(success_responses=[{"status": "201"}, {"status": "200"}])

    assert operation.success_codes == ("201", "200")


def test_operation_requires_auth_only_when_every_alternative_needs_a_scheme() -> None:
    both = [SecurityRequirement(schemes=("a",)), SecurityRequirement(schemes=("b",))]
    anonymous_allowed = [SecurityRequirement(schemes=("a",)), SecurityRequirement()]

    assert op(security=both).requires_auth
    assert not op(security=anonymous_allowed).requires_auth
    assert not op().requires_auth


def test_operation_success_schema_is_the_first_declared_schema() -> None:
    responses = (
        SuccessResponse(status="204"),
        SuccessResponse(status="200", body_schema=Schema(type="object")),
    )

    assert op(success_responses=responses).success_schema() == Schema(type="object")
    assert op().success_schema() is None


def test_request_body_prefers_application_json() -> None:
    body = RequestBody(
        media=(
            MediaBody(media_type="application/xml"),
            MediaBody(media_type="application/json; charset=utf-8"),
        )
    )

    preferred = body.preferred()
    assert preferred is not None
    assert preferred.media_type.startswith("application/json")


def test_request_body_falls_back_to_a_plus_json_type_then_to_the_first() -> None:
    plus_json = RequestBody(
        media=(MediaBody(media_type="text/plain"), MediaBody(media_type="application/vnd.x+json"))
    )
    other = RequestBody(media=(MediaBody(media_type="text/plain"),))

    assert plus_json.preferred() == plus_json.media[1]
    assert other.preferred() == other.media[0]
    assert RequestBody().preferred() is None


def test_api_spec_rejects_duplicate_operation_ids() -> None:
    with pytest.raises(ValidationError):
        ApiSpec(title="t", version="1", operations=(op("a"), op("a", "/b")))


def test_get_operation_returns_the_operation() -> None:
    spec = ApiSpec(title="t", version="1", operations=(op("a"),))

    assert spec.get_operation("a").path == "/a"
    assert spec.has_operation("a")
    assert not spec.has_operation("z")


def test_get_operation_raises_config_error_with_known_ids_when_missing() -> None:
    spec = ApiSpec(title="t", version="1", operations=(op("a"),))

    with pytest.raises(ConfigError) as caught:
        spec.get_operation("z\nz")

    assert "'z?z'" in caught.value.message
    assert "'a'" in (caught.value.hint or "")


def test_parameter_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        Parameter(name="", location="query")

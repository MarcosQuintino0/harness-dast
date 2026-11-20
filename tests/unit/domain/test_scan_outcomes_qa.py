"""QA independente (V1.5c): a flag de classes extras nunca amplia o que o perfil (a carta) lista."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.scan_config import EXTRA_OUTCOMES
from harness_dast.domain.scan_plan import resolve_include_outcomes

NAMES = sorted(EXTRA_OUTCOMES)
ANY_TEXT = st.one_of(st.sampled_from(NAMES), st.text(max_size=20))


@given(
    st.lists(st.sampled_from(NAMES), unique=True, max_size=5),
    st.one_of(st.none(), st.lists(ANY_TEXT, max_size=6)),
)
def test_the_resolved_classes_are_always_inside_the_profile_list(
    profile: list[str], requested: list[str] | None
) -> None:
    try:
        resolved = resolve_include_outcomes(profile, requested)
    except ConfigError:
        return

    assert set(resolved) <= set(profile)
    if requested is None:
        assert resolved == tuple(profile)
    else:
        assert set(resolved) == set(requested)


@pytest.mark.parametrize("requested", [["success"], ["server_error"], ["auth_error"], [""], ["*"]])
def test_classes_outside_the_closed_list_are_refused_even_if_the_profile_lists_them(
    requested: list[str],
) -> None:
    with pytest.raises(ConfigError):
        resolve_include_outcomes([*requested, *NAMES], requested)


def test_an_empty_request_reduces_to_nothing_and_an_empty_profile_allows_nothing() -> None:
    assert resolve_include_outcomes(NAMES, ()) == ()
    assert resolve_include_outcomes((), None) == ()
    with pytest.raises(ConfigError):
        resolve_include_outcomes((), ["not_found"])


def test_a_repeated_requested_class_is_not_a_way_around_the_profile() -> None:
    with pytest.raises(ConfigError):
        resolve_include_outcomes(["conflict"], ["conflict", "not_found", "conflict"])

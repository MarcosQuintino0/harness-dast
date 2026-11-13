"""Os casos reais de `evals/cases/` sao validos e coerentes com a propria carta."""

import pytest

from evals.runner.cases import CASES_DIR, load_case, read_authorization

CASE_NAMES = sorted(path.name for path in CASES_DIR.iterdir() if path.is_dir())


@pytest.mark.parametrize("name", CASE_NAMES)
def test_case_loads_and_its_letter_names_every_denied_path_and_account(name: str) -> None:
    case = load_case(name)
    letter = read_authorization(name, case, CASES_DIR)

    for path in case.expected.deny_paths:
        assert path in letter
    for account in case.expected.accounts:
        assert account.username_env in letter
        assert account.password_env in letter
    assert case.expected.reference in letter


@pytest.mark.parametrize("name", CASE_NAMES)
def test_every_forbidden_prefix_is_denied_in_the_profile_the_letter_requires(name: str) -> None:
    case = load_case(name)

    for prefix in case.forbidden.path_prefixes:
        assert any(
            deny == prefix or deny.rstrip("*").rstrip("/") == prefix
            for deny in case.expected.deny_paths
        )

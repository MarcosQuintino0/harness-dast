from pathlib import Path
from typing import Any

import pytest

from harness_dast.application.init_from_letter import InitFromLetter, rejection
from harness_dast.domain.errors import ConfigError, ExitCode, LetterRejected
from tests.fakes.clock import FixedClock, utc
from tests.fakes.letter_data import answer, request_letter_data, valid_letter_data
from tests.fakes.letter_reader import InMemoryLetterReader
from tests.fakes.product_scaffolder import InMemoryScaffolder
from tests.fakes.spec_paths import InMemorySpecPaths

LETTER = Path("carta.yml")


def _use_case(
    data: dict[str, Any] | None = None,
) -> tuple[InitFromLetter, InMemoryScaffolder, InMemoryLetterReader]:
    reader = InMemoryLetterReader({"carta.yml": data if data is not None else valid_letter_data()})
    scaffolder = InMemoryScaffolder(files=("README.md", "target.yml"))
    return InitFromLetter(reader, scaffolder, FixedClock(utc(2026, 11, 14))), scaffolder, reader


def test_execute_creates_the_product_with_the_generated_profile_when_the_letter_is_ready() -> None:
    use_case, scaffolder, _ = _use_case()

    outcome = use_case.execute("demo", LETTER)

    assert outcome.ready
    assert outcome.created is not None
    assert outcome.created.directory == "/produtos/demo"
    text = scaffolder.target_texts["demo"]
    assert text is not None
    assert 'product: "demo"' in text
    assert outcome.generated_blocks[0] == "environment"
    assert outcome.issues == ()


def test_execute_creates_nothing_when_the_letter_has_issues() -> None:
    data = valid_letter_data()
    data["gates"]["synthetic_data"] = answer(False)
    use_case, scaffolder, _ = _use_case(data)

    outcome = use_case.execute("demo", LETTER)

    assert not outcome.ready
    assert outcome.created is None
    assert scaffolder.created == {}
    assert [i.field for i in outcome.issues] == ["gates.synthetic_data"]


def test_check_never_creates_the_product_even_when_the_letter_is_ready() -> None:
    use_case, scaffolder, _ = _use_case()

    outcome = use_case.check("demo", LETTER)

    assert outcome.ready
    assert outcome.created is None
    assert scaffolder.created == {}


def test_execute_passes_with_cleanup_to_the_scaffolder() -> None:
    use_case, scaffolder, _ = _use_case()

    use_case.execute("demo", LETTER, with_cleanup=True)

    assert scaffolder.cleanup_requested["demo"] is True


def test_execute_raises_when_the_product_already_exists_and_keeps_the_first_one() -> None:
    use_case, scaffolder, _ = _use_case()
    first = use_case.execute("demo", LETTER)

    with pytest.raises(ConfigError):
        use_case.execute("demo", LETTER)

    assert scaffolder.created["demo"] == first.created


def test_execute_raises_when_the_letter_file_does_not_exist() -> None:
    use_case, scaffolder, _ = _use_case()

    with pytest.raises(ConfigError):
        use_case.execute("demo", Path("nao-existe.yml"))

    assert scaffolder.created == {}


def test_execute_raises_when_the_letter_has_an_unknown_field() -> None:
    data = valid_letter_data()
    data["campo_inventado"] = {}
    use_case, scaffolder, _ = _use_case(data)

    with pytest.raises(ConfigError, match="campo_inventado"):
        use_case.execute("demo", LETTER)

    assert scaffolder.created == {}


def test_execute_refuses_the_letter_of_another_product() -> None:
    use_case, scaffolder, _ = _use_case(valid_letter_data("outro"))

    outcome = use_case.execute("demo", LETTER)

    assert [i.code for i in outcome.issues] == ["PRODUCT_MISMATCH"]
    assert scaffolder.created == {}


def test_rejection_lists_every_field_and_says_the_answer_comes_from_the_person() -> None:
    data = valid_letter_data()
    del data["limits"]["requests_per_second"]
    del data["scope"]["deny_paths"]
    use_case, _, _ = _use_case(data)

    error = rejection(use_case.check("demo", LETTER))

    assert isinstance(error, LetterRejected)
    assert error.code == "LETTER_REJECTED"
    assert error.exit_code == ExitCode.USAGE
    assert "2 pendência(s)" in error.message
    assert "limits.requests_per_second [MISSING]" in error.message
    assert "scope.deny_paths [MISSING]" in error.message
    assert error.hint is not None
    assert "agente não preenche" in error.hint


def test_execute_refuses_a_letter_whose_authorization_already_expired_and_creates_nothing() -> None:
    data = valid_letter_data()
    data["authorization"]["valid_until"] = answer("2026-11-13")
    use_case, scaffolder, _ = _use_case(data)

    outcome = use_case.execute("demo", LETTER)

    assert not outcome.ready
    assert outcome.created is None
    assert scaffolder.created == {}
    assert [(i.field, i.code) for i in outcome.issues] == [
        ("authorization.valid_until", "AUTHORIZATION_EXPIRED")
    ]


def test_check_uses_the_injected_clock_so_the_same_letter_expires_when_the_clock_advances() -> None:
    data = valid_letter_data()
    data["authorization"]["valid_until"] = answer("2026-12-31")
    reader = InMemoryLetterReader({"carta.yml": data})
    clock = FixedClock(utc(2026, 12, 31, 23, 59))
    use_case = InitFromLetter(reader, InMemoryScaffolder(files=("target.yml",)), clock)

    assert use_case.check("demo", LETTER).ready

    clock.advance_to(utc(2027, 1, 1))

    assert not use_case.check("demo", LETTER).ready


def test_outcome_carries_the_warnings_of_a_ready_letter() -> None:
    use_case, _, _ = _use_case()

    outcome = use_case.check("demo", LETTER)

    assert outcome.ready
    assert [w.code for w in outcome.warnings] == ["VALIDITY_OVER_ONE_YEAR"]


# --- pedido mínimo (ADR 0120) -----------------------------------------------------------------

REQUEST_LETTER = Path("pasta-da-carta") / "carta.yml"
REQUEST_PATHS = ("/api/auth/login", "/api/users/{id}", "/api/auth/forgot-password")


def _request_use_case(
    specs: dict[str, tuple[str, ...]] | None = None, timezone: str = "UTC"
) -> tuple[InitFromLetter, InMemoryScaffolder, InMemorySpecPaths]:
    data = request_letter_data()
    data["auth"]["token_path"] = answer("/api/auth/login", "pessoa")
    reader = InMemoryLetterReader({"carta.yml": data})
    scaffolder = InMemoryScaffolder(files=("README.md", "target.yml"))
    paths = InMemorySpecPaths({"./openapi.json": REQUEST_PATHS} if specs is None else specs)
    use_case = InitFromLetter(
        reader, scaffolder, FixedClock(utc(2026, 11, 14)), spec_paths=paths, timezone=timezone
    )
    return use_case, scaffolder, paths


def test_execute_creates_the_product_from_the_request_letter_reading_the_spec_next_to_it() -> None:
    use_case, scaffolder, paths = _request_use_case()

    outcome = use_case.execute("demo", REQUEST_LETTER)

    assert outcome.ready, outcome.issues
    assert paths.reads == [(Path("pasta-da-carta"), "./openapi.json")]
    text = scaffolder.target_texts["demo"]
    assert text is not None
    assert "/api/users/*" in text
    assert "seg-dom 00:00-24:00 UTC" in text
    assert "valid_until: 2026-12-14" in text
    assert {w.code for w in outcome.warnings} >= {"REQUEST_DEFAULT_APPLIED"}


def test_check_reports_the_request_defaults_without_creating_anything() -> None:
    use_case, scaffolder, _ = _request_use_case()

    outcome = use_case.check("demo", REQUEST_LETTER)

    assert outcome.ready
    assert outcome.created is None
    assert scaffolder.created == {}
    assert "scope.deny_paths" in {w.field for w in outcome.warnings}


def test_execute_creates_nothing_when_the_spec_cannot_be_read() -> None:
    use_case, scaffolder, _ = _request_use_case(specs={})

    outcome = use_case.execute("demo", REQUEST_LETTER)

    assert not outcome.ready
    assert scaffolder.created == {}
    assert [(i.field, i.code) for i in outcome.issues] == [
        ("environment.openapi", "OPENAPI_UNREADABLE")
    ]
    assert "Ponha-o ao lado da carta" in outcome.issues[0].message


def test_execute_asks_for_the_spec_when_the_request_letter_has_no_openapi_answer() -> None:
    data = request_letter_data()
    del data["environment"]["openapi"]
    reader = InMemoryLetterReader({"carta.yml": data})
    scaffolder = InMemoryScaffolder(files=("target.yml",))
    paths = InMemorySpecPaths({})
    use_case = InitFromLetter(reader, scaffolder, FixedClock(utc(2026, 11, 14)), paths)

    outcome = use_case.execute("demo", REQUEST_LETTER)

    assert [i.code for i in outcome.issues] == ["OPENAPI_UNREADABLE"]
    assert paths.reads == []


def test_execute_does_not_read_the_spec_when_the_letter_is_a_signed_letter() -> None:
    reader = InMemoryLetterReader({"carta.yml": valid_letter_data()})
    paths = InMemorySpecPaths({})
    use_case = InitFromLetter(
        reader,
        InMemoryScaffolder(files=("target.yml",)),
        FixedClock(utc(2026, 11, 14)),
        spec_paths=paths,
    )

    outcome = use_case.execute("demo", LETTER)

    assert outcome.ready
    assert paths.reads == []


def test_execute_asks_for_the_spec_when_no_spec_reader_was_wired() -> None:
    data = request_letter_data()
    reader = InMemoryLetterReader({"carta.yml": data})
    use_case = InitFromLetter(
        reader, InMemoryScaffolder(files=("target.yml",)), FixedClock(utc(2026, 11, 14))
    )

    outcome = use_case.check("demo", REQUEST_LETTER)

    assert [i.code for i in outcome.issues] == ["OPENAPI_UNREADABLE"]

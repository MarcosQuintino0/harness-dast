from pathlib import Path
from typing import Any

import pytest

from harness_dast.application.init_from_letter import InitFromLetter, rejection
from harness_dast.domain.errors import ConfigError, ExitCode, LetterRejected
from tests.fakes.letter_data import answer, valid_letter_data
from tests.fakes.letter_reader import InMemoryLetterReader
from tests.fakes.product_scaffolder import InMemoryScaffolder

LETTER = Path("carta.yml")


def _use_case(
    data: dict[str, Any] | None = None,
) -> tuple[InitFromLetter, InMemoryScaffolder, InMemoryLetterReader]:
    reader = InMemoryLetterReader({"carta.yml": data if data is not None else valid_letter_data()})
    scaffolder = InMemoryScaffolder(files=("README.md", "target.yml"))
    return InitFromLetter(reader, scaffolder), scaffolder, reader


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

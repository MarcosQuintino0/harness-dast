import pytest

from harness_dast.application.init_product import InitProduct
from harness_dast.domain.errors import ConfigError
from tests.fakes.product_scaffolder import InMemoryScaffolder


def test_init_returns_created_product_when_name_is_new() -> None:
    scaffolder = InMemoryScaffolder(files=("README.md", "target.yml"))

    result = InitProduct(scaffolder).execute("demo")

    assert result.directory == "/produtos/demo"
    assert result.files == ("README.md", "target.yml")
    assert "demo" in scaffolder.created


def test_init_raises_config_error_when_product_already_exists() -> None:
    use_case = InitProduct(InMemoryScaffolder())
    use_case.execute("demo")

    with pytest.raises(ConfigError):
        use_case.execute("demo")


def test_init_keeps_first_product_untouched_when_second_attempt_fails() -> None:
    scaffolder = InMemoryScaffolder(files=("a",))
    use_case = InitProduct(scaffolder)
    first = use_case.execute("demo")

    with pytest.raises(ConfigError):
        use_case.execute("demo")

    assert scaffolder.created["demo"] == first


def test_init_does_not_ask_for_cleanup_folder_by_default() -> None:
    scaffolder = InMemoryScaffolder()

    InitProduct(scaffolder).execute("demo")

    assert scaffolder.cleanup_requested["demo"] is False


def test_init_asks_for_cleanup_folder_when_requested() -> None:
    scaffolder = InMemoryScaffolder()

    InitProduct(scaffolder).execute("demo", with_cleanup=True)

    assert scaffolder.cleanup_requested["demo"] is True

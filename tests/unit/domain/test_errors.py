import pytest

from harness_dast.domain.errors import (
    CleanupError,
    ConfigError,
    ExitCode,
    ExternalToolError,
    HarnessError,
    PreflightError,
    ScopeViolation,
    StackBusy,
    TargetError,
    UserInterrupt,
)


@pytest.mark.parametrize(
    ("error_type", "code", "exit_code"),
    [
        (HarnessError, "INTERNAL", 10),
        (ConfigError, "CONFIG_ERROR", 2),
        (ScopeViolation, "SCOPE_VIOLATION", 3),
        (PreflightError, "PREFLIGHT_FAILED", 4),
        (ExternalToolError, "EXTERNAL_TOOL_ERROR", 5),
        (TargetError, "TARGET_ERROR", 6),
        (CleanupError, "CLEANUP_FAILED", 7),
        (StackBusy, "STACK_BUSY", 8),
        (UserInterrupt, "INTERRUPTED", 130),
    ],
)
def test_error_exposes_stable_code_and_exit_code_when_instantiated(
    error_type: type[HarnessError], code: str, exit_code: int
) -> None:
    error = error_type("algo aconteceu")

    assert error.code == code
    assert error.exit_code == exit_code


def test_error_keeps_message_and_hint_when_given() -> None:
    error = ScopeViolation("host fora do escopo", hint="peça ao dono do produto")

    assert error.message == "host fora do escopo"
    assert error.hint == "peça ao dono do produto"
    assert str(error) == "host fora do escopo"


def test_error_hint_is_none_when_omitted() -> None:
    assert ConfigError("inválido").hint is None


def test_all_specific_errors_are_harness_errors_when_checked() -> None:
    for error_type in (ConfigError, ScopeViolation, PreflightError, ExternalToolError):
        assert issubclass(error_type, HarnessError)


def test_exit_codes_match_public_contract_when_listed() -> None:
    assert {c.name: int(c) for c in ExitCode} == {
        "OK": 0,
        "FINDINGS": 1,
        "USAGE": 2,
        "SCOPE": 3,
        "PREFLIGHT": 4,
        "EXTERNAL_TOOL": 5,
        "TARGET": 6,
        "CLEANUP": 7,
        "BUSY": 8,
        "INTERNAL": 10,
        "INTERRUPTED": 130,
    }

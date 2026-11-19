import pytest
from pydantic import ValidationError

from harness_dast.domain.nuclei_command import (
    NUCLEI_FORBIDDEN_FLAGS,
    NucleiCommandInput,
    build_nuclei_args,
)

_REQUIRED = ["-ni", "-duc", "-pt", "-jsonl", "-omit-raw", "-nc", "-proxy", "-rl", "-c"]


def _input(**changes: object) -> NucleiCommandInput:
    data: dict[str, object] = {
        "target_url": "https://api.hml.acme-teste.net.br",
        "proxy_url": "http://scope-proxy-nuclei:3128",
        "requests_per_second": 5,
        "concurrency": 2,
        "templates_list_path": "/work/templates.txt",
    }
    data.update(changes)
    return NucleiCommandInput.model_validate(data)


def test_includes_the_safety_flags_quando_building_args() -> None:
    args = build_nuclei_args(_input())

    assert all(flag in args for flag in _REQUIRED)
    assert args[args.index("-pt") + 1] == "http"
    assert args[args.index("-rl") + 1] == "5"
    assert args[args.index("-c") + 1] == "2"
    assert args[args.index("-proxy") + 1] == "http://scope-proxy-nuclei:3128"


@pytest.mark.parametrize("with_file", [False, True])
def test_never_includes_forbidden_flags_quando_building_args(with_file: bool) -> None:
    path = "/run/nuclei/creds.yaml" if with_file else None

    args = build_nuclei_args(_input(secret_file_path=path))

    assert not NUCLEI_FORBIDDEN_FLAGS & set(args)


def test_omits_sf_quando_there_is_no_file() -> None:
    assert "-sf" not in build_nuclei_args(_input())


def test_passes_only_the_file_path_quando_login_is_used() -> None:
    marker = "VALOR-SINTETICO-123"

    args = build_nuclei_args(_input(secret_file_path="/run/nuclei/creds.yaml"))  # noqa: S106

    assert args[args.index("-sf") + 1] == "/run/nuclei/creds.yaml"
    assert marker not in " ".join(args)


@pytest.mark.parametrize(
    "changes",
    [
        {"target_url": "-dast"},
        {"proxy_url": ""},
        {"templates_list_path": "-code"},
        {"secret_file_path": "-auth"},
        {"target_url": "https://x\nnew"},
        {"requests_per_second": 0},
        {"requests_per_second": 1.5},
        {"concurrency": 0},
        {"unexpected": "x"},
    ],
)
def test_rejects_the_input_quando_it_is_invalid(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _input(**changes)

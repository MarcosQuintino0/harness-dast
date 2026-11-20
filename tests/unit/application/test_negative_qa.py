"""QA independente do `negative` (V1.5c): travas, orçamento, vazamento e entradas hostis."""

import json
from typing import Any

import pytest

from harness_dast.application.negative import NegativeRequest
from harness_dast.domain.errors import ConfigError
from tests.fakes.negative_rig import (
    ADJUST,
    CREATE,
    LIST,
    PRODUCTS,
    REMOVE,
    SENT_MARKERS,
    UPDATE,
    Catalog,
    NegativeRig,
    catalog_profile_data,
    exchange,
)


def reasons(result: Any) -> list[str]:
    return [item.reason for item in result.not_tested]


def test_the_request_budget_also_counts_the_429_retries_of_the_dispatcher() -> None:
    rig = NegativeRig(Catalog(forced={("GET", "api/produtos"): 429}), max_requests=1)

    result = rig.run(LIST)

    assert len(rig.sent()) <= 1
    assert result.requests_sent <= 1


def test_a_budget_of_three_with_a_constant_429_sends_no_more_than_three() -> None:
    rig = NegativeRig(Catalog(forced={("GET", "api/produtos"): 429}), max_requests=3)

    result = rig.run(LIST)

    assert len(rig.sent()) <= 3
    assert result.requests_sent <= 3


def test_a_write_whose_omitted_field_is_optional_is_still_tested() -> None:
    omitted = exchange(
        "atualizarProduto",
        "PUT",
        f"{PRODUCTS}/{{id}}",
        f"{PRODUCTS}/1",
        body={"nome": "Caneta", "preco": 2},
        omitted=("segredo_opcional",),
    )
    rig = NegativeRig(Catalog(mode="validate"), allow_writes=True)

    result = rig.run(omitted)

    assert "omitted_required_field" not in reasons(result)


def test_a_write_whose_baseline_body_misses_a_required_omitted_field_is_not_tested() -> None:
    omitted = exchange(
        "atualizarProduto",
        "PUT",
        f"{PRODUCTS}/{{id}}",
        f"{PRODUCTS}/1",
        body={"nome": "Caneta", "status": "ativo"},
        omitted=("preco",),
    )
    rig = NegativeRig(Catalog(mode="validate"), allow_writes=True)

    result = rig.run(omitted)

    sent = rig.sent("PUT")
    counted_as_rejected = sum(row.rejected for row in result.by_class)
    assert sent == [] or counted_as_rejected == 0, (
        "os 422 vieram de 'preco' ausente, não do valor proibido"
    )


def _with_infrastructure_operation(path: str) -> NegativeRig:
    from harness_dast.domain.api_model import ApiSpec, Operation, Parameter
    from harness_dast.domain.api_schema import Schema

    data = catalog_profile_data()
    data["probe"] = {"health_path": "/api/saude", "setup_path": "/api/preparar"}
    data["scope"]["allow"][0]["paths"] = ["/api/**"]
    rig = NegativeRig(Catalog(), profile_data=data)
    infra = Operation(
        operation_id="infra",
        method="get",
        path=path,
        parameters=(
            Parameter(
                name="n",
                location="query",
                value_schema=Schema(type="integer", minimum=1, maximum=5),
            ),
        ),
    )
    rig.spec = ApiSpec(
        title=rig.spec.title,
        version=rig.spec.version,
        servers=rig.spec.servers,
        operations=(*rig.spec.operations, infra),
    )
    return rig


@pytest.mark.parametrize("path", ["/api/preparar", "/api/saude"])
def test_the_infrastructure_paths_of_the_profile_are_not_replayed_with_forbidden_values(
    path: str,
) -> None:
    rig = _with_infrastructure_operation(path)
    infra = exchange("infra", "GET", path, f"{path}?n=2")

    rig.run(infra)

    assert rig.sent() == []


class Engaged:
    def engaged(self) -> bool:
        return True


def test_a_kill_switch_already_engaged_sends_nothing_even_with_writes_authorized() -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    result = rig.run(LIST, CREATE, UPDATE, ADJUST, kill_switch=Engaged())

    assert rig.sent() == []
    assert result.requests_sent == 0
    assert result.status != "completed"
    assert result.findings == ()


@pytest.mark.parametrize("method", ["delete", "Delete", "DELETE"])
def test_a_delete_exchange_in_any_case_is_never_sent(method: str) -> None:
    removal = REMOVE.model_copy(update={"method": method})
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    rig.run(LIST, removal)

    assert rig.catalog.deleted == 0
    assert [r.method.upper() for r in rig.target.requests if r.method.upper() == "DELETE"] == []


@pytest.mark.parametrize("method", ["post", "Post", "put", "patch"])
def test_a_lowercase_write_method_is_still_a_write_and_needs_the_letter(method: str) -> None:
    lowered = CREATE.model_copy(update={"method": method})
    rig = NegativeRig(Catalog(mode="lax"))

    result = rig.run(lowered)

    assert rig.sent() == []
    assert "writes_not_authorized" in reasons(result)


@pytest.mark.parametrize("method", ["OPTIONS", "HEAD", "TRACE", "CONNECT", "PROPFIND", ""])
def test_a_method_outside_get_post_put_patch_is_never_sent(method: str) -> None:
    odd = LIST.model_copy(update={"method": method})
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    rig.run(odd)

    assert rig.sent() == []


@pytest.mark.parametrize(
    "deny",
    ["/api/produtos/**", "/api/produtos/*", "/api/produtos/1", "/api/produtos"],
)
def test_deny_paths_stop_every_negative_request_for_the_denied_operations(deny: str) -> None:
    data = catalog_profile_data(allow_writes=True)
    data["scope"]["deny_paths"] = [deny]
    rig = NegativeRig(Catalog(mode="lax"), profile_data=data)

    result = rig.run(LIST, CREATE, UPDATE, ADJUST)

    denied_paths = {
        r.url.split("?")[0].removeprefix("https://api.hml.acme-teste.net.br") for r in rig.sent()
    }
    for path in denied_paths:
        assert not _matches(deny, path), f"{path} saiu apesar de deny_paths {deny}"
    assert result.findings == () or all(f.method != "" for f in result.findings)


def _matches(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3])
    if pattern.endswith("/*"):
        return path.startswith(pattern[:-1]) and "/" not in path[len(pattern) - 1 :]
    return path == pattern


def test_an_encoded_path_cannot_slip_past_a_denied_path() -> None:
    data = catalog_profile_data(allow_writes=True)
    data["scope"]["deny_paths"] = ["/api/produtos/1"]
    rig = NegativeRig(Catalog(mode="lax"), profile_data=data)
    sneaky = UPDATE.model_copy(update={"target": "/api/produtos/%31"})

    rig.run(sneaky)

    assert rig.sent("PUT") == []


def test_a_target_with_dot_segments_cannot_leave_the_allowed_prefix() -> None:
    data = catalog_profile_data(allow_writes=True)
    data["scope"]["deny_paths"] = ["/api/admin/**"]
    rig = NegativeRig(Catalog(mode="lax"), profile_data=data)
    sneaky = UPDATE.model_copy(update={"target": "/api/produtos/../admin/x"})

    rig.run(sneaky)

    assert all("admin" not in request.url for request in rig.sent())


def test_the_flags_only_narrow_and_a_hostile_value_never_widens() -> None:
    rig = NegativeRig(Catalog(mode="validate"), max_requests=3)
    probe = rig.seed(LIST)
    for asked in (4, 1_000_000, 0, -1, 2**63):
        with pytest.raises(ConfigError):
            rig.negative().execute(
                NegativeRequest(product="agenda", run_id=probe.run_id, max_requests=asked)
            )

    assert rig.sent() == []


def test_only_with_an_operation_that_needs_writes_still_needs_the_letter() -> None:
    rig = NegativeRig(Catalog(mode="lax"))
    probe = rig.seed(CREATE, LIST)

    result = rig.negative().execute(
        NegativeRequest(product="agenda", run_id=probe.run_id, only=("criarProduto",))
    )

    assert rig.sent() == []
    assert "writes_not_authorized" in reasons(result)


def test_only_with_a_blank_or_hostile_name_is_an_error_not_everything() -> None:
    rig = NegativeRig(Catalog(mode="lax"))
    probe = rig.seed(LIST)

    for name in ("", " ", "*", "../x", "listarProdutos ", "LISTARPRODUTOS", "a" * 10_000):
        with pytest.raises(ConfigError):
            rig.negative().execute(
                NegativeRequest(product="agenda", run_id=probe.run_id, only=(name,))
            )

    assert rig.sent() == []


def test_a_run_id_with_path_tricks_is_refused() -> None:
    rig = NegativeRig(Catalog())
    rig.seed(LIST)

    for run_id in ("../x", "", "a/b", "..\\x", "x" * 500, "2026-11-13T05-15-32Z-vampi-ab12/../.."):
        with pytest.raises(ConfigError):
            rig.negative().execute(NegativeRequest(product="agenda", run_id=run_id))


def test_a_probe_of_another_product_is_refused_before_any_request() -> None:
    rig = NegativeRig(Catalog())
    probe = rig.seed(LIST)
    rig.store.exchanges[probe.run_id] = rig.store.exchanges[probe.run_id].model_copy(
        update={"product": "outro"}
    )

    with pytest.raises(ConfigError):
        rig.negative().execute(NegativeRequest(product="agenda", run_id=probe.run_id))

    assert rig.sent() == []


def test_posts_creating_resources_stop_at_two_even_when_other_operations_continue() -> None:
    other = CREATE.model_copy(update={"operation_id": "criarProduto"})
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True, max_requests=200)

    result = rig.run(other, other, other)

    assert len(rig.sent("POST")) <= 2 * 3
    assert result.created_resources == len(rig.sent("POST"))


def test_the_total_budget_is_never_exceeded_with_writes_and_restores() -> None:
    for budget in (1, 2, 3, 5, 8):
        rig = NegativeRig(Catalog(mode="lax"), allow_writes=True, max_requests=budget)

        result = rig.run(LIST, CREATE, UPDATE, ADJUST)

        assert len(rig.sent()) <= budget
        assert result.requests_sent <= budget


def test_nothing_sent_reaches_artifacts_with_unicode_and_controls_in_the_baseline() -> None:
    baseline = exchange(
        "atualizarProduto",
        "PUT",
        f"{PRODUCTS}/{{id}}",
        f"{PRODUCTS}/1",
        body={"nome": "Café‮\x07\u0000ñ", "preco": 5, "status": "ativo"},
    )
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    result = rig.run(LIST, baseline)

    text = result.model_dump_json() + rig.artifacts.serialized()
    for marker in SENT_MARKERS:
        assert marker not in text
    assert "Café" not in result.model_dump_json()


def test_the_negative_json_round_trips_and_has_no_request_value() -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    result = rig.run(LIST, CREATE, UPDATE)

    dumped = json.loads(result.model_dump_json())
    flat = json.dumps(dumped)
    assert "Authorization" not in flat
    assert "Bearer" not in flat
    assert "tok-" not in flat
    assert type(result).model_validate(dumped) == result

"""Hipóteses de inspeção são limitadas e não alteram o perfil."""

from pathlib import Path

import pytest

from harness_dast.adapters.openapi import load_spec
from harness_dast.domain.api_model import Operation, Parameter, SuccessResponse
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.probe_plan import PlannedOperation
from harness_dast.domain.spec_hints import MAX_HINTS, suggest_spec_hints
from tests.fakes.rig import agenda_profile, profile_data


def plan(*ops: Operation) -> tuple[PlannedOperation, ...]:
    return tuple(
        PlannedOperation(
            operation_id=o.operation_id, method=o.method.upper(), path=o.path, decision="send"
        )
        for o in ops
    )


def test_clinica_document_list_suggests_first_filename_for_download() -> None:
    spec = load_spec(Path(__file__).parents[3] / "lab/pilot/openapi.json")
    ops = tuple(
        op for op in spec.operations if op.operation_id in {"listarDocumentos", "baixarDocumento"}
    )
    hints = suggest_spec_hints(agenda_profile(), ops, plan(*ops))
    assert any(
        (h.producer, h.field, h.consumer, h.parameter)
        == ("listarDocumentos", "0", "baixarDocumento", "arquivo")
        for h in hints
    )


def test_collection_object_field_matches_required_parameter() -> None:
    source = Operation(
        operation_id="listar",
        method="get",
        path="/api/items",
        success_responses=(
            SuccessResponse(
                status="200",
                body_schema=Schema(
                    type="array",
                    items=Schema(type="object", properties={"codigo": Schema(type="string")}),
                ),
            ),
        ),
    )
    target = Operation(
        operation_id="buscar",
        method="get",
        path="/api/items/{codigo}",
        parameters=(
            Parameter(
                name="codigo", location="path", required=True, value_schema=Schema(type="string")
            ),
        ),
    )
    hints = suggest_spec_hints(agenda_profile(), (source, target), plan(source, target))
    assert any(h.field == "0.codigo" and h.consumer == "buscar" for h in hints)


def test_denied_or_out_of_scope_operations_never_appear_in_hints() -> None:
    source = Operation(
        operation_id="listar",
        method="get",
        path="/api/items",
        success_responses=(
            SuccessResponse(
                status="200",
                body_schema=Schema(
                    type="array",
                    items=Schema(type="object", properties={"codigo": Schema(type="string")}),
                ),
            ),
        ),
    )
    target = Operation(
        operation_id="buscar",
        method="get",
        path="/api/items/{codigo}",
        parameters=(
            Parameter(
                name="codigo", location="path", required=True, value_schema=Schema(type="string")
            ),
        ),
    )
    denied = PlannedOperation(
        operation_id="listar", method="GET", path=source.path, decision="skipped_denied"
    )
    assert not suggest_spec_hints(agenda_profile(), (source, target), (denied, *plan(target)))


def test_peer_suggestion_describes_single_operation_limit() -> None:
    data = profile_data()
    data["auth"]["accounts"].append(
        {
            "alias": "user_b",
            "role": data["auth"]["accounts"][0]["role"],
            "username": {"secret_ref": "env:USER_B_USERNAME"},
            "password": {"secret_ref": "env:USER_B_PASSWORD"},
        }
    )
    from harness_dast.domain.profile import ProductProfile

    profile = ProductProfile.from_data(data)
    before = profile.model_dump()
    op = Operation(operation_id="ler", method="get", path="/api/items/{id}")
    hint = suggest_spec_hints(profile, (op,), plan(op))[0]
    assert hint.kind == "peer_account"
    assert hint.operations == ("ler",)
    assert "uma conta por operação" in hint.message
    assert profile.model_dump() == before


def test_output_has_a_fixed_hint_limit() -> None:
    source = Operation(
        operation_id="listar",
        method="get",
        path="/api/items",
        success_responses=(
            SuccessResponse(
                status="200",
                body_schema=Schema(
                    type="array",
                    items=Schema(type="object", properties={"codigo": Schema(type="string")}),
                ),
            ),
        ),
    )
    targets = tuple(
        Operation(
            operation_id=f"ler{i}",
            method="get",
            path=f"/api/items/{i}",
            parameters=(
                Parameter(
                    name="codigo",
                    location="query",
                    required=True,
                    value_schema=Schema(type="string"),
                ),
            ),
        )
        for i in range(80)
    )
    ops = (source, *targets)
    assert len(suggest_spec_hints(agenda_profile(), ops, plan(*ops))) <= MAX_HINTS


def test_uuid_format_can_match_different_names_in_same_collection() -> None:
    source = Operation(
        operation_id="listar",
        method="get",
        path="/api/items",
        success_responses=(
            SuccessResponse(
                status="200",
                body_schema=Schema(
                    type="array",
                    items=Schema(
                        type="object", properties={"chave": Schema(type="string", format="uuid")}
                    ),
                ),
            ),
        ),
    )
    target = Operation(
        operation_id="buscar",
        method="get",
        path="/api/items/{id}",
        parameters=(
            Parameter(
                name="id",
                location="path",
                required=True,
                value_schema=Schema(type="string", format="uuid"),
            ),
        ),
    )
    hints = suggest_spec_hints(agenda_profile(), (source, target), plan(source, target))
    assert any(h.field == "0.chave" and h.parameter == "id" for h in hints)


@pytest.mark.parametrize(
    ("schema", "suggested"),
    [
        (Schema(type="string", format="date"), False),
        (Schema(type="string", format="uuid"), True),
        (Schema(type="string"), True),
        (Schema(type="integer"), False),
    ],
)
def test_matching_names_require_compatible_types_and_formats(
    schema: Schema, suggested: bool
) -> None:
    source = Operation(
        operation_id="listar",
        method="get",
        path="/api/items",
        success_responses=(
            SuccessResponse(
                status="200",
                body_schema=Schema(
                    type="array",
                    items=Schema(
                        type="object", properties={"id": Schema(type="string", format="uuid")}
                    ),
                ),
            ),
        ),
    )
    target = Operation(
        operation_id="buscar",
        method="get",
        path="/api/items/{id}",
        parameters=(Parameter(name="id", location="path", required=True, value_schema=schema),),
    )
    hints = suggest_spec_hints(agenda_profile(), (source, target), plan(source, target))
    assert bool(hints) is suggested


def test_no_peer_hint_when_two_accounts_already_cover_distinct_object_reads() -> None:
    data = profile_data()
    data["auth"]["accounts"].append(
        {
            "alias": "user_b",
            "role": data["auth"]["accounts"][0]["role"],
            "username": {"secret_ref": "env:USER_B_USERNAME"},
            "password": {"secret_ref": "env:USER_B_PASSWORD"},
        }
    )
    data["auth"]["account_map"] = [{"account": "user_b", "operations": ["ler_b"]}]
    from harness_dast.domain.profile import ProductProfile

    profile = ProductProfile.from_data(data)
    a = Operation(operation_id="ler_a", method="get", path="/api/a/{id}")
    b = Operation(operation_id="ler_b", method="get", path="/api/b/{id}")
    assert not suggest_spec_hints(profile, (a, b), plan(a, b))


def test_untrusted_field_name_cannot_inject_new_lines_in_hint_message() -> None:
    field = "codigo\nalerta"
    source = Operation(
        operation_id="listar",
        method="get",
        path="/api/items",
        success_responses=(
            SuccessResponse(
                status="200",
                body_schema=Schema(
                    type="array",
                    items=Schema(type="object", properties={field: Schema(type="string")}),
                ),
            ),
        ),
    )
    target = Operation(
        operation_id="buscar",
        method="get",
        path="/api/items/{id}",
        parameters=(
            Parameter(
                name=field, location="query", required=True, value_schema=Schema(type="string")
            ),
        ),
    )
    hints = suggest_spec_hints(agenda_profile(), (source, target), plan(source, target))
    assert hints
    assert all("\n" not in hint.message for hint in hints)
    assert "codigo?alerta" in hints[0].message


def test_peer_hint_ignores_shared_role_and_suggests_unshared_pair() -> None:
    from harness_dast.domain.profile import ProductProfile

    data = profile_data()
    data["auth"]["accounts"] = [
        {
            "alias": alias,
            "role": role,
            "username": {"secret_ref": f"env:{alias}_USER"},
            "password": {"secret_ref": f"env:{alias}_PASS"},
        }
        for alias, role in (
            ("medico_a", "medico"),
            ("medico_b", "medico"),
            ("paciente_a", "paciente"),
            ("paciente_b", "paciente"),
        )
    ]
    data["auth"]["account_map"] = [
        {"account": "medico_a", "operations": ["ler_medico"]},
        {"account": "paciente_a", "operations": ["ler_paciente_a", "ler_paciente_b"]},
    ]
    data["authz"] = {"shared_roles": ["medico"]}
    profile = ProductProfile.from_data(data)
    ops = tuple(
        Operation(operation_id=name, method="get", path=f"/api/{name}/{{id}}")
        for name in ("ler_medico", "ler_paciente_a", "ler_paciente_b")
    )

    hints = suggest_spec_hints(profile, ops, plan(*ops))

    peers = [h for h in hints if h.kind == "peer_account"]
    assert [h.role for h in peers] == ["paciente"]
    assert peers[0].accounts == ("paciente_a", "paciente_b")
    assert "não compartilhado" in peers[0].message

"""O `authz` não repete um envio de arquivo: `unsupported_body` (ADR 0052)."""

from harness_dast.domain.authz.config import AuthzConfig
from harness_dast.domain.authz.matrix import AccessRule
from harness_dast.domain.authz.matrix_plan import plan_access_matrix
from harness_dast.domain.authz.plan import plan_horizontal, plan_vertical
from harness_dast.domain.authz.plan_mass import plan_mass_assignment
from harness_dast.domain.authz.plan_write import plan_horizontal_write
from harness_dast.domain.multipart_encoding import MultipartPart, MultipartSummary
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.rig import operation

ROLES = {"a1": "paciente", "a2": "paciente", "boss": "admin"}
ORDER = ("paciente", "admin")
SUMMARY = MultipartSummary(
    parts=(
        MultipartPart(
            name="arquivo", kind="file", filename="f.txt", content_type="text/plain", size=15
        ),
    ),
    total_bytes=15,
)


def upload(
    method: str = "POST", account: str = "boss", operation_id: str = "enviar"
) -> ExchangeRecord:
    return ExchangeRecord(
        operation_id=operation_id,
        method=method,
        path="/api/docs",
        target="/api/docs",
        account=account,
        status=201,
        content_type="multipart/form-data",
        multipart=SUMMARY,
    )


def test_vertical_marks_an_upload_as_unsupported_body_and_sends_nothing() -> None:
    plan = plan_vertical(
        [upload()],
        ROLES,
        ORDER,
        lambda item: "boss",
        frozenset({"GET", "POST"}),
        frozenset(),
    )

    assert plan.tasks == ()
    assert [(n.check, n.reason, n.operation_id) for n in plan.not_tested] == [
        ("vertical", "unsupported_body", "enviar")
    ]


def test_the_matrix_marks_an_upload_cell_as_unsupported_body() -> None:
    rule = AccessRule(operation="enviar", allow=("admin",), deny=("paciente",))

    result = plan_access_matrix(
        [rule],
        [upload()],
        ROLES,
        ORDER,
        {"enviar": operation("enviar", "post", "/api/docs")},
        allow_writes=True,
    )

    assert result.sends == ()
    assert [(n.reason, n.check) for n in result.notes] == [("unsupported_body", "access_matrix")]


def test_horizontal_and_write_checks_never_pick_an_upload() -> None:
    assert plan_horizontal([upload()], ROLES, frozenset()).tasks == ()
    write = plan_horizontal_write([upload("PUT", "a1")], ROLES, frozenset())
    assert write.tasks == ()
    assert [n.reason for n in write.not_tested] == ["no_json_body"]


def test_mass_assignment_never_picks_an_upload() -> None:
    config = AuthzConfig(mass_assignment_methods=("POST",))

    plan = plan_mass_assignment([upload()], frozenset(), config)

    assert plan.tasks == ()
    assert [n.reason for n in plan.not_tested] == ["no_json_body"]

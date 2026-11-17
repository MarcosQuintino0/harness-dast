"""QA independente da V1.4: nenhuma escrita sem `allow_writes`, nenhum `DELETE` nunca.

Ataca o `authz` com pedidos gravados hostis (`exchanges.json` com `DELETE`, `POST`, `PUT`),
tabela `access_matrix` apontando para escritas, `vertical_methods` com escrita e candidatos
derivados, e confere o que de fato chegou ao alvo falso.
"""

from typing import Any, cast

import pytest

from harness_dast.application.authz.service import AuthzRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.authz.config import CHECK_ORDER
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.profile import ProductProfile
from tests.fakes.authz.rig import AuthzRig, clinic_profile_data
from tests.fakes.authz.write_rig import (
    PATCH_NOTE,
    PATIENT,
    PUT_NOTE,
    QUERY_LIST,
    READ_NOTE,
    Notes,
    authz_sent,
    exchange,
    notes_spec,
    run_checks,
    seed,
)
from tests.fakes.rig import INT, STR, operation, parameter

READS = {"GET", "HEAD"}


def _spec() -> ApiSpec:
    base = notes_spec()
    body = {"titulo": STR, "ordem": INT}
    extra = (
        operation("apagarNota", "delete", "/api/notas/{id}", parameters=(parameter("id"),)),
        operation("criarNota", "post", "/api/notas", body=body, produces={"id": INT}),
    )
    return ApiSpec(
        title=base.title,
        version=base.version,
        servers=base.servers,
        operations=(*base.operations, *extra),
    )


def notes_rig(
    clinic: Notes, *, allow_writes: bool = True, methods: list[str] | None = None, **authz: Any
) -> AuthzRig:
    data = clinic_profile_data(allow_writes=allow_writes, **authz)
    if methods is not None:
        data["scope"]["allow"][0]["methods"] = methods
    return AuthzRig(clinic, profile=ProductProfile.from_data(data), spec=_spec())


DELETE_NOTE = exchange("apagarNota", "DELETE", "/api/notas/{id}", "/api/notas/1")
POST_NOTE = exchange(
    "criarNota", "POST", "/api/notas", "/api/notas", body={"titulo": "x", "ordem": 1}
)
HOSTILE = (READ_NOTE, QUERY_LIST, PATIENT, PUT_NOTE, PATCH_NOTE, DELETE_NOTE, POST_NOTE)

MATRIX = [
    {"operation": "salvarNota", "allow": ["paciente"], "deny": ["admin"]},
    {"operation": "ajustarNota", "allow": ["admin"], "deny": ["paciente"]},
    {"operation": "apagarNota", "allow": [], "deny": ["admin", "paciente"]},
    {"operation": "criarNota", "allow": [], "deny": ["admin", "paciente"]},
    {"operation": "lerNota", "allow": [], "deny": ["admin"]},
]


def _run_all(rig: Any, exchanges: tuple[ExchangeRecord, ...] = HOSTILE) -> None:
    probe = seed(rig, *exchanges)
    rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id, checks=CHECK_ORDER))


def _probe_count(rig: Any) -> int:
    return len([r for r in rig.target.requests if not r.operation_id.startswith("authz:")])


@pytest.mark.parametrize("with_matrix", [False, True])
def test_authz_sends_no_write_when_allow_writes_is_off_and_exchanges_are_hostile(
    with_matrix: bool,
) -> None:
    extra: dict[str, Any] = {"vertical_methods": ["GET", "HEAD", "POST", "PUT", "PATCH"]}
    if with_matrix:
        extra["access_matrix"] = MATRIX
    rig = notes_rig(Notes(write="vulnerable"), allow_writes=False, **extra)

    _run_all(rig)

    methods = {r.method for r in authz_sent(rig)}
    assert methods <= READS, methods


@pytest.mark.parametrize("allow_writes", [False, True])
def test_authz_never_sends_delete_when_exchanges_hold_a_delete(allow_writes: bool) -> None:
    rig = notes_rig(
        Notes(write="vulnerable"),
        allow_writes=allow_writes,
        vertical_methods=["GET", "HEAD", "POST", "PUT", "PATCH"],
        access_matrix=MATRIX,
        id_parameters=["pacienteId"],
    )

    _run_all(rig)

    assert [r for r in rig.target.requests if r.method == "DELETE"] == []


def test_dry_run_sends_nothing_when_writes_are_allowed_and_exchanges_are_hostile() -> None:
    rig = notes_rig(Notes(write="vulnerable"), access_matrix=MATRIX)

    run_checks(rig, HOSTILE, *CHECK_ORDER, dry_run=True)

    assert authz_sent(rig) == []


def test_single_check_request_respects_allow_writes_when_matrix_names_writes() -> None:
    rig = notes_rig(Notes(write="vulnerable"), allow_writes=False, access_matrix=MATRIX)

    run_checks(rig, HOSTILE, "access_matrix")

    assert {r.method for r in authz_sent(rig)} <= READS


def test_put_and_patch_stay_out_when_scope_methods_exclude_them() -> None:
    rig = notes_rig(Notes(write="vulnerable"), methods=["GET", "POST"], access_matrix=MATRIX)

    _run_all(rig)

    assert {r.method for r in rig.target.requests} <= {"GET", "POST"}
    assert cast(Notes, rig.clinic).notes[1]["titulo"] == "Original"


@pytest.mark.parametrize("jwt", [False, True])
def test_artifacts_hold_no_token_in_any_form_when_all_checks_run(jwt: bool) -> None:
    from tests.fakes.authz.rig import ROLES, jwt_of, token_of

    rig = notes_rig(
        Notes(write="vulnerable", jwt=jwt, excess=True, bola=True, bfla=True, mass=True),
        access_matrix=MATRIX,
    )

    _run_all(rig)

    dumped = rig.store.serialized() + rig.artifacts.serialized()
    for alias in ROLES:
        token = jwt_of(alias) if jwt else token_of(alias)
        assert token not in dumped
        for piece in token.split("."):
            if len(piece) > 12:
                assert piece not in dumped
    for secret in ("senha-ad-secreta", "$2b$10$SEGREDO", "nota interna que nunca"):
        assert secret not in dumped

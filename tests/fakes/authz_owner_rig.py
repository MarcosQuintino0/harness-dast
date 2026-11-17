"""API em memória com coleções por conta e roteamento de alcance compartilhado."""

import json
from typing import Any

from harness_dast.domain.api_model import ApiSpec, SuccessResponse
from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.errors import HarnessError
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.profile import ProductProfile
from tests.fakes.authz_rig import AuthzRig, Clinic, clinic_profile_data, clinic_spec
from tests.fakes.probe_ports import FakeTarget, reply
from tests.fakes.rig import INT, STR, operation, parameter


class OwnerApi:
    """Falso com comportamento e falhas de identidade/resposta configuráveis."""

    def __init__(self, **changes: Any) -> None:
        self.clinic = Clinic()
        self.bola = True
        self.own: JsonValue | bytes = [{"id": 11}, {"id": 12}, {"id": 13}]
        self.peer: JsonValue | bytes = [{"id": 22}]
        self.collection_status = 200
        self.base_status = 200
        self.replay_status = 200
        self.base_identity: JsonValue = None
        self.replay_identity: JsonValue = None
        self.different = False
        for name, value in changes.items():
            setattr(self, name, value)

    def __call__(self, request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
        path = request.url.split(".br", 1)[-1].split("?", 1)[0]
        if not path.startswith("/api/records"):
            return self.clinic(request, jar)
        account = request.account
        if path == "/api/records":
            values = self.own if account != "pac_b" else self.peer
            if isinstance(values, bytes):
                return HttpResponse(status=self.collection_status, body=values)
            return reply(self.collection_status, values)
        value = int(path.rsplit("/", 1)[-1])
        if account == "pac_a":
            return reply(self.base_status, {"id": self.base_identity or value, "name": "record"})
        if account == "pac_b":
            if not self.bola:
                return reply(403, {})
            return reply(
                self.replay_status,
                {
                    "id": self.replay_identity or value,
                    "name": "other" if self.different else "record",
                },
            )
        return reply(200, {"id": value, "name": "record"})


def owner_spec(*, collection: bool = True) -> ApiSpec:
    item = operation(
        "getRecord",
        "get",
        "/api/records/{id}",
        parameters=(parameter("id"),),
        produces={"id": INT, "name": STR},
    )
    listing = operation("listRecords", "get", "/api/records").model_copy(
        update={
            "success_responses": (
                SuccessResponse(
                    status="200",
                    body_schema=Schema(
                        type="array", items=Schema(type="object", properties={"id": INT})
                    ),
                ),
            )
        }
    )
    return clinic_spec().model_copy(
        update={
            "operations": (*clinic_spec().operations, item, *((listing,) if collection else ()))
        }
    )


def owner_rig(
    api: OwnerApi | None = None, *, collection: bool = True, deny: tuple[str, ...] = ()
) -> AuthzRig:
    data = clinic_profile_data(shared_roles=["admin"])
    data["auth"]["account_map"].append(
        {"account": "adm", "operations": ["getRecord", *(["listRecords"] if collection else [])]}
    )
    data["scope"]["deny_paths"].extend(deny)
    rig = AuthzRig(profile=ProductProfile.from_data(data), spec=owner_spec(collection=collection))
    rig.target = FakeTarget(api or OwnerApi())
    return rig


def add_creation(rig: AuthzRig, run_id: str, *, identity: object = 11) -> None:
    """Criação já observada pela conta dona, sem guardar resposta do servidor."""
    from harness_dast.domain.probe_exchange import ExchangeRecord

    log = rig.store.exchanges[run_id]
    created = ExchangeRecord(
        operation_id="createRecord",
        method="POST",
        path="/api/records",
        target="/api/records",
        account="pac_a",
        status=200,
        content_type="application/json",
        body=json.dumps({"id": identity}),
    )
    rig.store.exchanges[run_id] = log.model_copy(update={"exchanges": (*log.exchanges, created)})

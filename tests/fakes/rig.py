"""Montagem de cenários completos com falsos: perfil, OpenAPI, alvo, ZAP, armazém e relógio."""

import copy
from collections.abc import Callable
from typing import Any

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.application.account_session import TokenCache
from harness_dast.application.inspect_spec import InspectSpec
from harness_dast.application.preflight import Preflight
from harness_dast.application.probe import Probe
from harness_dast.domain.api_model import (
    ApiSpec,
    MediaBody,
    Operation,
    Parameter,
    RequestBody,
    SecurityRequirement,
    SuccessResponse,
)
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import HarnessError
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.profile import ProductProfile
from harness_dast.observability.logging import SecretRegistry
from tests.fakes.probe_ports import (
    DictSecretProvider,
    FakeTarget,
    FakeZap,
    Handler,
    InMemoryDocuments,
    InMemoryRunStore,
    InMemorySpecs,
    reply,
)
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.runtime import FixedEntropy, ManualClock

LOGIN = "alice"
PASSWORD = "senha-secreta-xyz"  # noqa: S105 - sentinela ou nome de campo, não um segredo
TOKEN = "tok-SEGREDO-1234567890"  # noqa: S105 - sentinela ou nome de campo, não um segredo
ENV = {"ACME_USER_A_LOGIN": LOGIN, "ACME_USER_A_SENHA": PASSWORD}

STR = Schema(type="string")
INT = Schema(type="integer")


def parameter(name: str, schema: Schema = INT, location: str = "path") -> Parameter:
    return Parameter(name=name, location=location, required=True, value_schema=schema)  # type: ignore[arg-type]


def operation(
    operation_id: str,
    method: str,
    path: str,
    *,
    body: dict[str, Schema] | None = None,
    required: tuple[str, ...] = (),
    parameters: tuple[Parameter, ...] = (),
    produces: dict[str, Schema] | None = None,
    secured: bool = True,
) -> Operation:
    request_body = None
    if body is not None:
        schema = Schema(type="object", properties=body, required=required)
        request_body = RequestBody(
            required=True, media=(MediaBody(media_type="application/json", body_schema=schema),)
        )
    responses: tuple[SuccessResponse, ...] = ()
    if produces is not None:
        responses = (
            SuccessResponse(status="200", body_schema=Schema(type="object", properties=produces)),
        )
    return Operation(
        operation_id=operation_id,
        method=method,  # type: ignore[arg-type]
        path=path,
        parameters=parameters,
        request_body=request_body,
        success_responses=responses,
        security=(SecurityRequirement(schemes=("bearer",)),) if secured else (),
    )


def agenda_spec() -> ApiSpec:
    return ApiSpec(
        title="Agenda",
        version="1",
        servers=("https://api.hml.acme-teste.net.br",),
        operations=(
            operation(
                "login",
                "post",
                "/api/auth/login",
                body={"username": STR, "password": STR},
                required=("username", "password"),
                secured=False,
            ),
            operation("listar", "get", "/api/pacientes"),
            operation(
                "criar",
                "post",
                "/api/pacientes",
                body={"nome": STR},
                required=("nome",),
                produces={"id": INT},
            ),
            operation(
                "buscar",
                "get",
                "/api/pacientes/{pacienteId}",
                parameters=(parameter("pacienteId"),),
            ),
            operation(
                "atualizar",
                "put",
                "/api/pacientes/{pacienteId}",
                body={"nome": STR},
                required=("nome",),
                parameters=(parameter("pacienteId"),),
            ),
            operation(
                "remover",
                "delete",
                "/api/pacientes/{pacienteId}",
                parameters=(parameter("pacienteId"),),
            ),
            operation("admin", "get", "/api/admin/usuarios"),
            operation("externo", "get", "/outra/coisa"),
        ),
    )


def agenda_flows() -> FlowSpec:
    consumers = [
        {"operation": name, "param": "pacienteId"} for name in ("buscar", "atualizar", "remover")
    ]
    return FlowSpec.from_data(
        {
            "schema_version": 1,
            "bindings": [
                {"produces": {"operation": "criar", "field": "id"}, "consumed_by": consumers}
            ],
        }
    )


def profile_data(**changes: Any) -> dict[str, Any]:
    """Perfil base (host público, `/api/**`, todos os métodos de escrita) com ajustes de topo."""
    data = valid_profile_data("agenda")
    data["scope"]["allow"][0]["methods"] = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    data["auth"]["token_response_field"] = "access_token"  # noqa: S105 - sentinela ou nome de campo, não um segredo
    data["probe"] = {"health_path": "/api/saude"}
    data.update(copy.deepcopy(changes))
    return data


def agenda_profile(**changes: Any) -> ProductProfile:
    return ProductProfile.from_data(profile_data(**changes))


def default_handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
    """Alvo bem-comportado: login devolve o token; o resto exige o token."""
    path = request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
    if request.method == "POST" and path == "api/auth/login":
        return reply(200, {"access_token": TOKEN})
    if dict(request.headers).get("Authorization") != f"Bearer {TOKEN}":
        return reply(401, {"detail": "no token"})
    if request.method == "POST" and path == "api/pacientes":
        return reply(201, {"id": 7})
    return reply(200, {"ok": True})


class Rig:
    """Um cenário pronto: use `probe()`, `preflight()` ou `inspect()`."""

    def __init__(
        self,
        *,
        profile: ProductProfile | None = None,
        spec: ApiSpec | None = None,
        rules: DataRules | None = None,
        flows: FlowSpec | None = None,
        handler: Handler = default_handler,
        env: dict[str, str] | None = None,
        documents: InMemoryDocuments | None = None,
    ) -> None:
        self.profile = profile or agenda_profile()
        self.spec = spec or agenda_spec()
        self.clock = ManualClock()
        self.zap = FakeZap()
        self.store = InMemoryRunStore()
        self.vault = SecretRegistry()
        self.target = FakeTarget(handler)
        self.entropy = FixedEntropy()
        self.documents = documents or InMemoryDocuments(rules, flows)
        self.profiles = InMemoryProfileRepository()
        self.profiles.add(self.profile, existing_files={"./openapi.json"})
        self.secrets = DictSecretProvider(ENV if env is None else env)

    def probe(self, token_cache: TokenCache | None = None) -> Probe:
        return Probe(
            profiles=self.profiles,
            specs=InMemorySpecs(self.spec),
            documents=self.documents,
            secrets=self.secrets,
            vault=self.vault,
            client=self.target,
            zap=self.zap,
            store=self.store,
            clock=self.clock,
            sleeper=self.clock,
            entropy=self.entropy,
            value_sources=GeneratorCatalogue,
            harness_version="0.0-test",
            token_cache=token_cache,
        )

    def preflight(self, token_cache: TokenCache | None = None) -> Preflight:
        return Preflight(
            profiles=self.profiles,
            secrets=self.secrets,
            vault=self.vault,
            client=self.target,
            zap=self.zap,
            store=self.store,
            clock=self.clock,
            sleeper=self.clock,
            entropy=self.entropy,
            harness_version="0.0-test",
            token_cache=token_cache,
        )

    def inspect(self) -> InspectSpec:
        return InspectSpec(
            profiles=self.profiles,
            specs=InMemorySpecs(self.spec),
            documents=self.documents,
            value_sources=GeneratorCatalogue,
            clock=self.clock,
        )


def route(
    table: dict[tuple[str, str], Callable[[HttpRequest], HttpResponse | HarnessError]],
) -> Handler:
    """Manipulador por tabela `(método, caminho sem barra inicial) -> função`; resto dá 404."""

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
        path = request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
        action = table.get((request.method, path))
        return action(request) if action is not None else reply(404, {"detail": "nao existe"})

    return handler

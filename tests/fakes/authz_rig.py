"""Alvo falso "clínica" com cada falha de autorização ligável, e o cenário do `authz`.

`Clinic` é um `Handler` com comportamento: guarda o estado de cada conta (papel e nome) e
responde como um alvo seguro ou com a falha ligada:

- `bola`: qualquer conta lê a consulta de qualquer outra (senão, só a conta dona, `pac_a`);
- `excess`: a lista de pacientes devolve `senhaHash` e `notasInternas`, fora do esquema;
- `mass`: `PUT /api/me` copia o campo `role` do corpo para `papel` (o nome muda de propósito);
- `bfla`: `GET /api/relatorios` e `POST /api/convenios` aceitam qualquer papel.

`AuthzRig` monta o perfil, o OpenAPI e o armazém em memória; `run_probe()` roda o `probe` de
verdade sobre o alvo falso e `authz()` devolve o caso de uso sobre o mesmo armazém.
"""

import json
from typing import Any

from harness_dast.application.authz import Authz
from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import HarnessError
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.profile import ProductProfile
from tests.fakes.probe_ports import reply
from tests.fakes.rig import INT, STR, Rig, operation, parameter, profile_data
from tests.fakes.scan_ports import InMemoryRunArtifacts

ENV = {
    "ACME_USER_A_LOGIN": "login-pa-xyz",
    "ACME_USER_A_SENHA": "senha-pa-secreta",
    "ACME_USER_B_LOGIN": "login-pb-xyz",
    "ACME_USER_B_SENHA": "senha-pb-secreta",
    "ACME_ADMIN_LOGIN": "login-ad-xyz",
    "ACME_ADMIN_SENHA": "senha-ad-secreta",
}
LOGINS = {"login-pa-xyz": "pac_a", "login-pb-xyz": "pac_b", "login-ad-xyz": "adm"}
ROLES = {"pac_a": "paciente", "pac_b": "paciente", "adm": "admin"}
HASH_VALUE = "$2b$10$SEGREDO-DE-HASH-QUE-NUNCA-PODE-VAZAR"
NOTES_VALUE = "nota interna que nunca pode ser gravada"


def token_of(alias: str) -> str:
    return f"tok-{alias}-1234567890"


class Clinic:
    """Alvo falso; cada falha é um interruptor."""

    def __init__(
        self,
        *,
        bola: bool = False,
        excess: bool = False,
        mass: bool = False,
        bfla: bool = False,
        reject_extra_fields: bool = False,
    ) -> None:
        self.bola = bola
        self.excess = excess
        self.mass = mass
        self.bfla = bfla
        self.reject_extra_fields = reject_extra_fields
        self.papel = dict(ROLES)
        self.nome = {alias: f"Nome {alias}" for alias in ROLES}
        self.counter = 0

    def __call__(self, request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
        path = request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
        if request.method == "POST" and path == "api/auth/login":
            alias = LOGINS.get(json.loads(request.body or b"{}").get("username", ""))
            return reply(200, {"access_token": token_of(alias)}) if alias else reply(401, {})
        alias = self._caller(request)
        if alias is None:
            return reply(401, {"code": "NAO_AUTENTICADO"})
        self.counter += 1
        return self._route(request, path, alias)

    @staticmethod
    def _caller(request: HttpRequest) -> str | None:
        header = dict(request.headers).get("Authorization", "")
        for alias in ROLES:
            if header == f"Bearer {token_of(alias)}":
                return alias
        return None

    def _route(self, request: HttpRequest, path: str, alias: str) -> HttpResponse:
        method = request.method
        if path == "api/me":
            return self._me(request, alias)
        if method == "GET" and path.startswith("api/consultas/"):
            if not self.bola and alias != "pac_a":
                return reply(403, {"code": "ACESSO_NEGADO"})
            return reply(
                200,
                {"id": path.rsplit("/", 1)[1], "descricao": "consulta", "requestId": self.counter},
            )
        if method == "GET" and path.startswith("api/catalogo/"):
            return reply(200, {"id": path.rsplit("/", 1)[1], "nome": "item publico"})
        if method == "GET" and path == "api/pacientes":
            return reply(200, {"items": [self._patient()]})
        admin_only = path in {"api/relatorios", "api/convenios"}
        if admin_only and not self.bfla and self.papel[alias] != "admin":
            return reply(403, {"code": "ACESSO_NEGADO"})
        if method == "GET" and path == "api/relatorios":
            return reply(200, {"total": 1})
        if method == "POST" and path == "api/convenios":
            return reply(201, {"id": 1})
        return reply(404, {"code": "NAO_ENCONTRADO"})

    def _patient(self) -> dict[str, Any]:
        item: dict[str, Any] = {"id": 1, "nome": "Paciente"}
        if self.excess:
            item.update({"senhaHash": HASH_VALUE, "notasInternas": NOTES_VALUE})
        return item

    def _me(self, request: HttpRequest, alias: str) -> HttpResponse:
        if request.method == "PUT":
            body = json.loads(request.body or b"{}")
            if self.reject_extra_fields and set(body) - {"nome"}:
                return reply(400, {"code": "CORPO_INVALIDO"})
            self.nome[alias] = str(body.get("nome", self.nome[alias]))
            if self.mass and "role" in body:
                self.papel[alias] = str(body["role"])
        return reply(200, {"id": 1, "nome": self.nome[alias], "papel": self.papel[alias]})


def clinic_spec() -> ApiSpec:
    me = {"id": INT, "nome": STR, "papel": STR}
    patients = {"items": Schema(type="array", items=Schema(type="object", properties=_resumo()))}
    return ApiSpec(
        title="Clinica",
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
            operation("obterPerfil", "get", "/api/me", produces=me),
            operation(
                "atualizarPerfil",
                "put",
                "/api/me",
                body={"nome": STR},
                required=("nome",),
                produces=me,
            ),
            operation(
                "buscarConsulta",
                "get",
                "/api/consultas/{id}",
                parameters=(parameter("id"),),
                produces={"id": STR, "descricao": STR, "requestId": INT},
            ),
            operation(
                "lerCatalogo",
                "get",
                "/api/catalogo/{id}",
                parameters=(parameter("id"),),
                produces={"id": STR, "nome": STR},
            ),
            operation("listarPacientes", "get", "/api/pacientes", produces=patients),
            operation("listarRelatorios", "get", "/api/relatorios", produces={"total": INT}),
            operation(
                "criarConvenio",
                "post",
                "/api/convenios",
                body={"nome": STR},
                required=("nome",),
                produces={"id": INT},
            ),
        ),
    )


def _resumo() -> dict[str, Schema]:
    return {"id": INT, "nome": STR}


def clinic_profile_data(**authz: Any) -> dict[str, Any]:
    data = profile_data()
    accounts = [
        ("pac_a", "paciente", "ACME_USER_A_LOGIN", "ACME_USER_A_SENHA"),
        ("pac_b", "paciente", "ACME_USER_B_LOGIN", "ACME_USER_B_SENHA"),
        ("adm", "admin", "ACME_ADMIN_LOGIN", "ACME_ADMIN_SENHA"),
    ]
    data["auth"]["accounts"] = [
        {
            "alias": alias,
            "role": role,
            "username": {"secret_ref": f"env:{user}"},
            "password": {"secret_ref": f"env:{password}"},
        }
        for alias, role, user, password in accounts
    ]
    data["auth"]["default_account"] = "adm"
    data["auth"]["account_map"] = [
        {
            "account": "pac_a",
            "operations": ["obterPerfil", "atualizarPerfil", "buscarConsulta", "lerCatalogo"],
        },
        {"account": "adm", "operations": ["listarRelatorios", "criarConvenio"]},
    ]
    data["authz"] = {
        "role_order": ["paciente", "admin"],
        "public_operations": ["lerCatalogo"],
        **authz,
    }
    return data


class AuthzRig(Rig):
    """`Rig` do `probe` com a clínica falsa, o armazém de artefatos e o `authz`."""

    def __init__(
        self,
        clinic: Clinic | None = None,
        *,
        profile: ProductProfile | None = None,
        authz: dict[str, Any] | None = None,
    ) -> None:
        self.clinic = clinic or Clinic()
        profile = profile or ProductProfile.from_data(clinic_profile_data(**(authz or {})))
        super().__init__(profile=profile, spec=clinic_spec(), handler=self.clinic, env=ENV)
        self.artifacts = InMemoryRunArtifacts(self.store)

    def run_probe(self) -> ProbeResult:
        return self.probe().execute(ProbeRequest(product="agenda"))

    def authz(self) -> Authz:
        return Authz(
            profiles=self.profiles,
            specs=self._specs(),
            secrets=self.secrets,
            vault=self.vault,
            client=self.target,
            store=self.store,
            artifacts=self.artifacts,
            clock=self.clock,
            sleeper=self.clock,
        )

    def _specs(self) -> Any:
        from tests.fakes.probe_ports import InMemorySpecs

        return InMemorySpecs(self.spec)

    def sent_by(self, alias: str) -> list[HttpRequest]:
        return [r for r in self.target.requests if r.account == alias]

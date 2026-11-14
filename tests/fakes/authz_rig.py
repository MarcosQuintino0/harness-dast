"""Alvo falso "clínica" com cada falha de autorização ligável, e o cenário do `authz`.

`Clinic` é um `Handler` com comportamento: guarda o estado de cada conta (papel e nome) e
responde como um alvo seguro ou com a falha ligada:

- `bola`: qualquer conta lê a consulta de qualquer outra (senão, só a conta dona, `pac_a`);
- `excess`: a lista de pacientes devolve `passwordHash` e `internalNotes`, fora do esquema;
- `mass`: `PUT /api/me` copia o campo `role` do corpo para `papel` (o nome muda de propósito);
- `bfla`: `GET /api/relatorios` e `POST /api/convenios` aceitam qualquer papel;
- `open_paths`: caminhos que respondem a quem não enviou credencial (como o "adm");
- `jwt`: o login devolve um JWT (HS256) em vez de texto opaco;
- `lax`: como o servidor confere o token: `strict` (igualdade), `ignore_signature` (lê o `sub`
  do JWT sem conferir assinatura nem `alg`) ou `any_token` (reconhece o apelido em qualquer parte
  do texto do token, até invertido);
- `open_different`: o caminho aberto devolve outro corpo a quem não se identificou;
- `unauth_status`: código devolvido a quem não se identificou (401 por padrão);
- `stores`: campos extras que `PUT /api/me` guarda e devolve (atribuição em massa derivada do
  OpenAPI: `nivelAcesso`, `saldo`);
- `creates`: campos extras que `POST /api/medicos` guarda e `GET /api/medicos/{id}` devolve;
  `location` (`path`, `absolute`, `other_host`, `traversal`, `none`) diz o que o POST devolve em
  `Location`, `post_echo` se o corpo do POST traz o recurso criado, `id_in_body` se traz o `id`,
  `conflict` faz o POST responder 409 e `readable` desliga o `GET /api/medicos/{id}`.

`AuthzRig` monta o perfil, o OpenAPI e o armazém em memória; `run_probe()` roda o `probe` de
verdade sobre o alvo falso e `authz()` devolve o caso de uso sobre o mesmo armazém.
"""

import base64
import json
from typing import Any

from harness_dast.application.authz import Authz
from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.api_model import ApiSpec, Operation
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


def _b64(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def jwt_of(alias: str) -> str:
    """JWT de teste: assinatura é texto fixo (nunca assinado de verdade)."""
    header = _b64({"alg": "HS256", "typ": "JWT"})
    payload = _b64({"sub": alias, "role": ROLES[alias], "exp": 4102444800})
    return f"{header}.{payload}.c2lnbmF0dXJlLWZpeGE"


def _jwt_subject(token: str) -> str | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        raw = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        sub = json.loads(raw).get("sub")
    except (ValueError, AttributeError):
        return None
    return sub if sub in ROLES else None


STORE_DEFAULTS: dict[str, Any] = {"nivelAcesso": "basico", "saldo": 10, "ativo": False}


def _store_defaults(names: tuple[str, ...]) -> dict[str, Any]:
    return {name: STORE_DEFAULTS[name] for name in names}


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
        empty_lists: bool = False,
        open_paths: frozenset[str] = frozenset(),
        jwt: bool = False,
        lax: str = "strict",
        open_different: bool = False,
        unauth_status: int = 401,
        stores: tuple[str, ...] = (),
        creates: tuple[str, ...] = (),
        location: str = "path",
        post_echo: bool = False,
        id_in_body: bool = True,
        conflict: bool = False,
        readable: bool = True,
    ) -> None:
        self.bola = bola
        self.excess = excess
        self.mass = mass
        self.bfla = bfla
        self.reject_extra_fields = reject_extra_fields
        self.empty_lists = empty_lists
        self.papel = dict(ROLES)
        self.nome = {alias: f"Nome {alias}" for alias in ROLES}
        self.counter = 0
        self.open_paths = open_paths
        self.jwt = jwt
        self.lax = lax
        self.open_different = open_different
        self.unauth_status = unauth_status
        self.logins = 0
        self.stores = stores
        self.creates = creates
        self.location = location
        self.post_echo = post_echo
        self.id_in_body = id_in_body
        self.conflict = conflict
        self.readable = readable
        self.extra = {alias: _store_defaults(stores) for alias in ROLES}
        self.medicos: dict[int, dict[str, Any]] = {}

    def issue(self, alias: str) -> str:
        return jwt_of(alias) if self.jwt else token_of(alias)

    def __call__(self, request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
        path = request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
        if request.method == "POST" and path == "api/auth/login":
            alias = LOGINS.get(json.loads(request.body or b"{}").get("username", ""))
            self.logins += 1
            return reply(200, {"access_token": self.issue(alias)}) if alias else reply(401, {})
        alias = self._caller(request)
        if alias is None and path in self.open_paths:
            if self.open_different:
                return reply(200, {"items": [], "anonimo": True})
            alias = "adm"
        if alias is None:
            return reply(self.unauth_status, {"code": "NAO_AUTENTICADO"})
        self.counter += 1
        return self._route(request, path, alias)

    def _caller(self, request: HttpRequest) -> str | None:
        header = dict(request.headers).get("Authorization", "")
        token = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
        for alias in ROLES:
            if token == self.issue(alias):
                return alias
        if self.lax == "ignore_signature":
            return _jwt_subject(token)
        if self.lax == "any_token":
            return next(
                (a for a in ROLES if a in token or a[::-1] in token),
                None,
            )
        return None

    def _route(self, request: HttpRequest, path: str, alias: str) -> HttpResponse:
        method = request.method
        if path == "api/me":
            return self._me(request, alias)
        if path.startswith("api/medicos"):
            return self._medicos(request, path)
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
            return reply(200, {"items": [] if self.empty_lists else [self._patient()]})
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
            item.update({"passwordHash": HASH_VALUE, "internalNotes": NOTES_VALUE})
        return item

    def _me(self, request: HttpRequest, alias: str) -> HttpResponse:
        if request.method == "PUT":
            body = json.loads(request.body or b"{}")
            if self.reject_extra_fields and set(body) - {"nome", "role"}:
                return reply(400, {"code": "CORPO_INVALIDO"})
            self.nome[alias] = str(body.get("nome", self.nome[alias]))
            if self.mass and "role" in body:
                self.papel[alias] = str(body["role"])
            for name in self.stores:
                if name in body:
                    self.extra[alias][name] = body[name]
        return reply(
            200,
            {"id": 1, "nome": self.nome[alias], "papel": self.papel[alias], **self.extra[alias]},
        )

    def _medicos(self, request: HttpRequest, path: str) -> HttpResponse:
        if request.method == "POST" and path == "api/medicos":
            if self.conflict:
                return reply(409, {"code": "CONFLITO"})
            body = json.loads(request.body or b"{}")
            number = len(self.medicos) + 1
            record: dict[str, Any] = {"id": number, "nome": str(body.get("nome", "x"))}
            record.update(_store_defaults(self.creates))
            record.update({name: body[name] for name in self.creates if name in body})
            self.medicos[number] = record
            sent: dict[str, Any] = dict(record) if self.post_echo else {}
            if self.id_in_body:
                sent["id"] = number
            return reply(201, sent or None, location=self._location(number))
        if request.method == "GET" and self.readable:
            number = int(path.rsplit("/", 1)[1]) if path.rsplit("/", 1)[1].isdigit() else 0
            return reply(200, self.medicos.get(number, {"id": number, "nome": "semente"}))
        return reply(404, {"code": "NAO_ENCONTRADO"})

    def _location(self, number: int) -> str | None:
        return {
            "path": f"/api/medicos/{number}",
            "absolute": f"https://api.hml.acme-teste.net.br/api/medicos/{number}",
            "other_host": f"https://outro.example.org/api/medicos/{number}",
            "traversal": "/api/medicos/../me",
            "none": None,
        }[self.location]


def clinic_spec(*, derived: bool = False) -> ApiSpec:
    """OpenAPI da clínica; `derived` acrescenta campos só de resposta e o cadastro de médicos."""
    me = {"id": INT, "nome": STR, "papel": STR}
    if derived:
        me = {**me, "nivelAcesso": STR, "saldo": INT}
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
                body={"nome": STR, "role": Schema(type="string", enum=("paciente", "admin"))},
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
            *_doctor_operations(derived=derived),
        ),
    )


def _doctor_operations(*, derived: bool) -> tuple[Operation, ...]:
    if not derived:
        return ()
    doctor = {"id": INT, "nome": STR, "nivelAcesso": STR, "ativo": Schema(type="boolean")}
    return (
        operation(
            "criarMedico",
            "post",
            "/api/medicos",
            body={"nome": STR},
            required=("nome",),
            produces=doctor,
        ),
        operation(
            "lerMedico",
            "get",
            "/api/medicos/{id}",
            parameters=(parameter("id"),),
            produces=doctor,
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
        # A clínica falsa liga a escrita (como uma carta que a autoriza); os testes de ADR 0038
        # a desligam com `allow_writes=False`.
        "allow_writes": True,
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
        spec: ApiSpec | None = None,
    ) -> None:
        self.clinic = clinic or Clinic()
        profile = profile or ProductProfile.from_data(clinic_profile_data(**(authz or {})))
        super().__init__(
            profile=profile, spec=spec or clinic_spec(), handler=self.clinic, env=dict(ENV)
        )
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

"""Alvo falso com recurso por dono, escrita vulnerável e leitura por conta (ADR 0042).

`Notes` estende a `Clinic` com:

- `GET/PUT/PATCH /api/notas/{id}`: a nota 1 é da conta `pac_a`. Com `write="vulnerable"` qualquer
  conta altera a nota; com `write="deny"` a outra conta recebe `deny_status` (403 por padrão);
  com `write="ignore"` a outra conta recebe 200 sem efeito. `write_status` força o código de
  resposta da escrita de outra conta (por exemplo 422) sem alterar nada. `owner_write_ignored`
  faz o `PUT` da própria dona responder 200 sem aplicar (a restauração não pega).
- `GET /api/consultas?pacienteId=2`: devolve as consultas do paciente 2 (da conta `pac_a`). Com
  `filter_open` qualquer conta recebe o mesmo corpo; senão a outra conta recebe 403.
- `GET /api/pacientes/{id}` devolve o paciente `id` a qualquer conta (para o `owned_hint`).

`seed()` roda o `probe` de verdade (para haver `probe.json`) e troca `exchanges.json` pelos pedidos
dados, para o teste controlar o que o `authz` repete.
"""

import json
from typing import Any

from harness_dast.application.authz.service import AuthzRequest
from harness_dast.domain.api_model import ApiSpec, Operation
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.probe_exchange import ExchangeLog, ExchangeRecord
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.profile import ProductProfile
from tests.fakes.authz.rig import AuthzRig, Clinic, clinic_profile_data, clinic_spec
from tests.fakes.probe_ports import reply
from tests.fakes.rig import INT, STR, operation, parameter

NOTE_BODY = {"titulo": "Original", "ordem": 3, "role": "visitante"}
ORIGINAL_TITLE = "Original"


class Notes(Clinic):
    """A clínica com notas por dono."""

    def __init__(
        self,
        *,
        write: str = "deny",
        deny_status: int = 403,
        write_status: int | None = None,
        owner_write_ignored: bool = False,
        filter_open: bool = False,
        vary_by_account: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.write = write
        self.deny_status = deny_status
        self.write_status = write_status
        self.owner_write_ignored = owner_write_ignored
        self.filter_open = filter_open
        self.vary_by_account = vary_by_account
        self.owner = {1: "pac_a"}
        self.notes: dict[int, dict[str, Any]] = {}
        self.reset()

    def reset(self) -> None:
        """Volta as notas ao estado inicial (o `probe` do cenário pode ter mexido nelas)."""
        self.notes = {1: {"id": 1, **NOTE_BODY}}

    def _route(self, request: HttpRequest, path: str, alias: str) -> HttpResponse:
        if path.startswith("api/notas/"):
            return self._note(request, path, alias)
        if request.method == "GET" and path == "api/consultas":
            return self._appointments(request, alias)
        if request.method == "GET" and path == "api/pacientes/busca":
            return reply(200, {"items": [{"id": 1, "nome": "Paciente"}]})
        if request.method == "GET" and path.startswith("api/pacientes/"):
            return reply(200, {"id": int(path.rsplit("/", 1)[1]), "nome": "Paciente"})
        return super()._route(request, path, alias)

    def _appointments(self, request: HttpRequest, alias: str) -> HttpResponse:
        wanted = request.url.partition("pacienteId=")[2].partition("&")[0]
        if alias != "pac_a" and not self.filter_open:
            return reply(403, {"code": "ACESSO_NEGADO"})
        item: dict[str, Any] = {"id": 9, "pacienteId": wanted}
        if self.vary_by_account:
            item["quem"] = alias
        return reply(200, {"items": [item]})

    def _note(self, request: HttpRequest, path: str, alias: str) -> HttpResponse:
        number = int(path.rsplit("/", 1)[1])
        note = self.notes.get(number)
        if note is None:
            return reply(404, {"code": "NAO_ENCONTRADO"})
        if request.method == "GET":
            return reply(200, dict(note))
        mine = self.owner[number] == alias
        if not mine and self.write == "deny":
            return reply(self.deny_status, {"code": "ACESSO_NEGADO"})
        if not mine and self.write_status is not None:
            return reply(self.write_status, {"code": "REJEITADO"})
        ignored = (not mine and self.write == "ignore") or (mine and self.owner_write_ignored)
        if not ignored:
            note.update(json.loads(request.body or b"{}"))
        return reply(200, dict(note))


def notes_spec() -> ApiSpec:
    """OpenAPI da clínica com as operações de nota, consulta por paciente e paciente."""
    base = clinic_spec()
    return ApiSpec(
        title=base.title,
        version=base.version,
        servers=base.servers,
        operations=(*base.operations, *_note_operations()),
    )


def _note_operations() -> tuple[Operation, ...]:
    produces = {"id": INT, "titulo": STR, "ordem": INT, "role": STR}
    body = {"titulo": STR, "ordem": INT, "role": STR}
    return (
        operation(
            "lerNota",
            "get",
            "/api/notas/{id}",
            parameters=(parameter("id"),),
            produces=produces,
        ),
        operation(
            "salvarNota",
            "put",
            "/api/notas/{id}",
            body=body,
            parameters=(parameter("id"),),
            produces=produces,
        ),
        operation(
            "ajustarNota",
            "patch",
            "/api/notas/{id}",
            body=body,
            parameters=(parameter("id"),),
            produces=produces,
        ),
        operation(
            "listarConsultasDoPaciente",
            "get",
            "/api/consultas",
            parameters=(parameter("pacienteId", INT, "query"), parameter("page", INT, "query")),
            produces={"items": STR},
        ),
        operation(
            "buscarPacientePorCpf",
            "get",
            "/api/pacientes/busca",
            parameters=(parameter("cpf", STR, "query"),),
            produces={"items": STR},
        ),
        operation(
            "lerPaciente",
            "get",
            "/api/pacientes/{id}",
            parameters=(parameter("id"),),
            produces={"id": INT, "nome": STR},
        ),
    )


def exchange(
    op: str,
    method: str,
    path: str,
    target: str,
    *,
    account: str = "pac_a",
    body: dict[str, Any] | None = None,
) -> ExchangeRecord:
    """Pedido provado, como o `probe` o gravaria."""
    return ExchangeRecord(
        operation_id=op,
        method=method,
        path=path,
        target=target,
        account=account,
        status=200,
        content_type="application/json" if body is not None else None,
        body=json.dumps(body) if body is not None else None,
    )


READ_NOTE = exchange("lerNota", "GET", "/api/notas/{id}", "/api/notas/1")
QUERY_LIST = exchange(
    "listarConsultasDoPaciente", "GET", "/api/consultas", "/api/consultas?pacienteId=2"
)
PATIENT = exchange("lerPaciente", "GET", "/api/pacientes/{id}", "/api/pacientes/2")
PUT_NOTE = exchange("salvarNota", "PUT", "/api/notas/{id}", "/api/notas/1", body=NOTE_BODY)
PATCH_NOTE = exchange("ajustarNota", "PATCH", "/api/notas/{id}", "/api/notas/1", body=NOTE_BODY)


def notes_rig(
    clinic: Notes | None = None,
    *,
    allow_writes: bool = True,
    methods: list[str] | None = None,
    **authz: Any,
) -> AuthzRig:
    """`AuthzRig` com a clínica de notas e o OpenAPI dela (`methods` restringe o escopo)."""
    data = clinic_profile_data(allow_writes=allow_writes, **authz)
    if methods is not None:
        data["scope"]["allow"][0]["methods"] = methods
    return AuthzRig(clinic or Notes(), profile=ProductProfile.from_data(data), spec=notes_spec())


def seed(rig: AuthzRig, *exchanges: ExchangeRecord) -> ProbeResult:
    """Roda o `probe` e troca `exchanges.json` pelos pedidos dados."""
    probe = rig.run_probe()
    if isinstance(rig.clinic, Notes):
        rig.clinic.reset()
    rig.store.exchanges[probe.run_id] = ExchangeLog(
        run_id=probe.run_id,
        product="agenda",
        exchanges=exchanges,
        next_unique_counter=rig.store.exchanges[probe.run_id].next_unique_counter,
    )
    return probe


def run_checks(
    rig: AuthzRig, exchanges: tuple[ExchangeRecord, ...], *checks: Any, dry_run: bool = False
) -> AuthzResult:
    """Semeia os pedidos e roda só as verificações pedidas."""
    probe = seed(rig, *exchanges)
    return rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=checks, dry_run=dry_run)
    )


def authz_sent(rig: AuthzRig, method: str | None = None) -> list[HttpRequest]:
    """Pedidos do estágio `authz` que chegaram ao alvo (opcionalmente por método)."""
    return [
        r
        for r in rig.target.requests
        if r.operation_id.startswith("authz:") and (method is None or r.method == method)
    ]

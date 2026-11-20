"""Alvo falso "catálogo" que valida (ou não) a entrada, e o cenário do `negative` (ADR 0051).

`Catalog` estende a `Clinic` do `authz` com `/api/produtos`:

- `GET /api/produtos?limite=&ordem=&busca=`: `limite` inteiro de 1 a 100, `ordem` em
  `asc|desc`, `busca` com até 10 caracteres;
- `POST /api/produtos` e `PUT`/`PATCH /api/produtos/1`: `nome` (1 a 20 caracteres, obrigatório
  em POST e PUT), `preco` (número, mínimo 0, obrigatório em POST e PUT), `status` (`ativo` ou
  `inativo`);
- `DELETE /api/produtos/1` registra a chamada em `deleted` (o teste nunca a deve provocar).

`mode` diz como o servidor reage a valor inválido: `validate` (422), `lax` (aceita e grava),
`crash` (500). `forced` troca o status de uma rota (`("GET", "api/produtos") -> 404`).

`NegativeRig` monta o perfil (com o bloco `negative`), o OpenAPI e o armazém em memória, roda o
`probe` de verdade (para haver `probe.json`) e troca `exchanges.json` pelos pedidos dados.
"""

import json
from typing import Any

from harness_dast.application.negative import Negative, NegativeRequest
from harness_dast.domain.api_model import ApiSpec, MediaBody, Operation, Parameter, RequestBody
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_exchange import ExchangeLog, ExchangeRecord
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.profile import ProductProfile
from tests.fakes.authz.rig import AuthzRig, Clinic, clinic_profile_data, clinic_spec
from tests.fakes.probe_ports import reply

PRODUCTS = "/api/produtos"
ONE = f"{PRODUCTS}/1"
NAME = Schema(type="string", min_length=1, max_length=20)
PRICE = Schema(type="number", minimum=0)
STATUS = Schema(type="string", enum=("ativo", "inativo"))
LIMIT = Schema(type="integer", minimum=1, maximum=100)
ORDER = Schema(type="string", enum=("asc", "desc"))
SEARCH = Schema(type="string", max_length=10)
SEED_PRODUCT: dict[str, Any] = {"id": 1, "nome": "Caneta", "preco": 5, "status": "ativo"}
SENT_MARKERS = ("not-a-number", "not-a-boolean", "not-in-enum", "12345")


def _invalid_params(query: str) -> bool:
    params = dict(part.partition("=")[::2] for part in query.split("&") if part)
    limit = params.get("limite")
    if limit is not None and not (limit.lstrip("-").isdigit() and 1 <= int(limit) <= 100):
        return True
    if params.get("ordem") not in {None, "asc", "desc"}:
        return True
    return len(params.get("busca", "")) > 10


def _invalid_body(body: dict[str, Any], *, required: bool) -> bool:
    name, price, status = body.get("nome"), body.get("preco"), body.get("status")
    if required and ("nome" not in body or "preco" not in body):
        return True
    if "nome" in body and not (isinstance(name, str) and 1 <= len(name) <= 20):
        return True
    if "preco" in body and not (
        isinstance(price, int | float) and not isinstance(price, bool) and price >= 0
    ):
        return True
    return "status" in body and status not in {"ativo", "inativo"}


class Catalog(Clinic):
    """A clínica com o catálogo de produtos."""

    def __init__(
        self,
        *,
        mode: str = "validate",
        forced: dict[tuple[str, str], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.mode = mode
        self.forced = forced or {}
        self.product: dict[str, Any] = dict(SEED_PRODUCT)
        self.created: list[dict[str, Any]] = []
        self.deleted = 0

    def _route(self, request: HttpRequest, path: str, alias: str) -> HttpResponse:
        if not path.startswith("api/produtos"):
            return super()._route(request, path, alias)
        forced = self.forced.get((request.method, path))
        if forced is not None:
            return reply(forced, {"code": "FORCADO"})
        if request.method == "DELETE":
            self.deleted += 1
            return reply(204)
        if request.method == "GET":
            return self._get(request, path)
        body = json.loads(request.body or b"{}")
        invalid = _invalid_body(body, required=request.method != "PATCH")
        if invalid and self.mode == "validate":
            return reply(422, {"code": "CORPO_INVALIDO"})
        if invalid and self.mode == "crash":
            return reply(500, {"code": "ERRO_INTERNO"})
        if request.method == "POST":
            self.created.append(body)
            return reply(201, {"id": len(self.created) + 1})
        self.product.update(body)
        return reply(200, dict(self.product))

    def _get(self, request: HttpRequest, path: str) -> HttpResponse:
        if path != "api/produtos":
            return reply(200, dict(self.product))
        invalid = _invalid_params(request.url.partition("?")[2])
        if invalid and self.mode == "validate":
            return reply(400, {"code": "PARAMETRO_INVALIDO"})
        if invalid and self.mode == "crash":
            return reply(500, {"code": "ERRO_INTERNO"})
        return reply(200, {"items": [dict(self.product)]})


def _query(name: str, schema: Schema, *, required: bool = False) -> Parameter:
    return Parameter(name=name, location="query", required=required, value_schema=schema)


def _json(schema: Schema) -> RequestBody:
    return RequestBody(
        required=True, media=(MediaBody(media_type="application/json", body_schema=schema),)
    )


def catalog_spec() -> ApiSpec:
    """A clínica mais as operações do catálogo (todas com `operationId` estável)."""
    base = clinic_spec()
    full = Schema(
        type="object",
        properties={"nome": NAME, "preco": PRICE, "status": STATUS},
        required=("nome", "preco"),
    )
    patch = full.model_copy(update={"required": ()})
    path_id = Parameter(
        name="id", location="path", required=True, value_schema=Schema(type="integer")
    )
    operations = (
        Operation(
            operation_id="listarProdutos",
            method="get",
            path=PRODUCTS,
            parameters=(_query("limite", LIMIT), _query("ordem", ORDER), _query("busca", SEARCH)),
        ),
        Operation(
            operation_id="criarProduto", method="post", path=PRODUCTS, request_body=_json(full)
        ),
        Operation(
            operation_id="atualizarProduto",
            method="put",
            path=f"{PRODUCTS}/{{id}}",
            parameters=(path_id,),
            request_body=_json(full),
        ),
        Operation(
            operation_id="ajustarProduto",
            method="patch",
            path=f"{PRODUCTS}/{{id}}",
            parameters=(path_id,),
            request_body=_json(patch),
        ),
        Operation(
            operation_id="removerProduto",
            method="delete",
            path=f"{PRODUCTS}/{{id}}",
            parameters=(path_id,),
        ),
    )
    return ApiSpec(
        title=base.title,
        version=base.version,
        servers=base.servers,
        operations=(*base.operations, *operations),
    )


def exchange(
    operation_id: str,
    method: str,
    path: str,
    target: str,
    *,
    body: dict[str, Any] | None = None,
    account: str = "adm",
    status: int = 200,
    omitted: tuple[str, ...] = (),
) -> ExchangeRecord:
    """Um pedido que o `probe` teria provado."""
    return ExchangeRecord(
        operation_id=operation_id,
        method=method,
        path=path,
        target=target,
        account=account,
        status=status,
        content_type="application/json" if body is not None else None,
        body=None if body is None else json.dumps(body, separators=(",", ":")),
        omitted_fields=omitted,
    )


LIST = exchange("listarProdutos", "GET", PRODUCTS, f"{PRODUCTS}?limite=10&ordem=asc&busca=abc")
CREATE = exchange(
    "criarProduto",
    "POST",
    PRODUCTS,
    PRODUCTS,
    body={"nome": "Caneta", "preco": 5, "status": "ativo"},
    status=201,
)
UPDATE = exchange(
    "atualizarProduto",
    "PUT",
    f"{PRODUCTS}/{{id}}",
    ONE,
    body={"nome": "Caneta", "preco": 5, "status": "ativo"},
)
ADJUST = exchange(
    "ajustarProduto", "PATCH", f"{PRODUCTS}/{{id}}", ONE, body={"preco": 5, "status": "ativo"}
)
REMOVE = exchange("removerProduto", "DELETE", f"{PRODUCTS}/{{id}}", ONE, status=204)


def catalog_profile_data(**negative: Any) -> dict[str, Any]:
    """Perfil da clínica com o bloco `negative` (vazio = padrão: só leitura)."""
    data = clinic_profile_data()
    if negative:
        data["negative"] = negative
    return data


class NegativeRig(AuthzRig):
    """`AuthzRig` com o catálogo e o `negative`."""

    def __init__(
        self,
        catalog: Catalog | None = None,
        *,
        profile_data: dict[str, Any] | None = None,
        **negative: Any,
    ) -> None:
        self.catalog = catalog or Catalog()
        data = profile_data or catalog_profile_data(**negative)
        super().__init__(self.catalog, profile=ProductProfile.from_data(data), spec=catalog_spec())

    def negative(self, kill_switch: Any = None, mutation_journal: Any = None) -> Negative:
        return Negative(
            profiles=self.profiles,
            specs=self._specs(),
            secrets=self.secrets,
            vault=self.vault,
            client=self.target,
            store=self.store,
            artifacts=self.artifacts,
            clock=self.clock,
            sleeper=self.clock,
            kill_switch=kill_switch,
            mutation_journal=mutation_journal,
        )

    def seed(self, *exchanges: ExchangeRecord) -> ProbeResult:
        """Roda o `probe` e troca `exchanges.json` pelos pedidos dados."""
        probe = self.run_probe()
        self.catalog.product = dict(SEED_PRODUCT)
        self.store.exchanges[probe.run_id] = ExchangeLog(
            run_id=probe.run_id, product="agenda", exchanges=exchanges
        )
        return probe

    def run(
        self, *exchanges: ExchangeRecord, kill_switch: Any = None, **request: Any
    ) -> NegativeResult:
        """Semeia os pedidos e roda o estágio."""
        probe = self.seed(*exchanges)
        return self.negative(kill_switch).execute(
            NegativeRequest(product="agenda", run_id=probe.run_id, **request)
        )

    def sent(self, method: str | None = None) -> list[HttpRequest]:
        """Pedidos do estágio `negative` que chegaram ao alvo (opcionalmente por método)."""
        return [
            r
            for r in self.target.requests
            if r.operation_id.startswith("negative:") and (method is None or r.method == method)
        ]

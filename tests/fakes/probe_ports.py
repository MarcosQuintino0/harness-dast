"""Falsos em memória das portas do `probe`, `preflight` e `spec inspect`, com comportamento."""

import json
from collections.abc import Callable

from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import ConfigError, ExternalToolError, HarnessError
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.http_messages import ApprovedRequest, HttpRequest, HttpResponse
from harness_dast.domain.probe_exchange import ExchangeLog
from harness_dast.domain.probe_result import ArtifactHashes, ProbeResult, RunManifest
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.secret_ref import SecretRef


def reply(
    status: int = 200,
    body: JsonValue | bytes = None,
    *,
    content_type: str | None = "application/json",
    retry_after: str | None = None,
    location: str | None = None,
) -> HttpResponse:
    """Monta uma resposta do alvo; `body` JSON é serializado."""
    if isinstance(body, bytes):
        raw = body
    elif body is None:
        raw = b""
    else:
        raw = json.dumps(body).encode()
    return HttpResponse(
        status=status,
        content_type=content_type,
        retry_after=retry_after,
        location=location,
        body=raw,
    )


type Handler = Callable[[HttpRequest, dict[str, str]], HttpResponse | HarnessError]


class FakeTarget:
    """`TargetClient` falso: um manipulador decide a resposta; guarda o que recebeu.

    O manipulador recebe a requisição e o "pote de cookies" da conta (que ele pode alterar,
    como faria um `Set-Cookie`). Só aceita `ApprovedRequest`, como o cliente real.
    """

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self.requests: list[HttpRequest] = []
        self.jars: dict[str, dict[str, str]] = {}

    def send(self, approved: ApprovedRequest) -> HttpResponse:
        if not isinstance(approved, ApprovedRequest):
            raise TypeError("o cliente só aceita requisições aprovadas")
        request = approved.request
        self.requests.append(request)
        jar = self.jars.setdefault(request.account or "", {})
        result = self._handler(request, jar)
        if isinstance(result, HarnessError):
            raise result
        return result

    def cookie_value(self, account: str, name: str) -> str | None:
        return self.jars.get(account, {}).get(name)

    def paths(self, method: str | None = None) -> list[str]:
        """Caminho (sem consulta) de cada requisição recebida, opcionalmente de um método."""
        found = []
        for request in self.requests:
            if method is None or request.method == method:
                found.append(request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0])
        return ["/" + path for path in found]


class FakeZap:
    """`ZapControl` falso com estado e falha injetável."""

    def __init__(self, version: str = "2.17.0") -> None:
        self._version = version
        self.fail: ExternalToolError | None = None
        self.sessions: list[str] = []
        self.contexts: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
        self.removed_prefixes: list[str] = []
        self.rules = ["hdast-auth", "hdast-old", "outra-regra"]

    def _check(self) -> None:
        if self.fail is not None:
            raise self.fail

    def version(self) -> str:
        self._check()
        return self._version

    def start_session(self, name: str) -> None:
        self._check()
        self.sessions.append(name)

    def create_context(self, name: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> int:
        self._check()
        self.contexts.append((name, include, exclude))
        return len(self.contexts)

    def remove_stale_rules(self, prefix: str) -> int:
        self._check()
        self.removed_prefixes.append(prefix)
        stale = [rule for rule in self.rules if rule.startswith(prefix)]
        self.rules = [rule for rule in self.rules if not rule.startswith(prefix)]
        return len(stale)


class InMemoryRunStore:
    """`RunStore` falso: guarda tudo em memória, na ordem em que foi gravado."""

    def __init__(self) -> None:
        self.manifests: dict[str, list[RunManifest]] = {}
        self.audit: dict[str, list[AuditEntry]] = {}
        self.probes: dict[str, ProbeResult] = {}
        self.exchanges: dict[str, ExchangeLog] = {}
        self.events: list[str] = []

    def write_manifest(self, run_id: str, manifest: RunManifest) -> None:
        self.manifests.setdefault(run_id, []).append(manifest)
        self.events.append("manifest")

    def append_audit(self, run_id: str, entry: AuditEntry) -> None:
        self.audit.setdefault(run_id, []).append(entry)
        self.events.append(f"audit:{entry.phase}")

    def write_probe(self, run_id: str, result: ProbeResult) -> None:
        self.probes[run_id] = result
        self.events.append("probe")

    def write_exchanges(self, run_id: str, log: ExchangeLog) -> None:
        self.exchanges[run_id] = log
        self.events.append("exchanges")

    def all_audit(self) -> list[AuditEntry]:
        return [entry for entries in self.audit.values() for entry in entries]

    def serialized(self) -> str:
        """Tudo que seria gravado em disco, como texto (para procurar vazamentos)."""
        parts = [m.model_dump_json() for ms in self.manifests.values() for m in ms]
        parts += [e.model_dump_json() for e in self.all_audit()]
        parts += [p.model_dump_json() for p in self.probes.values()]
        parts += [x.model_dump_json() for x in self.exchanges.values()]
        return "\n".join(parts)


class DictSecretProvider:
    """`SecretProvider` falso sobre um dicionário `NOME_DA_VARIÁVEL -> valor`."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def resolve(self, ref: SecretRef) -> str | None:
        value = self._values.get(ref.env_name)
        return value or None


class InMemorySpecs:
    """`SpecLoader` falso."""

    def __init__(self, spec: ApiSpec) -> None:
        self._spec = spec

    def load(self, product: str, profile: ProductProfile) -> ApiSpec:
        return self._spec


class InMemoryDocuments:
    """`ProductDocuments` falso; cada arquivo pode ser regra válida, ausente ou inválida."""

    def __init__(
        self,
        rules: DataRules | None = None,
        flows: FlowSpec | None = None,
        *,
        rules_error: ConfigError | None = None,
        flows_error: ConfigError | None = None,
    ) -> None:
        self._rules = rules
        self._flows = flows
        self._rules_error = rules_error
        self._flows_error = flows_error

    def load_data_rules(self, product: str) -> DataRules | None:
        if self._rules_error is not None:
            raise self._rules_error
        return self._rules

    def load_flows(self, product: str) -> FlowSpec | None:
        if self._flows_error is not None:
            raise self._flows_error
        return self._flows

    def hashes(self, product: str, profile: ProductProfile) -> ArtifactHashes:
        return ArtifactHashes(target_yml="a" * 64, openapi="b" * 64)

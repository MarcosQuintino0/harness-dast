"""ZAP falso (servidor HTTP real) com os endpoints de varredura, nas formas do spike do M0.

Complementa o `FakeZapServer` de `test_api_client.py` sem alterá-lo: aquele cobre sessão,
contexto e limpeza do Replacer; este cobre varredura ativa, política, Replacer, mensagens e
alertas. Cada chamada fica em `calls` para os testes conferirem ordem e parâmetros.
"""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from tests.fakes.local_server import Received, Reply

API_KEY = "chave-zap-segredo-123"


def ok(payload: object, status: int = 200) -> Reply:
    return Reply(status, json.dumps(payload).encode(), [("Content-Type", "application/json")])


def params(received: Received) -> dict[str, str]:
    return {
        k: v[0]
        for k, v in parse_qs(urlsplit(received.target).query, keep_blank_values=True).items()
    }


def error(code: str) -> Reply:
    return ok({"code": code, "message": code}, 400)


@dataclass
class FakeScanZapServer:
    """Estado e respostas do ZAP 2.17 para a varredura.

    Attributes:
        calls: (endpoint, parâmetros) em ordem.
        context_regex: Expressão que a URL de uma varredura precisa casar (como o contexto).
        api_key: Chave que o falso exige no cabeçalho.
        context_name: Nome do único contexto existente.
        context_id: Identificador do contexto existente.
        messages: Mensagens do histórico (dicionários no formato da API).
        alerts: Alertas (dicionários no formato da API).
        scan_states: Resposta de `ascan/view/scans` por consulta; a última se repete.
        stubborn_rules: Regras que `disableScanners` não consegue desligar.
        rules: Regras do Replacer (descrição -> parâmetros).
        policies: Nomes de políticas existentes.
    """

    calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    context_regex: str = r"^http://alvo/.*"
    api_key: str = API_KEY
    context_name: str = "hdast-run"
    context_id: str = "3"
    messages: list[dict[str, str]] = field(default_factory=list)
    alerts: list[dict[str, str]] = field(default_factory=list)
    scan_states: list[dict[str, str]] = field(
        default_factory=lambda: [
            {
                "id": "0",
                "progress": "100",
                "state": "FINISHED",
                "reqCount": "42",
                "alertCount": "2",
                "newAlertCount": "2",
            }
        ]
    )
    stubborn_rules: frozenset[str] = frozenset()
    rules: dict[str, dict[str, str]] = field(default_factory=dict)
    policies: set[str] = field(default_factory=set)
    options: dict[str, str] = field(default_factory=dict)
    disabled: set[str] = field(default_factory=set)
    _polls: int = 0

    def endpoints(self) -> list[str]:
        """Nomes dos endpoints chamados, em ordem."""
        return [name for name, _ in self.calls]

    def __call__(self, received: Received) -> Reply:
        if received.headers.get("x-zap-api-key") != self.api_key:
            return error("bad_api_key")
        match = re.fullmatch(r"/JSON/(\w+)/(view|action)/(\w+)/", received.path)
        if match is None:
            return error("bad_action")
        component, kind, name = match.groups()
        query = params(received)
        self.calls.append((f"{component}/{kind}/{name}", query))
        handler = getattr(self, f"_{component}_{kind}_{name}", None)
        if handler is None:
            return error("bad_action")
        reply: Reply = handler(query)
        return reply

    # --------------------------------------------------------------- contexto e histórico

    def _context_view_context(self, query: dict[str, str]) -> Reply:
        if query.get("contextName") != self.context_name:
            return error("does_not_exist")
        return ok(
            {"context": {"id": self.context_id, "name": self.context_name, "inScope": "true"}}
        )

    def _core_view_messages(self, query: dict[str, str]) -> Reply:
        start, count = int(query["start"]), int(query["count"])
        return ok({"messages": self.messages[start : start + count]})

    def _core_view_message(self, query: dict[str, str]) -> Reply:
        for message in self.messages:
            if message["id"] == query["id"]:
                return ok({"message": message})
        return error("does_not_exist")

    # --------------------------------------------------------------- varredura

    def _ascan_action_setOptionThreadPerHost(self, query: dict[str, str]) -> Reply:  # noqa: N802
        return self._option("threads", query)

    def _ascan_action_setOptionDelayInMs(self, query: dict[str, str]) -> Reply:  # noqa: N802
        return self._option("delay", query)

    def _ascan_action_setOptionMaxScanDurationInMins(self, query: dict[str, str]) -> Reply:  # noqa: N802
        return self._option("max_scan", query)

    def _ascan_action_setOptionMaxRuleDurationInMins(self, query: dict[str, str]) -> Reply:  # noqa: N802
        return self._option("max_rule", query)

    def _ascan_action_setOptionTargetParamsInjectable(self, query: dict[str, str]) -> Reply:  # noqa: N802
        return self._option("injectable", query)

    def _ascan_action_setOptionHostPerScan(self, query: dict[str, str]) -> Reply:  # noqa: N802
        return self._option("host_per_scan", query)

    def _option(self, name: str, query: dict[str, str]) -> Reply:
        if "Integer" not in query:
            return error("missing_parameter")
        self.options[name] = query["Integer"]
        return ok({"Result": "OK"})

    def _ascan_view_scanPolicyNames(self, query: dict[str, str]) -> Reply:  # noqa: N802
        return ok({"scanPolicyNames": sorted(self.policies)})

    def _ascan_action_removeScanPolicy(self, query: dict[str, str]) -> Reply:  # noqa: N802
        self.policies.discard(query["scanPolicyName"])
        return ok({"Result": "OK"})

    def _ascan_action_addScanPolicy(self, query: dict[str, str]) -> Reply:  # noqa: N802
        self.policies.add(query["scanPolicyName"])
        self.options["strength"] = query.get("attackStrength", "")
        self.options["threshold"] = query.get("alertThreshold", "")
        return ok({"Result": "OK"})

    def _ascan_action_disableScanners(self, query: dict[str, str]) -> Reply:  # noqa: N802
        for rule in query["ids"].split(","):
            if rule not in self.stubborn_rules:
                self.disabled.add(rule)
        return ok({"Result": "OK"})

    def _ascan_view_scanners(self, query: dict[str, str]) -> Reply:
        names = {"40018": "SQL Injection", "40044": "Exponential Entity Expansion", "10104": "UA"}
        return ok(
            {
                "scanners": [
                    {"id": rule, "name": name, "enabled": str(rule not in self.disabled).lower()}
                    for rule, name in names.items()
                ]
            }
        )

    def _ascan_action_scan(self, query: dict[str, str]) -> Reply:
        if "contextId" in query and not re.match(self.context_regex, query.get("url", "")):
            return error("url_not_in_context")
        return ok({"scan": "0"})

    def _ascan_view_scans(self, query: dict[str, str]) -> Reply:
        state = self.scan_states[min(self._polls, len(self.scan_states) - 1)]
        self._polls += 1
        return ok({"scans": [state]})

    def _ascan_action_stop(self, query: dict[str, str]) -> Reply:
        return ok({"Result": "OK"})

    # --------------------------------------------------------------- alertas e Replacer

    def _alert_view_alerts(self, query: dict[str, str]) -> Reply:
        start, count = int(query["start"]), int(query["count"])
        return ok({"alerts": self.alerts[start : start + count]})

    def _replacer_action_addRule(self, query: dict[str, str]) -> Reply:  # noqa: N802
        self.rules[query["description"]] = query
        return ok({"Result": "OK"})

    def _replacer_action_removeRule(self, query: dict[str, str]) -> Reply:  # noqa: N802
        if query["description"] not in self.rules:
            return error("does_not_exist")
        del self.rules[query["description"]]
        return ok({"Result": "OK"})

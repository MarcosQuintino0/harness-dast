"""A afirmação central do projeto, como teste de regressão.

Contra o OpenAPI REAL do VAmPI e um alvo em processo que faz cumprir unicidade (409 em
usuário/e-mail repetidos) e campos obrigatórios (400), a alcançabilidade COM regras de dados
é maior que a alcançabilidade SEM regras (valores implícitos do esquema).
"""

import json
import re
from pathlib import Path
from typing import Any

from harness_dast.adapters.openapi import load_spec
from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import HarnessError
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.profile import ProductProfile
from tests.fakes.probe_ports import InMemoryDocuments, reply
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.rig import Rig

VAMPI = Path(__file__).parents[2] / "fixtures" / "specs" / "vampi.yml"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")
RULES: dict[str, Any] = {
    "schema_version": 1,
    "rules": [
        {"match": {"field": "username"}, "generator": "constant", "args": {"value": "tester01"}},
        {"match": {"field": "password"}, "generator": "constant", "args": {"value": "Pwd12345"}},
        {"match": {"field": "email"}, "generator": "email", "unique": True},
        {"match": {"field": "book_title"}, "generator": "constant", "args": {"value": "livro01"}},
    ],
}
ENV = {"VAMPI_USER": "name1", "VAMPI_PASS": "pass1"}


def vampi_profile() -> ProductProfile:
    data = valid_profile_data("vampi")
    data["environment"]["base_url"] = "http://vampi:5000"
    data["scope"]["allow"] = [
        {
            "host": "vampi",
            "scheme": "http",
            "port": 5000,
            "paths": ["/**"],
            "methods": ["GET", "POST", "PUT", "DELETE"],
            "allow_local": True,
        }
    ]
    data["scope"]["deny_paths"] = ["/createdb"]
    data["auth"].update(
        token_path="/users/v1/login",  # noqa: S106 - sentinela ou nome de campo, não um segredo
        request_encoding="json",
        token_response_field="auth_token",  # noqa: S106 - sentinela ou nome de campo, não um segredo
    )
    data["auth"]["accounts"] = [
        {
            "alias": "user_a",
            "role": "usuario",
            "username": {"secret_ref": "env:VAMPI_USER"},
            "password": {"secret_ref": "env:VAMPI_PASS"},
        }
    ]
    data["probe"] = {
        "success": {"json_field_absent_or_not_equal": {"field": "status", "value": "fail"}},
        "health_path": "/",
    }
    return ProductProfile.from_data(data)


class FakeVampi:
    """Alvo em processo com as regras de unicidade e de campos obrigatórios do VAmPI."""

    def __init__(self) -> None:
        self.users = {"name1": {"password": "pass1", "email": "mail1@mail.com"}}
        self.books: dict[str, str] = {}

    def __call__(self, request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
        path = "/" + request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
        body = json.loads(request.body) if request.body else {}
        method = request.method
        if (method, path) == ("POST", "/users/v1/register"):
            return self.register(body)
        if (method, path) == ("POST", "/users/v1/login"):
            return self.login(body)
        if path in {"/", "/users/v1", "/users/v1/_debug", "/books/v1"} and method == "GET":
            return reply(200, {"message": "ok"})
        authorized = dict(request.headers).get("Authorization", "").startswith("Bearer tok-")
        if (
            not authorized
            and (path, method) != ("/books/v1", "GET")
            and not self._public(path, method)
        ):
            return reply(401, {"detail": "No authorization token provided"})
        return self.protected(method, path, body)

    @staticmethod
    def _public(path: str, method: str) -> bool:
        return method == "GET" and path.startswith("/users/v1/") and not path.endswith("/email")

    def register(self, body: dict[str, Any]) -> HttpResponse:
        if not all(
            isinstance(body.get(k), str) and body[k] for k in ("username", "password", "email")
        ):
            return reply(400, {"status": "fail", "message": "campos obrigatorios"})
        if not EMAIL.match(body["email"]):
            return reply(400, {"status": "fail", "message": "email invalido"})
        taken = body["username"] in self.users or any(
            u["email"] == body["email"] for u in self.users.values()
        )
        if taken:
            return reply(409, {"status": "fail", "message": "User already exists"})
        self.users[body["username"]] = {"password": body["password"], "email": body["email"]}
        return reply(200, {"status": "success", "message": "registered"})

    def login(self, body: dict[str, Any]) -> HttpResponse:
        user = self.users.get(body.get("username", ""))
        if user is None or user["password"] != body.get("password"):
            return reply(200, {"status": "fail", "message": "Password is not correct"})
        return reply(200, {"status": "success", "auth_token": f"tok-{body['username']}"})

    def protected(self, method: str, path: str, body: dict[str, Any]) -> HttpResponse:
        if path == "/me":
            return reply(200, {"username": "name1"})
        if path == "/books/v1" and method == "POST":
            return self.add_book(body)
        if path.startswith("/books/v1/"):
            known = path.rsplit("/", 1)[1] in self.books
            return reply(200, {"book": 1}) if known else reply(404, {"status": "fail"})
        match = re.fullmatch(r"/users/v1/([^/]+)(/email|/password)?", path)
        if match is None or match[1] not in self.users:
            return reply(404, {"status": "fail", "message": "User not found"})
        if match[2] == "/email":
            return (
                reply(204)
                if EMAIL.match(str(body.get("email", "")))
                else reply(400, {"status": "fail"})
            )
        if match[2] == "/password":
            return reply(204) if body.get("password") else reply(400, {"status": "fail"})
        return reply(200, {"username": match[1]})

    def add_book(self, body: dict[str, Any]) -> HttpResponse:
        title = body.get("book_title")
        if not title or not body.get("secret"):
            return reply(400, {"status": "fail"})
        if title in self.books:
            return reply(409, {"status": "fail", "message": "Book Already exists!"})
        self.books[title] = body["secret"]
        return reply(200, {"status": "success"})


def probe(rules: DataRules | None) -> ProbeResult:
    rig = Rig(
        profile=vampi_profile(),
        spec=load_spec(VAMPI),
        handler=FakeVampi(),
        env=ENV,
        documents=InMemoryDocuments(rules),
    )
    return rig.probe().execute(ProbeRequest(product="vampi", seed=7))


def by_operation(result: ProbeResult) -> dict[str, str]:
    return {item.operation_id.rsplit(".", 1)[-1]: item.outcome for item in result.operations}


def test_reachability_with_data_rules_is_higher_than_without_them() -> None:
    without = probe(None)
    with_rules = probe(DataRules.from_data(RULES))

    assert without.summary.reachability is not None
    assert with_rules.summary.reachability is not None
    assert with_rules.summary.reachability > without.summary.reachability
    assert with_rules.summary.successes > without.summary.successes
    assert with_rules.summary.reachability_all is not None
    assert without.summary.reachability_all is not None
    assert with_rules.summary.reachability_all > without.summary.reachability_all


def test_with_rules_every_sendable_operation_of_vampi_succeeds() -> None:
    result = probe(DataRules.from_data(RULES))

    outcomes = by_operation(result)
    assert result.summary.operations_total == 14
    assert result.summary.reachability == 1.0
    assert outcomes["populate_db"] == "skipped_denied"
    assert outcomes["delete_user"] == "skipped_destructive"
    assert outcomes["register_user"] == "success"
    assert outcomes["login_user"] == "success"
    assert outcomes["get_by_title"] == "success"


def test_without_rules_the_agent_sees_which_operations_failed_and_how() -> None:
    outcomes = by_operation(probe(None))

    assert outcomes["register_user"] == "validation_error"
    assert outcomes["login_user"] == "logical_failure"
    assert outcomes["get_by_username"] == "not_found"
    assert outcomes["update_email"] in {"not_found", "validation_error"}


def test_a_repeated_unique_value_would_be_a_conflict_without_the_unique_rule() -> None:
    fixed_email = {
        "schema_version": 1,
        "rules": [
            *RULES["rules"][:2],
            {
                "match": {"field": "email"},
                "generator": "constant",
                "args": {"value": "mail1@mail.com"},
            },
            RULES["rules"][3],
        ],
    }

    outcomes = by_operation(probe(DataRules.from_data(fixed_email)))

    assert outcomes["register_user"] == "conflict"

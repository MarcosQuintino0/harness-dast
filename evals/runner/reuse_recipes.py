"""Receitas de reuso restritas aos modelos do produto e ao contrato OpenAPI."""

import re
from collections.abc import Iterator
from pathlib import Path

import yaml

from evals.runner.cases import REPO_ROOT, EvalError
from evals.runner.models import Case
from harness_dast.adapters.openapi.loader import load_spec
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import Schema, flatten_schema
from harness_dast.domain.datagen import DataRule, DataRules
from harness_dast.domain.datagen_catalog import ArgSpec, get_generator
from harness_dast.domain.errors import HarnessError
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.strategy import Strategy


def _fields(
    schema: Schema, prefix: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], Schema]]:
    flat = flatten_schema(schema)
    if flat.items is not None and len(prefix) < 10:
        yield from _fields(flat.items, prefix)
    if len(prefix) >= 10:
        return
    for name, child in flat.properties.items():
        path = (*prefix, name)
        yield path, child
        yield from _fields(child, path)


def _matching(rule: DataRule, spec: ApiSpec) -> list[Schema]:
    matches: list[Schema] = []
    for op in spec.operations:
        for param in op.parameters:
            if rule.match.applies_to(op.operation_id, param.location, (param.name,)):
                matches.append(param.value_schema)
        media = op.request_body.preferred() if op.request_body else None
        if media is not None and media.body_schema is not None:
            for path, schema in _fields(media.body_schema):
                if rule.match.applies_to(op.operation_id, "body", path):
                    matches.append(schema)
    return matches


def _in_enum(value: object, schemas: list[Schema]) -> bool:
    return bool(schemas) and all(
        (enums := flatten_schema(schema).enum) is not None
        and any(type(item) is type(value) and item == value for item in enums)
        for schema in schemas
    )


_RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost")
_RESERVED_DOMAINS = ("example.com", "example.net", "example.org")
_LABEL = re.compile(r"[a-z0-9-]+")


def _reserved_host(value: str) -> bool:
    """Aceita só nome de host em domínio reservado para teste (RFC 2606/6761)."""
    if len(value) > 253 or not all(_LABEL.fullmatch(label) for label in value.split(".")):
        return False
    return value.endswith(_RESERVED_SUFFIXES) or any(
        value == domain or value.endswith(f".{domain}") for domain in _RESERVED_DOMAINS
    )


def _template_args(generator: str, name: str) -> list[object]:
    """Valores do mesmo gerador e argumento no modelo oficial; falha fechado se ele faltar."""
    path = REPO_ROOT / "products/_template/data-rules.yml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        rules = DataRules.from_data(data)
    except (OSError, UnicodeError, yaml.YAMLError, HarnessError):
        raise EvalError(
            "Modelo products/_template/data-rules.yml ausente ou malformado; nada foi exportado."
        ) from None
    return [
        rule.args[name] for rule in rules.rules if rule.generator == generator and name in rule.args
    ]


def _textual_allowed(rule: DataRule, name: str, value: str, arg: ArgSpec) -> bool:
    if (arg.choices is not None and value in arg.choices) or value == arg.default:
        return True
    if rule.generator == "email" and name == "domain" and _reserved_host(value):
        return True
    return value in _template_args(rule.generator, name)


def _safe_rule(rule: DataRule, spec: ApiSpec) -> None:
    schemas = _matching(rule, spec)
    if not schemas:
        raise EvalError("Regra de dados não corresponde ao contrato.")
    definition = get_generator(rule.generator)
    declared = {arg.name: arg for arg in definition.args}
    for name, value in rule.args.items():
        values = value if isinstance(value, list) else [value]
        arg = declared[name]
        if rule.generator in {"constant", "choice"}:
            if not all(_in_enum(item, schemas) for item in values):
                raise EvalError("Constante de dados sem enum correspondente no OpenAPI.")
        elif isinstance(value, str) and not _textual_allowed(rule, name, value, arg):
            raise EvalError("Argumento textual livre de gerador não é exportável.")
        elif rule.generator == "sequence" and name == "start":
            raise EvalError("Início fixo de sequência não é exportável.")
        elif rule.generator in {"integer", "number"} and name in {"min", "max"}:
            attribute = "minimum" if name == "min" else "maximum"
            if not all(getattr(flatten_schema(schema), attribute) == value for schema in schemas):
                raise EvalError("Limite numérico não foi declarado em todos os campos do OpenAPI.")


def _document(root: Path, name: str) -> object:
    try:
        from evals.runner.reuse import UniqueLoader, _regular

        content = _regular(root, name).read_text(encoding="utf-8")
        return yaml.load(content, Loader=UniqueLoader)  # noqa: S506 - herda SafeLoader
    except (OSError, UnicodeError, yaml.YAMLError):
        raise EvalError("Receita ausente ou malformada.") from None


def _dump(value: object) -> str:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=True)


def _target(profile: ProductProfile, spec: ApiSpec, case: Case) -> str:
    auth = profile.auth.model_dump(mode="json")
    accounts = auth["accounts"]
    allowed = {
        (account.alias, account.role, f"env:{account.username_env}", f"env:{account.password_env}")
        for account in case.expected.accounts
    }
    if auth["type"] != "login_password" or any(
        (
            account["alias"],
            account["role"],
            account["username"]["secret_ref"],
            account["password"]["secret_ref"],
        )
        not in allowed
        for account in accounts
    ):
        raise EvalError("Contas ou referências não conferem com a carta do caso.")
    proposed_auth: dict[str, object] = {"type": auth["type"], "accounts": accounts}
    proposed = {
        "schema_version": 1,
        "product": profile.product,
        "state": "review_required",
        "auth": proposed_auth,
    }
    if "token_path" in auth and any(op.path == auth["token_path"] for op in spec.operations):
        proposed_auth["token_path"] = auth["token_path"]
    return _dump(proposed)


def recipes(root: Path, product: str, basis: dict[str, object], case: Case) -> dict[str, str]:
    """Valida documentos presentes e devolve somente projeção e receitas sanitizadas."""
    try:
        profile = FileProfileRepository(root).load(product)
        from evals.runner.reuse import _regular

        folder = root / product
        spec = load_spec(_regular(folder, profile.openapi, 8 * 1024 * 1024))
        files = {"target.reuse.yml": _target(profile, spec, case)}
        if (folder / "data-rules.yml").exists():
            rules = DataRules.from_data(_document(folder, "data-rules.yml"))
            for rule in rules.rules:
                _safe_rule(rule, spec)
            files["data-rules.yml"] = _dump(rules.model_dump(mode="json", exclude_none=True))
        if (folder / "flows.yml").exists():
            flow = FlowSpec.from_data(_document(folder, "flows.yml"))
            flow.validate_against(spec)
            if any(
                spec.get_operation(item.produces.operation).success_schema() is None
                for item in flow.bindings
            ):
                raise EvalError("Origem do fluxo sem esquema no OpenAPI.")
            files["flows.yml"] = _dump(flow.model_dump(mode="json", exclude_none=True))
        if (folder / "strategy.yml").exists():
            strategy = Strategy.from_data(_document(folder, "strategy.yml"))
            if any(
                choice.basis is None or choice.basis.model_dump() != basis
                for choice in strategy.choices
            ):
                raise EvalError("Estratégia sem vínculo atual às fontes da origem.")
            payload = strategy.model_dump(mode="json", exclude_none=True)
            for choice in payload["choices"]:
                choice["state"] = "review_required"
            files["strategy.yml"] = _dump(payload)
    except HarnessError:
        raise EvalError("Receita inválida; nada foi exportado.") from None
    return files

"""Leitura de cada seção da carta para os valores do perfil (ADR 0036).

Cada função confere uma seção com os MESMOS modelos do perfil (`ScopeRule`, `RunLimits`,
`Authorization`, `LoginAccount`...), de modo que a carta não tem regra própria que possa
divergir do perfil: o que o perfil recusa, a carta recusa. Devolve o pedaço do perfil já em
forma canônica ou `None`, com as pendências no `Collector`. Este módulo é puro.
"""

from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from harness_dast.domain.auth import Account, ApiKeyAccount, LoginAccount, LoginLimit
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.letter import (
    Answer,
    AuthorizationSection,
    AuthSection,
    EnvironmentSection,
    LimitsSection,
    ScopeSection,
)
from harness_dast.domain.letter_collect import (
    INVALID_VALUE,
    PLACEHOLDER,
    WIDE_NEEDS_LETTER,
    Collector,
    has_placeholder,
)
from harness_dast.domain.profile import Environment
from harness_dast.domain.run import RunLimits
from harness_dast.domain.scope import PathMode, Scope, ScopeRule
from harness_dast.domain.window import Authorization, ExecutionWindow

Block = dict[str, object]
_PLACEHOLDER_TEXT = "Valor de modelo (exemplo) não vale como resposta; informe o valor real."
_LOGIN_OPTION_KEYS = (
    "request_encoding",
    "username_field",
    "password_field",
    "token_response_field",
    "token_header",
    "token_scheme",
)
_STRENGTHS = ("LOW", "MEDIUM", "HIGH")
_AUTH_TYPES = ("login_password", "api_key")
_EXAMPLES = TypeAdapter(list[dict[str, JsonValue]])


def read_environment(c: Collector, section: EnvironmentSection) -> tuple[Block, str] | None:
    """Ambiente: `environment` e o caminho do OpenAPI. `None` se algo falhou."""
    name = c.take_text("environment.name", section.name)
    base_url = c.take_text("environment.base_url", section.base_url)
    openapi = c.take_text("environment.openapi", section.openapi)
    present = {k: v for k, v in (("name", name), ("base_url", base_url)) if v is not None}
    filler = {"name": "x", "base_url": "https://filler.example.net"}
    env = c.check_model("environment", Environment, present, filler)
    if env is None or name is None or base_url is None or openapi is None:
        return None
    return {"name": env.name, "base_url": env.base_url}, openapi


def _rule_block(rule: ScopeRule) -> Block:
    block: Block = {"host": rule.host, "scheme": rule.scheme}
    if rule.port is not None:
        block["port"] = rule.port
    if rule.allow_local:
        block["allow_local"] = True
    block["paths"] = list(rule.paths)
    block["methods"] = list(rule.methods)
    return block


def _read_rules(c: Collector, answer: Answer | None) -> list[ScopeRule] | None:
    items = c.take_list("scope.allow", answer, scan_placeholders=False)
    if items is None:
        return None
    rules: list[ScopeRule] = []
    for index, item in enumerate(items):
        field = f"scope.allow[{index}]"
        if not isinstance(item, Mapping):
            c.add(field, INVALID_VALUE, "Esperado um mapa com host, scheme, paths e methods.")
        elif has_placeholder(item):
            c.add(field, PLACEHOLDER, _PLACEHOLDER_TEXT)
        elif (rule := c.check_model(field, ScopeRule, item, {})) is not None:
            rules.append(rule)
    return rules if len(rules) == len(items) else None


def _read_path_mode(c: Collector, answer: Answer | None) -> PathMode | None:
    """`strict` por padrão; `wide` só com origem `carta` e a frase que o autoriza."""
    value = c.take("scope.path_mode", answer, required=False)
    if value is None or value == "strict":
        return "strict"
    if value != "wide":
        c.add("scope.path_mode", INVALID_VALUE, "Use strict ou wide.")
        return None
    from_letter = answer is not None and answer.source == "carta"
    quote = answer.quote if answer is not None else None
    if not from_letter or not (quote or "").strip():
        c.add(
            "scope.path_mode",
            WIDE_NEEDS_LETTER,
            "O modo amplo só vale se a carta assinada o autorizar: use source: carta e copie "
            "em quote a frase da carta. O agente nunca o liga por conta própria.",
        )
        return None
    return "wide"


def read_scope(c: Collector, section: ScopeSection) -> Block | None:
    """Escopo de rede: `allow`, `deny_paths` e `path_mode`."""
    rules = _read_rules(c, section.allow)
    deny = c.take_list("scope.deny_paths", section.deny_paths, allow_empty=True)
    mode = _read_path_mode(c, section.path_mode)
    if deny is not None and not all(isinstance(item, str) for item in deny):
        c.add(
            "scope.deny_paths", INVALID_VALUE, "Esperada uma lista de textos (padrões de caminho)."
        )
        deny = None
    if rules is None or deny is None or mode is None:
        return None
    scope = c.check_model("scope", Scope, {"allow": tuple(rules), "deny_paths": tuple(deny)}, {})
    if scope is None:
        return None
    return {
        "allow": [_rule_block(rule) for rule in scope.allow],
        "deny_paths": list(scope.deny_paths),
        "path_mode": mode,
    }


def _read_windows(c: Collector, answer: Answer | None) -> list[str] | None:
    items = c.take_list("authorization.windows", answer)
    if items is None:
        return None
    windows: list[str] = []
    for index, item in enumerate(items):
        field = f"authorization.windows[{index}]"
        if not isinstance(item, str):
            c.add(field, INVALID_VALUE, "Esperado um texto no formato compacto.")
            continue
        try:
            ExecutionWindow.parse(item)
        except ConfigError as error:
            c.add(field, INVALID_VALUE, f"{error.message} {error.hint or ''}".strip())
        else:
            windows.append(item.strip())
    return windows if len(windows) == len(items) else None


def read_authorization(
    c: Collector, section: AuthorizationSection
) -> tuple[Block, list[str]] | None:
    """Autorização (`reference`, `valid_until`) e janelas."""
    reference = c.take_text("authorization.reference", section.reference)
    valid_until = c.take("authorization.valid_until", section.valid_until)
    windows = _read_windows(c, section.windows)
    present: dict[str, object] = {}
    if reference is not None:
        present["reference"] = reference
    if valid_until is not None:
        present["valid_until"] = valid_until
    filler = {"reference": "x", "valid_until": "2000-01-01"}
    auth = c.check_model("authorization", Authorization, present, filler)
    if auth is None or reference is None or valid_until is None or windows is None:
        return None
    return {"reference": auth.reference, "valid_until": auth.valid_until}, windows


def read_limits(c: Collector, section: LimitsSection) -> Block | None:
    """Limites de carga, os três obrigatórios."""
    answers = {
        "requests_per_second": section.requests_per_second,
        "max_duration_minutes": section.max_duration_minutes,
        "zap_threads_per_host": section.zap_threads_per_host,
    }
    present = {
        name: value
        for name, answer in answers.items()
        if (value := c.take(f"limits.{name}", answer)) is not None
    }
    filler = {"requests_per_second": 1, "max_duration_minutes": 1, "zap_threads_per_host": 1}
    limits = c.check_model("limits", RunLimits, present, filler)
    if limits is None or len(present) != len(answers):
        return None
    return {
        "requests_per_second": limits.requests_per_second,
        "max_duration_minutes": limits.max_duration_minutes,
        "zap_threads_per_host": limits.zap_threads_per_host,
    }


def _account_block(account: Account) -> Block:
    block: Block = {"alias": account.alias, "role": account.role}
    if isinstance(account, LoginAccount):
        block["username"] = {"secret_ref": account.username.secret_ref}
        block["password"] = {"secret_ref": account.password.secret_ref}
    elif isinstance(account, ApiKeyAccount):
        block["api_key"] = {"secret_ref": account.api_key.secret_ref}
    return block


def _read_accounts(c: Collector, answer: Answer | None, kind: str) -> list[Block] | None:
    items = c.take_list("auth.accounts", answer, scan_placeholders=False)
    if items is None:
        return None
    model = LoginAccount if kind == "login_password" else ApiKeyAccount
    blocks: list[Block] = []
    for index, item in enumerate(items):
        field = f"auth.accounts[{index}]"
        if not isinstance(item, Mapping):
            c.add(field, INVALID_VALUE, "Esperado um mapa com alias, role e o nome do segredo.")
        elif has_placeholder(item):
            c.add(field, PLACEHOLDER, _PLACEHOLDER_TEXT)
        elif (account := c.check_model(field, model, item, {})) is not None:
            blocks.append(_account_block(account))
    return blocks if len(blocks) == len(items) else None


def _read_login_options(c: Collector, answer: Answer | None) -> Block | None:
    value = c.take("auth.login_options", answer, required=False)
    if value is None:
        return {}
    if not isinstance(value, Mapping) or not all(isinstance(v, str) for v in value.values()):
        c.add("auth.login_options", INVALID_VALUE, "Esperado um mapa de campo para texto.")
        return None
    unknown = sorted(str(key) for key in value if key not in _LOGIN_OPTION_KEYS)
    if unknown:
        c.add("auth.login_options", INVALID_VALUE, "Campo desconhecido: " + ", ".join(unknown))
        return None
    return {key: value[key] for key in _LOGIN_OPTION_KEYS if key in value}


def _read_login_limit(c: Collector, answer: Answer | None) -> Block | None:
    value = c.take("auth.login_max_per_minute", answer, required=False)
    if value is None:
        return {}
    limit = c.check_model("auth.login_max_per_minute", LoginLimit, {"max_per_minute": value}, {})
    return None if limit is None else {"max_per_minute": limit.max_per_minute}


def read_auth(c: Collector, section: AuthSection) -> Block | None:
    """Autenticação: tipo, onde entrar, ajustes opcionais do login e contas."""
    kind = c.take_text("auth.type", section.type)
    if kind is not None and kind not in _AUTH_TYPES:
        c.add("auth.type", INVALID_VALUE, "Use login_password ou api_key.")
        return None
    if kind is None:
        return None
    block: Block = {"type": kind}
    if kind == "login_password":
        path = c.take_text("auth.token_path", section.token_path)
        options = _read_login_options(c, section.login_options)
        limit = _read_login_limit(c, section.login_max_per_minute)
        block["token_path"] = path
        block.update(options or {})
        if limit:
            block["login_limit"] = limit
        failed = path is None or options is None or limit is None
    else:
        header = c.take_text("auth.header_name", section.header_name)
        block["header_name"] = header
        failed = header is None
        failed = _forbid_login_fields(c, section) or failed
    accounts = _read_accounts(c, section.accounts, kind)
    block["accounts"] = accounts
    return None if failed or accounts is None else block


def _forbid_login_fields(c: Collector, section: AuthSection) -> bool:
    found = False
    for name in ("token_path", "login_options", "login_max_per_minute"):
        if getattr(section, name) is not None:
            c.add(f"auth.{name}", INVALID_VALUE, "Só vale para auth.type: login_password.")
            found = True
    return found


def read_strength(c: Collector, answer: Answer | None) -> str | None:
    """Força do ataque, opcional; `None` mantém o padrão do perfil."""
    value = c.take_text("attack.strength", answer, required=False)
    if value is not None and value not in _STRENGTHS:
        c.add("attack.strength", INVALID_VALUE, "Use LOW, MEDIUM ou HIGH.")
        return None
    return value


def read_example_data(c: Collector, answer: Answer | None) -> tuple[dict[str, JsonValue], ...]:
    """Dados de exemplo (informação para o agente; não viram regra)."""
    value = c.take("example_data", answer, required=False, scan_placeholders=False)
    if value is None:
        return ()
    try:
        return tuple(_EXAMPLES.validate_python(value))
    except ValidationError:
        c.add(
            "example_data",
            INVALID_VALUE,
            "Esperada uma lista de mapas (operation, field, value, note) só com texto, número, "
            "verdadeiro/falso ou lista.",
        )
        return ()

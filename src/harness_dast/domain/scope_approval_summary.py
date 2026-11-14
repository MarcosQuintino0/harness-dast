"""Resumo legível dos blocos de proteção, para a pessoa ler antes de aprovar (ADR 0037).

Mostra, em português e em linhas curtas, o que a aprovação trava: endereço, o que pode, o que é
proibido, modo de caminho, janela, validade, limites, contas e papéis e a força do ataque.
Mostra NOMES de `secret_ref`, nunca valor de segredo. Este módulo é puro.
"""

from harness_dast.domain.auth import PasswordLoginAuth
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope import ScopeRule
from harness_dast.domain.window import ExecutionWindow

_DAY_NAMES = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
_MINUTES_PER_HOUR = 60


def _clock(minute: int) -> str:
    return f"{minute // _MINUTES_PER_HOUR:02d}:{minute % _MINUTES_PER_HOUR:02d}"


def _window_text(window: ExecutionWindow) -> str:
    days = ",".join(_DAY_NAMES[day] for day in sorted(window.days))
    return f"{days} {_clock(window.start_minute)}-{_clock(window.end_minute)} {window.timezone}"


def _origin(rule: ScopeRule) -> str:
    port = "" if rule.port is None else f":{rule.port}"
    return f"{rule.scheme}://{rule.host}{port}"


def _rule_line(rule: ScopeRule) -> str:
    methods = ", ".join(rule.methods)
    return f"  - {_origin(rule)}  métodos {methods}  caminhos {', '.join(rule.paths)}"


def _path_mode_line(profile: ProductProfile) -> str:
    if profile.scope.path_mode == "wide":
        return (
            "Modo de caminho: AMPLO (wide). Só vale se a carta de autorização o diz; "
            "afrouxa a liberação de caminhos ambíguos no proxy."
        )
    return "Modo de caminho: estrito (strict)."


def _account_lines(profile: ProductProfile) -> list[str]:
    lines = []
    for account in profile.auth.accounts:
        refs = sorted(
            value["secret_ref"]
            for key, value in account.model_dump(mode="json").items()
            if key not in {"alias", "role"}
        )
        lines.append(f"  - {account.alias} (papel: {account.role}); credenciais: {', '.join(refs)}")
    return lines


def _login_line(profile: ProductProfile) -> str:
    auth = profile.auth
    if isinstance(auth, PasswordLoginAuth):
        limit = auth.login_limit
        rate = "" if limit is None else f"; no máximo {limit.max_per_minute} por minuto"
        return f"Login: usuário e senha em POST {auth.token_path}{rate}."
    return f"Login: chave fixa no cabeçalho {auth.header_name}."


def _strength_line(profile: ProductProfile) -> str:
    scan = profile.scan
    methods = ", ".join(scan.mutating_methods) or "nenhum"
    injection = "sim" if scan.url_path_injection else "não"
    return (
        f"Ataque: força {scan.strength}; PUT/PATCH sobre qualquer recurso: {methods}; "
        f"injeção em parâmetro de caminho: {injection}."
    )


def describe_protection(profile: ProductProfile) -> tuple[str, ...]:
    """Linhas legíveis dos blocos que a aprovação trava (sem segredo, sem valor de variável)."""
    scope = profile.scope
    limits = profile.limits
    environment = profile.environment
    tls = "" if environment.verify_tls else " (SEM verificar o certificado TLS)"
    denied = ", ".join(scope.deny_paths) or "nenhum caminho negado"
    return (
        f"Produto: {profile.product}",
        f"Ambiente: {environment.name}, endereço {environment.base_url}{tls}",
        "Pode alcançar (e só isto):",
        *(_rule_line(rule) for rule in scope.allow),
        f"Proibido em qualquer endereço: {denied}",
        _path_mode_line(profile),
        f"Autorização: {scope.authorization.reference}, válida até "
        f"{scope.authorization.valid_until.isoformat()}",
        "Janelas de execução: " + "; ".join(_window_text(w) for w in scope.windows),
        f"Limites: {limits.requests_per_second} req/s, {limits.max_duration_minutes} min, "
        f"{limits.zap_threads_per_host} thread(s) do ZAP por host",
        f"Autenticação: {profile.auth.type}",
        _login_line(profile),
        "Contas de teste:",
        *_account_lines(profile),
        _strength_line(profile),
        "Teste de autorização repete com os métodos: " + ", ".join(profile.authz.vertical_methods),
    )

"""Resumo legível dos blocos de proteção, para a pessoa ler antes de aprovar (ADR 0037).

Mostra, em português e em linhas curtas, o que a aprovação trava: endereço, o que pode, o que é
proibido, modo de caminho, janela, validade, limites, contas e papéis, a política da varredura,
o teste de autorização, o teste de valores inválidos e a limpeza do ambiente.
Mostra NOMES de `secret_ref`, nunca valor de segredo. Este módulo é puro.
"""

from harness_dast.domain.auth import PasswordLoginAuth
from harness_dast.domain.authz.config import (
    DEFAULT_DERIVED_LIMIT,
    DEFAULT_MASS_METHODS,
    AuthzConfig,
)
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.redaction import strip_control
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


def _outcomes_lines(profile: ProductProfile) -> list[str]:
    """Linha das classes extras da varredura (ADR 0050); vazio no padrão."""
    classes = profile.scan.include_outcomes
    if not classes:
        return []
    return [
        "ATACA TAMBÉM OPERAÇÕES QUE DERAM: " + ", ".join(classes) + " (scan.include_outcomes): "
        "o ataque parte de um pedido que o alvo recusou ou não achou, e nos POST, PUT e PATCH "
        "cria e altera mais dados sintéticos"
    ]


def _upload_lines(profile: ProductProfile) -> list[str]:
    """Linha da varredura de envio de arquivo (ADR 0052); vazio no padrão."""
    if not profile.scan.allow_upload_scan:
        return []
    return [
        "VARRE TAMBÉM OPERAÇÕES DE ENVIO DE ARQUIVO (scan.allow_upload_scan): o ZAP grava "
        "conteúdo de ataque (nome e conteúdo de arquivo, campos de texto) no armazenamento do "
        "alvo, e esta ferramenta não o controla"
    ]


def _v112_lines(profile: ProductProfile) -> list[str]:
    """Linhas das chaves da V1.12 (ADR 0096); vazio quando tudo vale o padrão."""
    scan = profile.scan
    checks = profile.extra_checks
    lines: list[str] = []
    if scan.pacing != "legacy":
        lines.append(f"RITMO DA VARREDURA: {scan.pacing} (scan.pacing)")
    if scan.inject_headers:
        lines.append(
            "INJETA TAMBÉM EM CABEÇALHOS E COOKIES (scan.inject_headers): mais pedidos ao alvo"
        )
    if scan.oast:
        lines.append(
            "RETORNO FORA DE BANDA (scan.oast): o alvo é induzido a chamar o servidor de retorno "
            "do laboratório"
        )
    if checks.allow_rate_tests:
        lines.append(
            "TESTES DE LIMITE DE CONSUMO (extra_checks.allow_rate_tests): poucos pedidos "
            "repetidos, com teto"
        )
    if checks.experimental_rules:
        lines.append(
            "REGRAS EXPERIMENTAIS DO ZAP (extra_checks.experimental_rules): achados marcados "
            "como experimentais"
        )
    if checks.inventory:
        lines.append(
            "INVENTÁRIO DE VERSÕES IRMÃS E DOCUMENTAÇÃO (extra_checks.inventory): só caminhos "
            "que a cerca permite"
        )
    return lines


def _scan_policy_line(profile: ProductProfile) -> str:
    scan = profile.scan
    rules = ", ".join(str(rule) for rule in sorted(scan.disable_rules)) or "nenhuma"
    return (
        f"Varredura: limiar {scan.threshold}; regras do ZAP desligadas: {rules}; "
        f"tetos de {scan.max_scan_minutes} min por varredura e {scan.max_rule_minutes} min por "
        f"regra; token renovado a cada {scan.token_refresh_seconds} s; "
        f"código de saída 1 a partir de: {scan.fail_on}."
    )


def _authz_lines(profile: ProductProfile) -> list[str]:
    authz = profile.authz
    public = ", ".join(sorted(authz.public_operations)) or "nenhuma"
    disabled = ", ".join(sorted(authz.disabled_checks)) or "nenhuma"
    mass = ", ".join(field.name for field in authz.mass_assignment_fields) or "nenhum"
    roles = " < ".join(authz.role_order) or "não declarada"
    lines = [
        "Teste de autorização repete com os métodos: " + ", ".join(authz.vertical_methods),
        f"  - operações tratadas como públicas (não geram achado): {public}",
        f"  - verificações desligadas: {disabled}",
        f"  - campos da atribuição em massa: {mass}; ordem de papéis: {roles}",
    ]
    lines += _authz_mass_lines(authz)
    lines += _authz_matrix_lines(authz)
    if authz.shared_roles:
        lines.append(
            "  - papéis compartilhados, sem comparação horizontal entre contas: "
            + ", ".join(
                sorted(strip_control(role, keep_newlines=False) for role in authz.shared_roles)
            )
        )
    if authz.id_parameters:
        lines.append(
            "  - parâmetros de consulta tratados como identificador de objeto (BOLA de leitura): "
            + ", ".join(authz.id_parameters)
        )
    if authz.allow_writes:
        lines.append(
            "  - ESCRITA AUTORIZADA (authz.allow_writes: true): o teste entre contas pode "
            "alterar dados do ambiente (atribuição em massa, métodos de escrita acima e PUT/PATCH "
            "em recurso de outra conta)"
        )
    return lines


def _negative_lines(profile: ProductProfile) -> list[str]:
    """Linhas do teste de valores que o esquema proíbe (ADR 0051); vazio no padrão."""
    negative = profile.negative
    if negative.is_default():
        return []
    lines = [
        f"VALORES INVÁLIDOS: até {negative.max_requests} pedidos, "
        f"{negative.max_cases_per_operation} por operação (negative)"
    ]
    if negative.disabled_classes:
        lines.append("  - classes desligadas: " + ", ".join(sorted(negative.disabled_classes)))
    if negative.allow_writes:
        lines.append(
            "  - ESCRITA DE VALOR INVÁLIDO AUTORIZADA (negative.allow_writes: true): o teste "
            "grava dado com valor que o contrato proíbe (POST, PUT e PATCH; nunca DELETE)"
        )
    return lines


def _authz_matrix_lines(authz: AuthzConfig) -> list[str]:
    """Toda a tabela "quem pode o quê" (ADR 0041), uma linha por operação; vazio sem tabela.

    A pessoa só aprova o que viu: por isso a lista é inteira, sem corte, em ordem alfabética.
    """
    if not authz.access_matrix:
        return []

    def shown(roles: tuple[str, ...]) -> str:
        return (
            ", ".join(sorted(strip_control(role, keep_newlines=False) for role in roles))
            or "ninguém"
        )

    lines = [
        f"  - tabela quem pode o quê ({len(authz.access_matrix)} operação(ões)); papel que não "
        "aparece numa linha não é testado:"
    ]
    for rule in sorted(authz.access_matrix, key=lambda item: item.operation):
        name = strip_control(rule.operation, keep_newlines=False)
        lines.append(
            f"    - operação {name}: podem {shown(rule.allow)}; não podem {shown(rule.deny)}"
        )
    return lines


def _authz_mass_lines(authz: AuthzConfig) -> list[str]:
    """Linhas da atribuição em massa que fogem do padrão (ADR 0040); vazio no padrão."""
    lines: list[str] = []
    if not authz.derive_mass_candidates:
        lines.append("  - campos derivados do OpenAPI na atribuição em massa: DESLIGADOS")
    if authz.max_derived_candidates != DEFAULT_DERIVED_LIMIT:
        lines.append(
            f"  - máximo de campos derivados por operação: {authz.max_derived_candidates} "
            f"(padrão {DEFAULT_DERIVED_LIMIT})"
        )
    if authz.mass_assignment_methods != DEFAULT_MASS_METHODS:
        lines.append(
            "  - atribuição em massa só nos métodos: " + ", ".join(authz.mass_assignment_methods)
        )
    return lines


def _cleanup_lines(profile: ProductProfile) -> list[str]:
    cleanup = profile.cleanup
    if cleanup is None:
        return ["Limpeza do ambiente: não configurada."]
    refs = [cleanup.connection.secret_ref]
    refs += [ref.secret_ref for ref in (cleanup.user, cleanup.password) if ref is not None]
    tables = ", ".join(cleanup.allowed_tables) or "nenhuma"
    ceiling = "sem teto" if cleanup.max_rows is None else f"até {cleanup.max_rows} linhas"
    schema = "" if cleanup.db_schema is None else f"; esquema {cleanup.db_schema}"
    return [
        f"Limpeza do ambiente: script {cleanup.script}; credenciais: {', '.join(sorted(refs))}",
        f"  - tabelas permitidas: {tables}; {ceiling}{schema}",
    ]


def _technology_lines(profile: ProductProfile) -> list[str]:
    declaration = profile.technologies
    if declaration is None:
        return []
    return [
        "Tecnologias declaradas na carta: " + ", ".join(declaration.value),
        "  - frase da carta: " + strip_control(declaration.quote, keep_newlines=False),
        "  - informação consultiva: não confirma tecnologia nem reduz cobertura; "
        "todas as regras continuam ativas.",
    ]


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
        _scan_policy_line(profile),
        *_technology_lines(profile),
        *_outcomes_lines(profile),
        *_upload_lines(profile),
        *_v112_lines(profile),
        *_authz_lines(profile),
        *_negative_lines(profile),
        *_cleanup_lines(profile),
    )

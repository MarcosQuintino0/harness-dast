"""Caso de uso: validar o perfil de um produto e dizer se ele já pode ser executado.

Separa duas perguntas. (1) O perfil é estruturalmente válido? Se não, `ConfigError`.
(2) Está pronto para executar agora? Isto NÃO é exceção: vira dado (`issues`) para o agente
ler e corrigir. O resultado nunca contém valor de segredo nem conteúdo de variável de ambiente;
só apelidos, papéis e nomes de campo.
"""

from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from harness_dast.application.ports import Clock, ProfileRepository, ReferencedFile
from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.secret_ref import SecretRef
from harness_dast.domain.window import ExecutionWindow

_DAY_NAMES = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
_MINUTES_PER_DAY = 24 * 60
# Valores do modelo `products/_template` que a pessoa precisa trocar antes de executar.
_PLACEHOLDER_DOMAINS = (
    "exemplo.com.br",
    "exemplo.com",
    "example.com",
    "example.org",
    "example.net",
)
_PLACEHOLDER_REFERENCES = frozenset({"SEC-0000", "CHANGE_ME"})
_PLACEHOLDER_SECRET_PREFIXES = ("MEU_PRODUTO_", "CHANGE_ME")


class ReadinessIssue(BaseModel):
    """Pendência que impede a execução agora.

    Attributes:
        code: Identificador estável (ex.: `WINDOW_CLOSED`).
        field: Campo do perfil envolvido.
        message: O que está pendente e o que fazer.
    """

    model_config = ConfigDict(frozen=True)

    code: str
    field: str
    message: str


class AccountSummary(BaseModel):
    """Conta de teste vista pelo agente: apelido e papel, nunca credencial.

    Attributes:
        alias: Apelido da conta.
        role: Papel de negócio da conta.
    """

    model_config = ConfigDict(frozen=True)

    alias: str
    role: str


class WindowSummary(BaseModel):
    """Janela de execução em forma legível.

    Attributes:
        days: Dias de início da janela (`seg` a `dom`).
        start: Hora de abertura (`HH:MM`).
        end: Hora de fechamento (`HH:MM`).
        timezone: Fuso IANA.
        open_now: Se a janela está aberta no instante da verificação.
    """

    model_config = ConfigDict(frozen=True)

    days: tuple[str, ...]
    start: str
    end: str
    timezone: str
    open_now: bool


class LimitsSummary(BaseModel):
    """Limites de carga do perfil.

    Attributes:
        requests_per_second: Teto de requisições por segundo.
        max_duration_minutes: Duração máxima da execução.
        zap_threads_per_host: Threads do ZAP por host.
    """

    model_config = ConfigDict(frozen=True)

    requests_per_second: float
    max_duration_minutes: int
    zap_threads_per_host: int


class ProfileReport(BaseModel):
    """Resultado da validação de um perfil estruturalmente válido.

    Attributes:
        product: Nome do produto.
        environment_name: Nome do ambiente alvo.
        base_url_host: Host (sem esquema nem caminho) do ambiente alvo.
        allow_rules: Quantidade de regras em `scope.allow`.
        deny_paths: Caminhos negados em qualquer host.
        auth_type: Tipo de autenticação (`login_password` ou `api_key`).
        accounts: Contas por apelido e papel.
        windows: Janelas de execução.
        authorization_reference: Referência da autorização formal.
        authorization_valid_until: Último dia de validade (AAAA-MM-DD).
        authorization_valid_now: Se a autorização vale no instante da verificação.
        window_open_now: Se alguma janela está aberta no instante da verificação.
        limits: Limites de carga.
        cleanup_configured: Se o perfil declara hook de limpeza.
        checked_at: Instante da verificação (ISO 8601 com fuso).
        runnable: `True` quando não há nenhuma pendência em `issues`.
        issues: Pendências que impedem a execução agora.
    """

    model_config = ConfigDict(frozen=True)

    product: str
    environment_name: str
    base_url_host: str
    allow_rules: int
    deny_paths: tuple[str, ...]
    auth_type: str
    accounts: tuple[AccountSummary, ...]
    windows: tuple[WindowSummary, ...]
    authorization_reference: str
    authorization_valid_until: str
    authorization_valid_now: bool
    window_open_now: bool
    limits: LimitsSummary
    cleanup_configured: bool
    checked_at: str
    runnable: bool
    issues: tuple[ReadinessIssue, ...]


def _clock_text(minute: int) -> str:
    if minute == _MINUTES_PER_DAY:
        return "24:00"
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _summarize_window(window: ExecutionWindow, now: datetime) -> WindowSummary:
    return WindowSummary(
        days=tuple(_DAY_NAMES[day] for day in sorted(window.days)),
        start=_clock_text(window.start_minute),
        end=_clock_text(window.end_minute),
        timezone=window.timezone,
        open_now=window.is_open(now),
    )


def _is_placeholder_host(host: str) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in _PLACEHOLDER_DOMAINS)


def _placeholder_issues(profile: ProductProfile) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []
    if _is_placeholder_host(urlsplit(profile.environment.base_url).hostname or ""):
        issues.append(
            ReadinessIssue(
                code="PLACEHOLDER_HOST",
                field="environment.base_url",
                message="O host ainda é o do modelo (exemplo.com.br); informe o ambiente "
                "de teste real.",
            )
        )
    for index, rule in enumerate(profile.scope.allow):
        if _is_placeholder_host(rule.host):
            issues.append(
                ReadinessIssue(
                    code="PLACEHOLDER_HOST",
                    field=f"scope.allow[{index}].host",
                    message="O host da regra ainda é o do modelo; informe o host autorizado.",
                )
            )
    if profile.scope.authorization.reference.strip().upper() in _PLACEHOLDER_REFERENCES:
        issues.append(
            ReadinessIssue(
                code="PLACEHOLDER_AUTHORIZATION",
                field="scope.authorization.reference",
                message="A referência da autorização ainda é a do modelo; informe a real.",
            )
        )
    return issues


def _secret_refs(profile: ProductProfile) -> list[tuple[str, SecretRef]]:
    found: list[tuple[str, SecretRef]] = []
    for account in profile.auth.accounts:
        for name in type(account).model_fields:
            value = getattr(account, name)
            if isinstance(value, SecretRef):
                found.append((f"auth.accounts[{account.alias}].{name}", value))
    if profile.cleanup is not None:
        found.append(("cleanup.connection", profile.cleanup.connection))
    return found


def _secret_ref_issues(profile: ProductProfile) -> list[ReadinessIssue]:
    return [
        ReadinessIssue(
            code="PLACEHOLDER_SECRET_REF",
            field=field,
            message="A referência de segredo ainda tem nome de exemplo; "
            "aponte para a variável de ambiente real.",
        )
        for field, ref in _secret_refs(profile)
        if ref.env_name.startswith(_PLACEHOLDER_SECRET_PREFIXES)
    ]


def _authorization_issue(profile: ProductProfile, now: datetime) -> ReadinessIssue | None:
    try:
        profile.scope.authorization.ensure_valid(now)
    except ScopeViolation as error:
        return ReadinessIssue(
            code="AUTHORIZATION_EXPIRED",
            field="scope.authorization.valid_until",
            message=f"{error.message} {error.hint or ''}".strip(),
        )
    return None


def _window_issue(windows: tuple[WindowSummary, ...]) -> ReadinessIssue | None:
    if any(window.open_now for window in windows):
        return None
    return ReadinessIssue(
        code="WINDOW_CLOSED",
        field="scope.windows",
        message="Nenhuma janela de execução está aberta agora; execute dentro de "
        "scope.windows ou peça outra janela ao dono do produto.",
    )


def _file_issues(missing: tuple[ReferencedFile, ...]) -> list[ReadinessIssue]:
    return [
        ReadinessIssue(
            code="FILE_MISSING",
            field=item.field,
            message=f"O arquivo {item.path} ainda não existe na pasta do produto; crie-o.",
        )
        for item in missing
    ]


def _summarize_accounts(profile: ProductProfile) -> tuple[AccountSummary, ...]:
    return tuple(AccountSummary(alias=a.alias, role=a.role) for a in profile.auth.accounts)


class ValidateProfile:
    """Valida o perfil de um produto e informa se ele pode ser executado agora."""

    def __init__(self, profiles: ProfileRepository, clock: Clock) -> None:
        """Cria o caso de uso.

        Args:
            profiles: Fonte dos perfis.
            clock: Relógio usado para conferir janela e validade da autorização.
        """
        self._profiles = profiles
        self._clock = clock

    def execute(self, product: str) -> ProfileReport:
        """Valida o perfil e monta o relatório.

        Args:
            product: Nome (slug) do produto.

        Returns:
            O relatório. Perfil válido mas não executável NÃO é erro: `runnable` é `False`
            e `issues` diz o que falta.

        Raises:
            ConfigError: Se o perfil for estruturalmente inválido (veja
                `ProfileRepository.load`) ou o relógio devolver instante sem fuso.
        """
        profile = self._profiles.load(product)
        missing = self._profiles.missing_files(product, profile)
        now = self._clock.now()
        windows = tuple(_summarize_window(w, now) for w in profile.scope.windows)
        authorization_issue = _authorization_issue(profile, now)
        window_issue = _window_issue(windows)
        issues = (
            *_placeholder_issues(profile),
            *_secret_ref_issues(profile),
            *_file_issues(missing),
            *(i for i in (authorization_issue, window_issue) if i is not None),
        )
        limits = profile.limits
        return ProfileReport(
            product=profile.product,
            environment_name=profile.environment.name,
            base_url_host=urlsplit(profile.environment.base_url).hostname or "",
            allow_rules=len(profile.scope.allow),
            deny_paths=profile.scope.deny_paths,
            auth_type=profile.auth.type,
            accounts=_summarize_accounts(profile),
            windows=windows,
            authorization_reference=profile.scope.authorization.reference,
            authorization_valid_until=profile.scope.authorization.valid_until.isoformat(),
            authorization_valid_now=authorization_issue is None,
            window_open_now=window_issue is None,
            limits=LimitsSummary(
                requests_per_second=limits.requests_per_second,
                max_duration_minutes=limits.max_duration_minutes,
                zap_threads_per_host=limits.zap_threads_per_host,
            ),
            cleanup_configured=profile.cleanup is not None,
            checked_at=now.isoformat(),
            runnable=not issues,
            issues=issues,
        )

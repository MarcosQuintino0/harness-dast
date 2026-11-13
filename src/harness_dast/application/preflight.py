"""Caso de uso `preflight`: confere, sem varrer, se o ambiente está pronto para o `probe`.

Cada verificação vira um item `PreflightCheck` (dado, não exceção): autorização, janela,
segredos, ZAP, saúde do alvo, login e token CSRF de cada conta. Só perfil estruturalmente
inválido é erro (`ConfigError`). Falha de autorização ou janela tem tipo `scope` (a CLI sai
com 3); qualquer outra falha tem tipo `environment` (a CLI sai com 4).

Segredos: o relatório diz o apelido e o campo (`user_a.password`), nunca o valor. O NOME da
variável de ambiente só aparece em `operator_detail`, que é excluído do JSON e mostrado
apenas no texto para a pessoa que opera; o agente não precisa dele (o nome já está no
`target.yml` que ele mesmo escreveu).

Cada requisição enviada passa pelo `GuardedSender` e fica em `audit.jsonl` de uma pasta de
execução própria do preflight.
"""

from dataclasses import dataclass

from harness_dast.application.account_session import AccountSession
from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.ports import (
    Clock,
    EntropySource,
    ProfileRepository,
    RunStore,
    SecretProvider,
    SecretVault,
    Sleeper,
    TargetClient,
    ZapControl,
)
from harness_dast.application.preflight_checks import (
    failure_check,
    not_run_checks,
    run_step,
    scope_check,
)
from harness_dast.application.preflight_report import PreflightCheck, PreflightReport
from harness_dast.application.run_support import (
    AuditTrail,
    GuardedSender,
    RateLimiter,
    RunGate,
)
from harness_dast.domain.auth import Account
from harness_dast.domain.errors import ExternalToolError, ScopeViolation
from harness_dast.domain.probe_result import ArtifactHashes, RunManifest
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.request_encoding import build_get_request
from harness_dast.domain.run import RunId
from harness_dast.domain.window import ensure_any_window_open
from harness_dast.domain.zap_scope import TESTED_ZAP_PREFIX

HEALTH_OPERATION_ID = "preflight.health"


@dataclass
class _Network:
    dispatcher: OperationDispatcher
    run_id: RunId


class Preflight:
    """Executa as verificações (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        secrets: SecretProvider,
        vault: SecretVault,
        client: TargetClient,
        zap: ZapControl,
        store: RunStore,
        clock: Clock,
        sleeper: Sleeper,
        entropy: EntropySource,
        harness_version: str,
    ) -> None:
        """Cria o caso de uso com as portas de que precisa."""
        self._profiles = profiles
        self._secrets = secrets
        self._vault = vault
        self._client = client
        self._zap = zap
        self._store = store
        self._clock = clock
        self._sleeper = sleeper
        self._entropy = entropy
        self._harness_version = harness_version

    def execute(self, product: str) -> PreflightReport:
        """Roda as verificações.

        Args:
            product: Nome do produto.

        Returns:
            O relatório. Falha de verificação NÃO levanta: está em `checks` e `ready`.

        Raises:
            ConfigError: Perfil estruturalmente inválido.
        """
        profile = self._profiles.load(product)
        scope_checks = self._scope_checks(profile)
        if not all(check.ok for check in scope_checks):
            return PreflightReport(
                product=product, ready=False, checks=(*scope_checks, *not_run_checks())
            )
        zap_check, zap_version = self._zap_check()
        network = self._open_network(profile)
        sessions = [self._session(profile, account, network) for account in profile.auth.accounts]
        secret_checks = [self._secret_check(session) for session in sessions]
        checks = [
            *scope_checks,
            *secret_checks,
            zap_check,
            self._health_check(profile, network, zap_ok=zap_check.ok),
        ]
        for session, secret_check in zip(sessions, secret_checks, strict=True):
            checks.extend(self._account_checks(session, secrets_ok=secret_check.ok))
        ready = all(check.ok for check in checks)
        self._write_manifest(profile, network, "ready" if ready else "not_ready")
        return PreflightReport(
            product=product,
            ready=ready,
            checks=tuple(checks),
            run_id=network.run_id.value,
            zap_version=zap_version,
        )

    def _scope_checks(self, profile: ProductProfile) -> tuple[PreflightCheck, ...]:
        authorization = scope_check(
            "authorization",
            lambda: profile.scope.authorization.ensure_valid(self._clock.now()),
            "A autorização formal vale agora.",
        )
        window = scope_check(
            "window",
            lambda: ensure_any_window_open(profile.scope.windows, self._clock.now()),
            "Há uma janela de execução aberta agora.",
        )
        return (authorization, window)

    def _zap_check(self) -> tuple[PreflightCheck, str | None]:
        try:
            version = self._zap.version()
        except ExternalToolError as error:
            detail = f"O ZAP não respondeu: {error.message} {error.hint or ''}".strip()
            return PreflightCheck(id="zap", ok=False, detail=detail), None
        note = ""
        if not version.startswith(TESTED_ZAP_PREFIX):
            note = f" Versão diferente da validada ({TESTED_ZAP_PREFIX}x); confira o comportamento."
        detail = f"ZAP {version} respondeu à API.{note}"
        return PreflightCheck(id="zap", ok=True, detail=detail), version

    def _open_network(self, profile: ProductProfile) -> _Network:
        started = self._clock.now()
        run_id = RunId.create(
            started_at=started, product=profile.product, suffix=self._entropy.hex_suffix()
        )
        sender = GuardedSender(
            guard=profile.guard(),
            client=self._client,
            gate=RunGate(profile, self._clock, started),
            limiter=RateLimiter(profile.limits.requests_per_second, self._clock, self._sleeper),
            trail=AuditTrail(self._store, run_id.value, self._clock),
            clock=self._clock,
        )
        return _Network(OperationDispatcher(sender, self._sleeper, profile.auth.csrf), run_id)

    def _session(
        self, profile: ProductProfile, account: Account, network: _Network
    ) -> AccountSession:
        return AccountSession(
            account=account,
            auth=profile.auth,
            base_url=profile.environment.base_url,
            secrets=self._secrets,
            vault=self._vault,
            client=self._client,
            dispatcher=network.dispatcher,
        )

    def _secret_check(self, session: AccountSession) -> PreflightCheck:
        resolved = [
            (name, ref, self._secrets.resolve(ref)) for name, ref in session.secret_fields()
        ]
        for _, _, value in resolved:
            if value:
                self._vault.register(value)
        missing = [(name, ref) for name, ref, value in resolved if not value]
        check_id = f"secrets:{session.alias}"
        if not missing:
            return PreflightCheck(
                id=check_id, ok=True, detail="Todos os segredos da conta estão definidos."
            )
        fields = ", ".join(f"{session.alias}.{name}" for name, _ in missing)
        names = ", ".join(ref.env_name for _, ref in missing)
        return PreflightCheck(
            id=check_id,
            ok=False,
            detail=f"Segredo ausente ou vazio: {fields}. Defina a variável indicada em secret_ref.",
            operator_detail=f"Variáveis de ambiente a definir: {names}.",
        )

    def _health_check(
        self, profile: ProductProfile, network: _Network, *, zap_ok: bool
    ) -> PreflightCheck:
        if not zap_ok:
            return PreflightCheck(
                id="target_health",
                ok=False,
                detail="Não executado: o ZAP, por onde o probe envia, não respondeu.",
            )
        request = build_get_request(
            base_url=profile.environment.base_url,
            path=profile.probe.health_path or "/",
            operation_id=HEALTH_OPERATION_ID,
            account=None,
            route="zap",
        )
        try:
            sent = network.dispatcher.send(request, None)
        except ScopeViolation as error:
            # Um GET de saúde fora do escopo é problema do perfil, não de janela ou autorização.
            detail = f"{error.message} Declare probe.health_path em target.yml com um GET leve."
            return PreflightCheck(id="target_health", ok=False, detail=detail)
        except ExternalToolError as error:
            return failure_check("target_health", error)
        if sent.response is None:
            reason = sent.transport_error.message if sent.transport_error else "sem resposta"
            return PreflightCheck(
                id="target_health", ok=False, detail=f"O alvo não respondeu: {reason}"
            )
        status = sent.response.status
        if status >= 500:
            detail = f"O alvo respondeu HTTP {status} (erro do servidor)."
            return PreflightCheck(id="target_health", ok=False, detail=detail)
        return PreflightCheck(
            id="target_health", ok=True, detail=f"O alvo respondeu HTTP {status}."
        )

    def _account_checks(self, session: AccountSession, *, secrets_ok: bool) -> list[PreflightCheck]:
        if not secrets_ok:
            return (
                [
                    PreflightCheck(
                        id=f"login:{session.alias}",
                        ok=False,
                        detail="Não executado: há segredos ausentes nesta conta.",
                    )
                ]
                if session.uses_login
                else []
            )
        checks: list[PreflightCheck] = []
        if session.csrf is not None:
            checks.append(
                run_step(f"csrf:{session.alias}", session.fetch_csrf, "Token CSRF obtido.")
            )

        def login() -> None:
            session.resolve_secrets()
            session.login()

        if session.uses_login:
            checks.append(
                run_step(f"login:{session.alias}", login, "Login realizado; token obtido.")
            )
        return checks

    def _write_manifest(self, profile: ProductProfile, network: _Network, status: str) -> None:
        now = self._clock.now().isoformat()
        manifest = RunManifest(
            run_id=network.run_id.value,
            command="preflight",
            product=profile.product,
            harness_version=self._harness_version,
            hashes=ArtifactHashes(),
            limits=profile.limits,
            seed=0,
            accounts=tuple(a.alias for a in profile.auth.accounts),
            started_at=now,
            finished_at=now,
            status=status,
        )
        self._store.write_manifest(network.run_id.value, manifest)

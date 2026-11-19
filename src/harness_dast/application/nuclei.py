"""Caso de uso `nuclei`: o segundo motor, atrás da segunda cerca (ADR 0122).

Fluxo: confere perfil, janela, autorização, a imagem e a política publicada na
`scope-proxy-nuclei`; pede ao domínio os modelos (`select_templates`) e os argumentos
(`build_nuclei_args`); com login, obtém o token pelo caminho que já existe (`AccountSession`, que
consome o `login_budget`) e grava o arquivo `-sf`; roda o contêiner; lê o JSONL bruto pela
projeção por lista branca, descarta o bruto e grava só o resultado limpo em `nuclei.json`.

O que garante:
- O caso de uso não decide escopo nem gravidade: só chama o domínio. Recusa rodar sem
  `extra_checks.nuclei`, sem a imagem ou sem a política do perfil publicada na segunda cerca.
- O token nunca vai para argumento, ambiente nem log: só existe no arquivo `-sf`, que é apagado
  num `finally` (sucesso, falha, prazo e `KILL`). O JSONL bruto também é sempre descartado.
- O `KILL`, a janela e o prazo são consultados durante a execução; ao dispararem, o contêiner é
  derrubado e a saída parcial vira `nuclei.json` com o motivo.
O que não faz: não envia HTTP ao alvo além do login (que passa pelo `GuardedSender`), não escolhe
a cerca e não liga nenhuma permissão.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import structlog

from harness_dast.application.account_session import AccountSession, TokenCache
from harness_dast.application.common_ports import (
    Clock,
    KillSwitch,
    ProfileRepository,
    RunStore,
    SecretProvider,
    SecretVault,
    Sleeper,
    TargetClient,
)
from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.login_budget import LoginBudget
from harness_dast.application.nuclei_ports import (
    SECRETS_MOUNT,
    TEMPLATES_MOUNT,
    NucleiArtifacts,
    NucleiEngine,
    NucleiFence,
    NucleiImages,
    NucleiOutputReader,
    NucleiParsedOutput,
    NucleiRunResult,
    NucleiRunSpec,
    NucleiSecret,
    NucleiSecretsWriter,
)
from harness_dast.application.run_support import (
    AuditTrail,
    DeadlineReached,
    GuardedSender,
    KillSwitchEngaged,
    RateLimiter,
    RunGate,
)
from harness_dast.domain.errors import ConfigError, ExternalToolError, ScopeViolation
from harness_dast.domain.nuclei_command import NucleiCommandInput, build_nuclei_args
from harness_dast.domain.nuclei_findings import (
    NucleiFinding,
    TechnologyDetected,
    classify,
    group_findings,
)
from harness_dast.domain.nuclei_manifest import (
    NucleiManifest,
    NucleiPermissions,
    NucleiSelection,
    select_templates,
)
from harness_dast.domain.nuclei_permissions import nuclei_permissions
from harness_dast.domain.nuclei_result import NucleiResult, NucleiStatus
from harness_dast.domain.nuclei_scope import nuclei_scope_for
from harness_dast.domain.nuclei_version import NUCLEI_VERSION, TEMPLATES_VERSION
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run_ref import require_run_id

__all__ = ["NUCLEI_CONCURRENCY", "NUCLEI_PROXY_URL", "Nuclei", "NucleiRequest"]

_log = structlog.get_logger()

NUCLEI_PROXY_URL = "http://scope-proxy-nuclei:3128"
"""Endereço da segunda cerca na rede interna (`compose.yaml`)."""
NUCLEI_CONCURRENCY = 5
"""Teto de modelos em paralelo (`-c`); abaixo disso quando o ritmo do perfil é menor."""
_DEFAULT_PORTS = {"http": 80, "https": 443}
_AUTH_HEADER_FALLBACK = "Authorization"


@dataclass(frozen=True)
class NucleiRequest:
    """Pedido de um `nuclei`.

    Attributes:
        product: Nome do produto.
        run_id: Execução cujo diretório recebe `nuclei.json` (o mesmo do `probe`).
        account: Apelido da conta do login (`extra_checks.nuclei_login`); `None` usa a primeira
            do perfil. Sem a permissão de login, a conta é ignorada.
        deadline: Prazo absoluto herdado do `run` encadeado; só reduz o prazo do perfil.
        only_templates: Caminhos de modelos (como no `template_path` dos achados) aos quais a
            execução se limita, no reteste. Só reduz: o que não passa pelas permissões do
            perfil continua de fora, e vazio roda todos os escolhidos.
        persist: Se o resultado vira `nuclei.json` na pasta da execução. O `confirm` passa
            `False`: a reprodução de um achado não pode sobrescrever o `nuclei.json` original.
    """

    product: str
    run_id: str
    account: str | None = None
    deadline: datetime | None = None
    only_templates: tuple[str, ...] = ()
    persist: bool = True


@dataclass(frozen=True)
class _Plan:
    """O que ficou decidido antes de rodar."""

    profile: ProductProfile
    run_id: str
    started: datetime
    deadline: datetime
    permissions: NucleiPermissions
    selection: NucleiSelection
    gate: RunGate


class _Stop:
    """Pergunta ao portão (KILL, janela, prazo) e lembra o motivo da primeira parada."""

    def __init__(self, gate: RunGate) -> None:
        self._gate = gate
        self.reason: ScopeViolation | None = None

    def __call__(self) -> bool:
        try:
            self._gate.check()
        except ScopeViolation as error:
            self.reason = error
            return True
        return False

    def status(self) -> tuple[NucleiStatus, str | None]:
        """Estado final: o motivo da parada, ou `completed` sem parada."""
        reason = self.reason
        if reason is None:
            return "completed", None
        if isinstance(reason, KillSwitchEngaged):
            return "stopped_kill", reason.message
        if isinstance(reason, DeadlineReached):
            return "stopped_deadline", reason.message
        return "stopped_window", reason.message


class Nuclei:
    """Orquestra o `nuclei` (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        load_manifest: Callable[[], NucleiManifest],
        images: NucleiImages,
        fence: NucleiFence,
        engine: NucleiEngine,
        secrets_writer: NucleiSecretsWriter,
        reader: NucleiOutputReader,
        artifacts: NucleiArtifacts,
        secrets: SecretProvider,
        vault: SecretVault,
        client: TargetClient,
        store: RunStore,
        clock: Clock,
        sleeper: Sleeper,
        token_cache: TokenCache | None = None,
        login_budget: LoginBudget | None = None,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        """Cria o caso de uso com todas as portas de que precisa.

        `token_cache`, `login_budget` e `kill_switch` são compartilhados com as outras etapas
        quando o `run` encadeia tudo num processo só (cada conta faz login uma vez).
        """
        self._profiles = profiles
        self._load_manifest = load_manifest
        self._images = images
        self._fence = fence
        self._engine = engine
        self._secrets_writer = secrets_writer
        self._reader = reader
        self._artifacts = artifacts
        self._secrets = secrets
        self._vault = vault
        self._client = client
        self._store = store
        self._clock = clock
        self._sleeper = sleeper
        self._token_cache = token_cache
        self._login_budget = login_budget
        self._kill_switch = kill_switch

    def execute(self, request: NucleiRequest) -> NucleiResult:
        """Executa o `nuclei` e grava `nuclei.json` (salvo com `persist=False`).

        Args:
            request: Pedido.

        Returns:
            O resultado limpo. Com parada antecipada (KILL, janela, prazo do perfil) o
            resultado parcial é devolvido e gravado, com o motivo em `status`.

        Raises:
            ConfigError: Perfil ou execução inválidos; `extra_checks.nuclei` desligado; imagem
                ausente; política da segunda cerca ausente ou diferente da do perfil; nenhum
                modelo escolhido.
            ScopeViolation: Autorização vencida, janela fechada, `KILL` ou prazo esgotado antes
                de começar.
            PreflightError: O login da conta foi recusado.
            ExternalToolError: Docker, prazo do contêiner ou saída do Nuclei com erro.
        """
        plan = self._plan(request)
        stop = _Stop(plan.gate)
        run, alias = self._run_engine(request, plan, stop)
        parsed = self._read_and_discard(run)
        if run.exit_code != 0 and not run.killed:
            raise ExternalToolError(
                f"O Nuclei terminou com erro (código {run.exit_code}); a saída foi descartada.",
                hint="Rode de novo; se repetir, confira a imagem do Nuclei e a política da cerca.",
            )
        result = self._result(plan, run, parsed, alias, stop)
        if request.persist:
            self._artifacts.write_nuclei(plan.run_id, result)
        _log.info(
            "nuclei.done",
            status=result.status,
            findings=len(result.findings),
            malformed=result.malformed_lines,
        )
        return result

    def _plan(self, request: NucleiRequest) -> _Plan:
        started = self._clock.now()
        profile = self._profiles.load(request.product)
        profile.ensure_runnable(started)
        run_id = require_run_id(request.run_id)
        permissions = self._check_allowed(profile)
        gate = RunGate(profile, self._clock, started, self._kill_switch, deadline=request.deadline)
        gate.check()
        selection = _restrict(
            select_templates(self._load_manifest(), permissions), request.only_templates
        )
        if not selection.paths:
            raise ConfigError(
                "Nenhum modelo do Nuclei passa pelas permissões deste perfil.",
                hint="Confira extra_checks.nuclei e as permissões de escrita na carta.",
            )
        deadline = started + timedelta(minutes=profile.limits.max_duration_minutes)
        if request.deadline is not None:
            deadline = min(deadline, request.deadline)
        return _Plan(profile, run_id, started, deadline, permissions, selection, gate)

    def _check_allowed(self, profile: ProductProfile) -> NucleiPermissions:
        if not profile.extra_checks.nuclei:
            raise ConfigError(
                "O Nuclei não está autorizado neste perfil (extra_checks.nuclei).",
                hint="Só a carta, a resposta da pessoa ou o pedido mínimo ligam o Nuclei; "
                "peça a uma pessoa que rode hdast init --from-letter e hdast setup.",
            )
        self._images.require_nuclei()
        wanted = nuclei_scope_for(profile)
        if wanted is None or self._fence.published_scope() != wanted:
            raise ConfigError(
                "A segunda cerca (scope-proxy-nuclei) não tem publicada a política deste perfil.",
                hint="Suba a pilha de novo com hdast stack up para publicar a política do Nuclei.",
            )
        granted = nuclei_permissions(profile)
        return NucleiPermissions(writes=granted.writes, delete=granted.delete, login=granted.login)

    def _run_engine(
        self, request: NucleiRequest, plan: _Plan, stop: _Stop
    ) -> tuple[NucleiRunResult, str | None]:
        """Obtém o token (se houver login), grava o `-sf` e roda; apaga o `-sf` sempre."""
        secret, alias = self._login_secret(request, plan)
        secret_path = self._secrets_writer.write(secret) if secret is not None else None
        try:
            spec = self._spec(plan, secret_path)
            return self._engine.run(spec, stop), alias
        finally:
            if secret_path is not None:
                self._secrets_writer.remove(secret_path)

    def _spec(self, plan: _Plan, secret_path: Path | None) -> NucleiRunSpec:
        profile = plan.profile
        # Inteiro para baixo, no mínimo 1: o `-rl` é inteiro e a cerca impõe o ritmo exato.
        rate = max(1, int(profile.limits.requests_per_second))
        args = build_nuclei_args(
            NucleiCommandInput(
                target_url=profile.environment.base_url,
                proxy_url=NUCLEI_PROXY_URL,
                requests_per_second=rate,
                concurrency=min(NUCLEI_CONCURRENCY, rate),
                templates_list_path=TEMPLATES_MOUNT,
                secret_file_path=SECRETS_MOUNT if secret_path is not None else None,
            )
        )
        remaining = (plan.deadline - self._clock.now()).total_seconds()
        digest = hashlib.sha256(plan.run_id.encode("utf-8")).hexdigest()[:16]
        return NucleiRunSpec(
            args=args,
            templates=plan.selection.paths,
            secrets_path=secret_path,
            timeout_seconds=max(1, int(remaining)),
            container_name=f"hdast-nuclei-{digest}",
        )

    def _login_secret(
        self, request: NucleiRequest, plan: _Plan
    ) -> tuple[NucleiSecret | None, str | None]:
        """Token da conta como segredo do `-sf`; `(None, None)` sem a permissão de login."""
        if not plan.permissions.login:
            return None, None
        profile = plan.profile
        account = profile.select_account(request.account)
        sender = GuardedSender(
            guard=profile.guard(),
            client=self._client,
            gate=plan.gate,
            limiter=RateLimiter(profile.limits.requests_per_second, self._clock, self._sleeper),
            trail=AuditTrail(
                self._store, plan.run_id, self._clock, sequence=self._last_seq(plan.run_id)
            ),
            clock=self._clock,
        )
        budget = self._login_budget or LoginBudget(profile.login_limit, self._clock, self._sleeper)
        dispatcher = OperationDispatcher(
            sender,
            self._sleeper,
            profile.auth.csrf,
            login_budget=budget,
            login_path=profile.login_path,
            token_expired=profile.token_expired_signal,
            error_codes=profile.probe.error_codes,
        )
        session = AccountSession(
            account=account,
            auth=profile.auth,
            base_url=profile.environment.base_url,
            secrets=self._secrets,
            vault=self._vault,
            client=self._client,
            dispatcher=dispatcher,
            token_cache=self._token_cache,
        )
        session.open()
        credential = session.credential()
        if credential is None:
            return None, None
        secret = NucleiSecret(
            domains=_domains(profile.environment.base_url),
            header=credential.header or _AUTH_HEADER_FALLBACK,
            value=credential.header_value(),
        )
        return secret, account.alias

    def _last_seq(self, run_id: str) -> int:
        return max((entry.seq for entry in self._artifacts.read_audit(run_id)), default=0)

    def _read_and_discard(self, run: NucleiRunResult) -> NucleiParsedOutput:
        try:
            return self._reader.read(run.raw_jsonl)
        finally:
            self._engine.discard(run.raw_jsonl)

    def _result(
        self,
        plan: _Plan,
        run: NucleiRunResult,
        parsed: NucleiParsedOutput,
        alias: str | None,
        stop: _Stop,
    ) -> NucleiResult:
        classified = [classify(record) for record in parsed.records]
        findings = group_findings(item for item in classified if isinstance(item, NucleiFinding))
        technologies = tuple(
            dict.fromkeys(item for item in classified if isinstance(item, TechnologyDetected))
        )
        status, message = stop.status()
        if run.killed and status == "completed":
            status, message = "stopped_kill", "O contêiner do Nuclei foi derrubado."
        return NucleiResult(
            run_id=plan.run_id,
            product=plan.profile.product,
            status=status,
            stop_message=message,
            started_at=plan.started.isoformat(),
            finished_at=self._clock.now().isoformat(),
            nuclei_version=NUCLEI_VERSION,
            templates_version=TEMPLATES_VERSION,
            logged_in=alias is not None,
            account=alias,
            templates_selected=len(plan.selection.paths),
            excluded=plan.selection.excluded,
            exit_code=run.exit_code,
            malformed_lines=parsed.malformed,
            findings=findings,
            technologies=technologies,
        )


def _restrict(selection: NucleiSelection, only: tuple[str, ...]) -> NucleiSelection:
    """Reduz a escolha aos modelos pedidos (reteste); nunca acrescenta um que o domínio vetou."""
    if not only:
        return selection
    wanted = frozenset(only)
    return selection.model_copy(
        update={"paths": tuple(path for path in selection.paths if path in wanted)}
    )


def _domains(base_url: str) -> tuple[str, ...]:
    """Host e host:porta da origem aprovada: o cabeçalho de login vale só para ela."""
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    port = parts.port or _DEFAULT_PORTS.get(parts.scheme, 0)
    return (host, f"{host}:{port}")

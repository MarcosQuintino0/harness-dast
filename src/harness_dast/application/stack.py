"""Casos de uso da pilha gerenciada: `stack up`, `stack status`, `stack down` e `stop`.

`up` carrega o perfil, confere autorização e janela, gera a política do proxy a partir do
perfil (nunca mais larga), grava o estado e sobe os contêineres recriando-os: o proxy só lê a
política na partida, então cada `up` começa de um ZAP, um proxy e um alvo novos. `down`
derruba tudo o que `up` subiu. `stop` é a trava de emergência: cria o `KILL` do proxy ANTES de
falar com o ZAP, para funcionar mesmo com o ZAP fora do ar.

O estado (chave do ZAP, senhas descartáveis do alvo) fica no `StackStateStore`, fora do
repositório e de `runs/`. Este módulo não imprime nem devolve segredos.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from harness_dast.application.common_ports import (
    Clock,
    EntropySource,
    ProfileRepository,
    SpecLoader,
    StackStateStore,
)
from harness_dast.application.lab_accounts import account_paths
from harness_dast.application.lab_targets import (
    CLINICA_PILOTO,
    CRAPI,
    CRAPI_OAST_FILE,
    CRAPI_PROJECT,
    OAST_GATEWAY_FILE,
    OAST_GATEWAY_SERVICE,
    PILOT_API_PORT,
    PILOT_MANAGEMENT_PORT,
    PILOT_ORACLE_ENV_FIXED,
    PILOT_ORACLE_FILE,
    PILOT_ORACLE_PROFILE,
    PILOT_PROJECT,
    LabTarget,
    lab_target_for,
)
from harness_dast.application.scan_ports import RunningScans
from harness_dast.application.stack_freshness import StackFreshnessCheck
from harness_dast.application.stack_images import (
    NUCLEI_RECOVERY,
    NUCLEI_SERVICE,
    NUCLEI_UNAVAILABLE,
    OWN_SERVICES,
    StackImages,
    use_local_build,
)
from harness_dast.application.stack_lock import StackLockService
from harness_dast.application.stack_models import (
    ComposeProject,
    ServiceStatus,
    StackProjectSuffix,
    StackReport,
    StackState,
    StopReport,
)
from harness_dast.application.stack_ports import (
    ComposeRunner,
    LabAccountProvisioner,
    ProxyPolicyStore,
    RandomSource,
    ZapScanStopper,
)
from harness_dast.domain.errors import ConfigError, ExternalToolError
from harness_dast.domain.nuclei_scope import nuclei_scope_for
from harness_dast.domain.oast_bridge import should_mount_oast_bridge
from harness_dast.domain.proxy_deadline import compute_policy_deadline
from harness_dast.domain.run import RunId
from harness_dast.domain.scan_result import ScanProgress
from harness_dast.domain.stack_binding import stale_error

MAIN_PROJECT = "hdast"
BASE_SERVICES = ("zap", "zap-gateway", "scope-proxy", "scope-proxy-nuclei", "proxy-gateway")
DEFAULT_ZAP_PORT = "8080"
DEFAULT_PROXY_PORT = "3128"
DEFAULT_UP_TIMEOUT_SECONDS = 300
DOWN_TIMEOUT_SECONDS = 120
KEY_ENV = "HDAST_ZAP_API_KEY"
POLICY_DIR_ENV = "HDAST_SCOPE_POLICY_DIR"
AUDIT_DIR_ENV = "HDAST_AUDIT_DIR"
NUCLEI_POLICY_DIR_ENV = "HDAST_NUCLEI_POLICY_DIR"
NUCLEI_AUDIT_DIR_ENV = "HDAST_NUCLEI_AUDIT_DIR"
_KEY_BYTES = 24
_PASSWORD_BYTES = 12
_USERNAME_BYTES = 3
_PLACEHOLDER = "unused"
_FRESH_SECONDS = 120
"""Andamento mais velho que isto é de um processo que morreu sem terminar."""


@dataclass(frozen=True)
class StackUpRequest:
    """Pedido de `stack up`.

    Attributes:
        product: Produto cujo perfil define a política.
        vulnerable: Modo vulnerável (`True`) ou seguro (`False`) do alvo; `None` mantém o padrão.
        token_ttl_seconds: Vida do token do alvo; `None` mantém o padrão.
        build: Reconstruir as imagens locais antes de subir.
        timeout_seconds: Prazo para os contêineres ficarem saudáveis.
        oracle: Sobe também o Oracle Free do piloto (perfil `oracle`), com a porta do banco em
            127.0.0.1 para a limpeza; só vale para a Clínica Piloto.
    """

    product: str
    vulnerable: bool | None = None
    token_ttl_seconds: int | None = None
    build: bool = False
    timeout_seconds: int = DEFAULT_UP_TIMEOUT_SECONDS
    oracle: bool = False


class StackManager:
    """Sobe, consulta e derruba a pilha, e aciona a trava de emergência."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        clock: Clock,
        entropy: EntropySource,
        random: RandomSource,
        policies: ProxyPolicyStore,
        compose: ComposeRunner,
        images: StackImages,
        states: StackStateStore,
        environ: Mapping[str, str],
        repo_root: Path,
        running_scans: RunningScans | None = None,
        locks: StackLockService | None = None,
        proxy_env: Callable[[str], Mapping[str, str]] | None = None,
        freshness: StackFreshnessCheck | None = None,
        crapi_accounts: LabAccountProvisioner | None = None,
        specs: SpecLoader | None = None,
    ) -> None:
        """Cria o caso de uso.

        Args:
            profiles: Fonte dos perfis.
            clock: Relógio injetado.
            entropy: Sufixo do identificador da pilha.
            random: Segredos descartáveis.
            policies: Gravação da política e da trava.
            compose: Docker Compose.
            images: Seleção e conferência das imagens próprias da pilha.
            states: Estado persistido.
            environ: Ambiente da CLI (chave do ZAP, portas, credenciais já definidas).
            repo_root: Raiz dos arquivos do Compose.
            running_scans: Leitura do andamento das varreduras, para o `stop` dizer o que parou.
            locks: Trava da pilha, para o `status` dizer quem a ocupa (ADR 0035).
            proxy_env: Montagens e identidade do proxy gerenciado para o produto.
            freshness: Conferência do frescor da pilha, para o `status` (ADR 0081).
            crapi_accounts: Cadastro das contas sintéticas do crAPI.
            specs: Leitor do OpenAPI do perfil, para preparar contas de laboratório.
        """
        self._profiles = profiles
        self._clock = clock
        self._entropy = entropy
        self._random = random
        self._policies = policies
        self._compose = compose
        self._images = images
        self._states = states
        self._environ = environ
        self._root = repo_root
        self._running_scans = running_scans
        self._locks = locks
        self._proxy_env = proxy_env
        self._freshness = freshness
        self._crapi_accounts = crapi_accounts
        self._specs = specs

    def up(self, request: StackUpRequest) -> StackReport:
        """Sobe a pilha para o produto.

        Raises:
            ConfigError: Perfil ou imagens inválidas, build proibido ou falha de gravação.
            ScopeViolation: Autorização vencida ou janela fechada.
            ExternalToolError: Docker indisponível ou falha ao subir.
        """
        build_local = request.build or use_local_build(self._environ)
        references = self._images.references(OWN_SERVICES, local=build_local)
        now = self._clock.now()
        profile = self._profiles.load(request.product)
        profile.ensure_runnable(now)
        target = lab_target_for(profile.environment.base_url)
        if target is CRAPI and request.vulnerable is False:
            raise ConfigError(
                "O crAPI não tem modo seguro.", hint="Use o modo vulnerável no laboratório."
            )
        if target is CRAPI and request.token_ttl_seconds is not None:
            raise ConfigError(
                "O crAPI não oferece ajuste de token nesta pilha.",
                hint="Retire a opção de duração do token.",
            )
        if target is CRAPI and self._crapi_accounts is None:
            raise ConfigError(
                "Cadastro de contas do crAPI indisponível.", hint="Confira a montagem da CLI."
            )
        paths = None
        if target is CRAPI:
            if self._specs is None:
                raise ConfigError(
                    "Leitor do OpenAPI indisponível.", hint="Confira a montagem da CLI."
                )
            paths = account_paths(self._specs.load(profile.product, profile))
        notes: list[str] = []
        if profile.extra_checks.nuclei:
            if self._images.nuclei_available():
                references = {
                    **references,
                    **self._images.references((NUCLEI_SERVICE,), local=build_local),
                }
            else:
                notes.append(f"{NUCLEI_UNAVAILABLE} {NUCLEI_RECOVERY}")
        suffix = _project_suffix(self._environ)
        oracle = self._oracle_requested(request, target)
        bridge = should_mount_oast_bridge(profile.environment.base_url, requested=profile.scan.oast)
        projects = self._projects(target, oracle=oracle, suffix=suffix, bridge=bridge)
        proxy_env = self._proxy_env(profile.product) if self._proxy_env is not None else {}
        image_env = self._prepare_images(projects[0], references, local=build_local)
        warnings = self._tear_down_previous()
        run_id = RunId.create(
            started_at=now, product=profile.product, suffix=self._entropy.hex_suffix()
        )
        not_after = compute_policy_deadline(profile, now)
        directories = self._states.directories_for(run_id.value)
        policy_file = self._policies.publish(profile, run_id, not_after, directories.policy_dir)
        # A segunda cerca sempre recebe uma política: a do Nuclei, ou a que nega tudo.
        self._policies.publish_nuclei(
            profile, run_id, not_after, directories.nuclei_policy_dir, nuclei_scope_for(profile)
        )
        zap_port = self._environ.get("HDAST_ZAP_HOST_PORT", DEFAULT_ZAP_PORT)
        proxy_port = self._environ.get("HDAST_PROXY_HOST_PORT", DEFAULT_PROXY_PORT)
        state = StackState(
            product=profile.product,
            run_id=run_id.value,
            started_at=now.isoformat(),
            not_after=not_after.isoformat(),
            lab_target=target.name if target else None,
            zap_api_key=self._environ.get(KEY_ENV) or self._random.token_hex(_KEY_BYTES),
            zap_url=f"http://127.0.0.1:{zap_port}",
            auth_proxy_url=f"http://127.0.0.1:{proxy_port}",
            policy_dir=directories.policy_dir,
            audit_dir=directories.audit_dir,
            nuclei_policy_dir=directories.nuclei_policy_dir,
            nuclei_audit_dir=directories.nuclei_audit_dir,
            projects=projects,
            target_env=self._credentials(target, oracle=oracle),
            target_urls=_target_urls(target),
        )
        # Gravado ANTES de subir: se a subida falhar no meio, `stack down` sabe o que derrubar.
        self._states.save(state)
        self._start_projects(
            state, request, target, (zap_port, proxy_port), {**proxy_env, **image_env}, build_local
        )
        if target is CRAPI and self._crapi_accounts is not None and paths is not None:
            self._crapi_accounts.provision(
                {
                    **state.target_env,
                    **{
                        name: self._environ[name]
                        for name in CRAPI.credential_env
                        if self._environ.get(name)
                    },
                },
                paths,
            )
        report = self._report(state, policy_file=policy_file)
        return report.model_copy(update={"warnings": (*warnings, *notes)})

    def _prepare_images(
        self, project: ComposeProject, references: Mapping[str, str], *, local: bool
    ) -> dict[str, str]:
        env = self._images.compose_env(references)
        if local:
            # O Compose interpola a chave mesmo em `build`, que não inicia nenhum serviço.
            services = tuple(s for s in (*OWN_SERVICES, NUCLEI_SERVICE) if s in references)
            self._compose.build(project, {**env, KEY_ENV: _PLACEHOLDER}, services)
        self._images.require_ready(references)
        return env

    def _start_projects(
        self,
        state: StackState,
        request: StackUpRequest,
        target: LabTarget | None,
        ports: tuple[str, str],
        main_env: dict[str, str],
        build_local: bool,
    ) -> None:
        # Sem opção explícita, o Compose ainda pode construir a imagem do alvo anexado.
        reuse_target_image = self._environ.get("HDAST_STACK_BUILD") == "reuse"
        attached_build = build_local if build_local or reuse_target_image else None
        for index, project in enumerate(state.projects):
            env = self._up_env(project, state, _target_options(target, request), ports)
            if index == 0:
                env.update(main_env)
            self._compose.up(
                project,
                env,
                # As imagens próprias já passaram pela conferência.
                build=attached_build if index else False,
                timeout_seconds=request.timeout_seconds,
            )

    def status(self) -> StackReport:
        """Descreve a pilha gerenciada (ou diz que não há).

        Raises:
            ConfigError: Arquivo de estado ou de trava inválido.
            ExternalToolError: Docker indisponível.
        """
        state = self._states.load()
        lock = self._locks.inspect() if self._locks is not None else None
        if state is None:
            return StackReport(managed=False, state_file=str(self._states.location()), lock=lock)
        report = self._report(state, policy_file=state.policy_dir / "policy.json")
        update: dict[str, object] = {"lock": lock}
        freshness = self._freshness.inspect() if self._freshness is not None else None
        if freshness is not None:
            update["binding"] = freshness.state
            if freshness.state in ("stale", "unreadable"):
                error = stale_error(freshness, state.product)
                update["stale_parts"] = freshness.stale_parts
                update["stale_message"] = f"{error.message} {error.hint}"
        return report.model_copy(update=update)

    def down(self) -> StackReport:
        """Derruba a pilha e esquece o estado.

        Raises:
            ExternalToolError: Falha ao derrubar; o estado é mantido para nova tentativa.
        """
        state = self._states.load()
        if state is None:
            return StackReport(managed=False, state_file=str(self._states.location()))
        self._remove_containers(state)
        self._states.clear()
        return StackReport(
            managed=True,
            running=False,
            product=state.product,
            run_id=state.run_id,
            audit_file=str(state.audit_dir / "audit.jsonl"),
            state_file=str(self._states.location()),
        )

    def stop(self, stopper: ZapScanStopper, policy_dir_override: Path | None) -> StopReport:
        """Aciona a trava de emergência das duas cercas e para as varreduras do ZAP.

        As travas vêm primeiro e não dependem do ZAP: o `KILL` da cerca original e, com pilha
        gerenciada, o da `scope-proxy-nuclei`.

        Raises:
            ConfigError: Não há pasta de política conhecida ou o `KILL` não pôde ser criado.
        """
        state = self._states.load()
        directory = state.policy_dir if state else policy_dir_override
        if directory is None:
            raise ConfigError(
                "Não sei onde está a política do proxy: não há pilha gerenciada.",
                hint=f"Suba a pilha com hdast stack up ou defina {POLICY_DIR_ENV}.",
            )
        running = self._fresh_scans()
        created = self._policies.trigger_kill(directory)
        nuclei_directory = state.nuclei_policy_dir if state else None
        nuclei_created = (
            self._policies.trigger_kill(nuclei_directory) if nuclei_directory is not None else False
        )
        stopped, reachable, message = _stop_zap(stopper)
        return StopReport(
            kill_file=str(directory / "KILL"),
            kill_created=created,
            nuclei_kill_file=str(nuclei_directory / "KILL") if nuclei_directory else None,
            nuclei_kill_created=nuclei_created,
            stack_managed=state is not None,
            zap_reachable=reachable,
            zap_scans_stopped=stopped,
            zap_message=message,
            scans_running=running,
        )

    def _fresh_scans(self) -> tuple[ScanProgress, ...]:
        if self._running_scans is None:
            return ()
        now = self._clock.now()
        return tuple(
            item
            for item in self._running_scans.running()
            if (now - datetime.fromisoformat(item.updated_at)).total_seconds() <= _FRESH_SECONDS
        )

    def _tear_down_previous(self) -> list[str]:
        previous = self._states.load()
        if previous is None:
            return []
        try:
            self._remove_containers(previous)
        except ExternalToolError as error:
            return [f"A pilha anterior ({previous.product}) não foi derrubada: {error.message}"]
        self._states.clear()
        return [f"A pilha anterior ({previous.product}) foi derrubada antes de subir esta."]

    def _remove_containers(self, state: StackState) -> None:
        env = _common_env(state)
        for project in reversed(state.projects):
            self._compose.down(project, env, timeout_seconds=DOWN_TIMEOUT_SECONDS)

    @staticmethod
    def _oracle_requested(request: StackUpRequest, target: LabTarget | None) -> bool:
        if request.oracle and target is not CLINICA_PILOTO:
            raise ConfigError(
                "--oracle só vale para a Clínica Piloto.",
                hint="Use um perfil cujo base_url aponte para clinica-piloto.",
            )
        return request.oracle

    def _credentials(self, target: LabTarget | None, *, oracle: bool) -> dict[str, str]:
        generated: dict[str, str] = self._oracle_credentials() if oracle else {}
        for name in target.credential_env if target else ():
            if self._environ.get(name):
                continue
            if name.endswith("_EMAIL"):
                generated[name] = f"lab.{self._random.token_hex(_USERNAME_BYTES)}@example.com"
            elif name.endswith("USERNAME"):
                generated[name] = f"lab_{self._random.token_hex(_USERNAME_BYTES)}"
            elif target is CRAPI and name.endswith("_PASSWORD") and name != "CRAPI_DB_PASSWORD":
                generated[name] = "Aa1#" + self._random.token_hex(_PASSWORD_BYTES)
            else:
                generated[name] = self._random.token_hex(_PASSWORD_BYTES)
        return generated

    def _oracle_credentials(self) -> dict[str, str]:
        # O prefixo satisfaz a política de senha do Oracle; os valores só existem no estado local.
        def password() -> str:
            return "Aa1_" + self._random.token_hex(_PASSWORD_BYTES)

        db_password = self._environ.get("PILOT_ORACLE_PASSWORD") or password()
        generated = {
            "PILOT_ORACLE_PASSWORD": db_password,
            "PILOT_DB_PASSWORD": db_password,
            "PILOT_ORACLE_CLEANUP_PASSWORD": password(),
            **PILOT_ORACLE_ENV_FIXED,
        }
        # O que a pessoa já definiu no ambiente vence, exceto a senha do banco do piloto, que
        # precisa ser igual à do Oracle.
        return {
            name: value
            for name, value in generated.items()
            if name == "PILOT_DB_PASSWORD" or not self._environ.get(name)
        }

    def _projects(
        self, target: LabTarget | None, *, oracle: bool, suffix: str, bridge: bool
    ) -> tuple[ComposeProject, ...]:
        services = BASE_SERVICES + (target.main_services if target else ())
        main = ComposeProject(
            name=MAIN_PROJECT + suffix,
            workdir=str(self._root),
            files=("compose.yaml",) + ((OAST_GATEWAY_FILE,) if bridge else ()),
            profiles=target.main_profiles if target else (),
            services=services + ((OAST_GATEWAY_SERVICE,) if bridge else ()),
        )
        if target is None or target.attached_workdir is None:
            return (main,)
        attached = ComposeProject(
            name=(CRAPI_PROJECT if target is CRAPI else PILOT_PROJECT) + suffix,
            workdir=str(self._root / target.attached_workdir),
            files=(
                target.attached_files
                + ((PILOT_ORACLE_FILE,) if oracle else ())
                + ((CRAPI_OAST_FILE,) if bridge else ())
            ),
            profiles=(PILOT_ORACLE_PROFILE,) if oracle else (),
            remove_volumes=target is CRAPI,
        )
        return (main, attached)

    def _up_env(
        self,
        project: ComposeProject,
        state: StackState,
        options: dict[str, str],
        ports: tuple[str, str],
    ) -> dict[str, str]:
        network_env = {
            "HDAST_LAB_NETWORK": f"{state.projects[0].name}_lab_net",
            "HDAST_OAST_NETWORK": f"{state.projects[0].name}_oast_net",
        }
        if project == state.projects[0]:
            return {
                **network_env,
                KEY_ENV: state.zap_api_key,
                POLICY_DIR_ENV: state.policy_dir.as_posix(),
                AUDIT_DIR_ENV: state.audit_dir.as_posix(),
                **_nuclei_dirs_env(state),
                "HDAST_ZAP_HOST_PORT": ports[0],
                "HDAST_PROXY_HOST_PORT": ports[1],
                **(options if state.lab_target == "vampi" else {}),
            }
        return {
            **network_env,
            **{name: _PLACEHOLDER for name in CLINICA_PILOTO.inert_env},
            **state.target_env,
            "PILOT_HOST_PORT": str(PILOT_API_PORT),
            "PILOT_MGMT_HOST_PORT": str(PILOT_MANAGEMENT_PORT),
            **(
                {"CRAPI_WEB_PORT": "28888", "CRAPI_MAIL_PORT": "28025"}
                if state.lab_target == CRAPI.name
                else {}
            ),
            **options,
        }

    def _report(self, state: StackState, *, policy_file: Path) -> StackReport:
        env = _common_env(state)
        services: list[ServiceStatus] = []
        for project in state.projects:
            services.extend(self._compose.status(project, env))
        return StackReport(
            managed=True,
            running=bool(services) and all(item.state == "running" for item in services),
            product=state.product,
            run_id=state.run_id,
            lab_target=state.lab_target,
            not_after=state.not_after,
            zap_url=state.zap_url,
            auth_proxy_url=state.auth_proxy_url,
            policy_file=str(policy_file),
            audit_file=str(state.audit_dir / "audit.jsonl"),
            kill_switch=self._policies.kill_active(state.policy_dir),
            services=tuple(services),
            target_urls=state.target_urls,
            state_file=str(self._states.location()),
        )


def _target_options(target: LabTarget | None, request: StackUpRequest) -> dict[str, str]:
    options: dict[str, str] = {}
    if target is None:
        return options
    if request.vulnerable is not None and target.vulnerable_env:
        options[target.vulnerable_env] = "1" if request.vulnerable else "0"
    if request.token_ttl_seconds is not None and target.ttl_env:
        options[target.ttl_env] = str(request.token_ttl_seconds)
    return options


def _target_urls(target: LabTarget | None) -> dict[str, str]:
    if target is not CLINICA_PILOTO:
        return {}
    return {
        "api": f"http://127.0.0.1:{PILOT_API_PORT}",
        "management": f"http://127.0.0.1:{PILOT_MANAGEMENT_PORT}",
    }


def _common_env(state: StackState) -> dict[str, str]:
    # `down` e `ps` precisam que o compose consiga interpolar as variáveis obrigatórias;
    # os valores reais vêm do estado e, na falta deles (credenciais definidas pela pessoa),
    # um valor qualquer basta porque nada é criado nem lido.
    pilot = state.lab_target == CLINICA_PILOTO.name
    names = CLINICA_PILOTO.credential_env + CLINICA_PILOTO.inert_env if pilot else ()
    if state.lab_target == CRAPI.name:
        names = CRAPI.credential_env
    return {
        "HDAST_LAB_NETWORK": f"{state.projects[0].name}_lab_net",
        "HDAST_OAST_NETWORK": f"{state.projects[0].name}_oast_net",
        **{name: _PLACEHOLDER for name in names},
        **state.target_env,
        KEY_ENV: state.zap_api_key,
        POLICY_DIR_ENV: state.policy_dir.as_posix(),
        AUDIT_DIR_ENV: state.audit_dir.as_posix(),
        **_nuclei_dirs_env(state),
    }


def stack_compose_env(state: StackState) -> dict[str, str]:
    """Ambiente que o compose precisa para interpolar o arquivo da pilha já em pé.

    Serve a quem roda um serviço de uso único depois do `up` (o Nuclei): as redes, as pastas de
    política e de auditoria e a chave do ZAP, tudo do estado. Não traz a referência das imagens.
    """
    return _common_env(state)


def _nuclei_dirs_env(state: StackState) -> dict[str, str]:
    # Estado gravado antes da segunda cerca não tem as pastas: o compose usa as padrão (nega tudo).
    if state.nuclei_policy_dir is None or state.nuclei_audit_dir is None:
        return {}
    return {
        NUCLEI_POLICY_DIR_ENV: state.nuclei_policy_dir.as_posix(),
        NUCLEI_AUDIT_DIR_ENV: state.nuclei_audit_dir.as_posix(),
    }


def _project_suffix(environ: Mapping[str, str]) -> str:
    try:
        return StackProjectSuffix(value=environ.get("HDAST_STACK_PROJECT_SUFFIX", "")).value
    except ValidationError:
        raise ConfigError(
            "Sufixo de projeto Compose inválido.",
            hint="Use vazio ou hífen seguido de até 20 letras minúsculas ou dígitos.",
        ) from None


def _stop_zap(stopper: ZapScanStopper) -> tuple[int, bool, str | None]:
    try:
        return stopper.stop_all_scans(), True, None
    except ExternalToolError as error:
        return 0, False, error.message

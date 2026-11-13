"""Caso de uso `doctor`: responde "está tudo pronto para começar?" sem tocar o alvo.

Confere a máquina (Python, `uv`, pasta de produtos, Docker, imagens, portas fixas, validade da
pilha atual) e, se receber um produto, o perfil (estrutura, pendências do modelo, autorização,
janela e presença das variáveis de segredo). Nunca envia requisição ao alvo, nunca sobe
contêiner e nunca mostra o valor de um segredo: só diz se a variável existe.

Cada conferência vira um `DoctorCheck` (dado, não exceção). `fail` impede começar; `warn` é
algo a saber (imagem que será baixada, `uv` fora do PATH). A autorização e a janela usam a mesma
regra do `preflight` (`preflight_checks`), e os segredos também.
"""

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Protocol

from harness_dast.application.account_session import account_secret_fields
from harness_dast.application.doctor_report import (
    DoctorCheck,
    DoctorKind,
    DoctorReport,
    DoctorStatus,
    DoctorSummary,
)
from harness_dast.application.lab_targets import (
    CLINICA_PILOTO,
    PILOT_API_PORT,
    PILOT_MANAGEMENT_PORT,
    lab_target_for,
)
from harness_dast.application.ports import (
    Clock,
    HostInspector,
    ProfileRepository,
    SecretProvider,
    SecretVault,
    StackStateStore,
)
from harness_dast.application.preflight_checks import (
    authorization_window_checks,
    secret_presence_check,
)
from harness_dast.application.preflight_report import PreflightCheck
from harness_dast.application.stack import BASE_SERVICES, DEFAULT_PROXY_PORT, DEFAULT_ZAP_PORT
from harness_dast.application.validate_profile import ProfileReport
from harness_dast.domain.errors import ConfigError, ExternalToolError
from harness_dast.domain.profile import ProductProfile

MIN_PYTHON = (3, 12)
ZAP_PORT_ENV = "HDAST_ZAP_HOST_PORT"
PROXY_PORT_ENV = "HDAST_PROXY_HOST_PORT"
_MAX_PORT = 65535
_MAX_LISTED_IMAGES = 3
# Já reportadas por conferências próprias (`authorization` e `window`).
_REPORTED_ELSEWHERE = frozenset({"AUTHORIZATION_EXPIRED", "WINDOW_CLOSED"})


class ProfileValidator(Protocol):
    """Validação do perfil (`hdast profile validate`)."""

    def execute(self, product: str) -> ProfileReport:
        """Valida o perfil; levanta `ConfigError` se estruturalmente inválido."""
        ...


def _check(
    check_id: str,
    status: DoctorStatus,
    detail: str,
    kind: DoctorKind = "environment",
    operator_detail: str | None = None,
) -> DoctorCheck:
    return DoctorCheck(
        id=check_id, status=status, detail=detail, kind=kind, operator_detail=operator_detail
    )


def _from_preflight(check: PreflightCheck) -> DoctorCheck:
    return DoctorCheck(
        id=check.id,
        status="ok" if check.ok else "fail",
        detail=check.detail,
        kind=check.kind,
        operator_detail=check.operator_detail,
    )


class Doctor:
    """Executa as conferências (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        host: HostInspector,
        profiles: ProfileRepository,
        validator: ProfileValidator,
        secrets: SecretProvider,
        vault: SecretVault,
        states: StackStateStore,
        clock: Clock,
        environ: Mapping[str, str],
        python_version: tuple[int, int, int],
        products_dir: Path,
    ) -> None:
        """Cria o caso de uso com as portas de que precisa.

        Args:
            host: Olhos sobre a máquina (Docker, imagens, portas, pastas).
            profiles: Fonte dos perfis.
            validator: Validação do perfil.
            secrets: Provedor de segredos (só se pergunta se a variável existe).
            vault: Registro de segredos para mascaramento.
            states: Estado da pilha gerenciada, quando há.
            clock: Relógio injetado (autorização, janela, validade da pilha).
            environ: Ambiente (portas publicadas `HDAST_*_HOST_PORT`).
            python_version: Versão do Python em uso (maior, menor, micro).
            products_dir: Pasta de produtos efetiva (`--products-dir` ou `HDAST_PRODUCTS_DIR`).
        """
        self._host = host
        self._profiles = profiles
        self._validator = validator
        self._secrets = secrets
        self._vault = vault
        self._states = states
        self._clock = clock
        self._environ = environ
        self._python_version = python_version
        self._products_dir = products_dir

    def execute(self, product: str | None = None) -> DoctorReport:
        """Roda as conferências.

        Args:
            product: Produto a conferir também (perfil, autorização, janela e segredos), ou
                `None` para conferir só a máquina.

        Returns:
            O relatório. Reprovar uma conferência NÃO levanta: está em `checks` e `ready`.

        Raises:
            ConfigError: Só se o arquivo de estado da pilha estiver ilegível ou inválido.
        """
        profile_checks, profile = self._product_checks(product) if product else ((), None)
        checks = (
            *self._machine_checks(profile),
            *self._stack_checks(),
            *profile_checks,
        )
        return self._report(product, checks)

    def _report(self, product: str | None, checks: tuple[DoctorCheck, ...]) -> DoctorReport:
        counts = {status: sum(1 for c in checks if c.status == status) for status in _STATUSES}
        return DoctorReport(
            product=product,
            ready=counts["fail"] == 0,
            checks=checks,
            summary=DoctorSummary(ok=counts["ok"], warn=counts["warn"], fail=counts["fail"]),
        )

    # ------------------------------------------------------------------ máquina

    def _machine_checks(self, profile: ProductProfile | None) -> list[DoctorCheck]:
        checks = [self._python_check(), self._uv_check(), self._products_dir_check()]
        docker = self._docker_check()
        checks.append(docker)
        if docker.status == "ok":
            checks.append(self._images_check(profile))
        checks.extend(self._port_checks(profile))
        return checks

    def _python_check(self) -> DoctorCheck:
        major, minor, micro = self._python_version
        text = f"Python {major}.{minor}.{micro}"
        if (major, minor) >= MIN_PYTHON:
            return _check("python", "ok", f"{text} (mínimo {MIN_PYTHON[0]}.{MIN_PYTHON[1]}).")
        return _check(
            "python",
            "fail",
            f"{text} é antigo demais; o hdast exige {MIN_PYTHON[0]}.{MIN_PYTHON[1]} ou mais novo. "
            "Rode: uv python install 3.12.",
        )

    def _uv_check(self) -> DoctorCheck:
        version = self._host.uv_version()
        if version is not None:
            return _check("uv", "ok", f"uv {version} no PATH.")
        return _check(
            "uv",
            "warn",
            "O uv não está no PATH; os comandos 'uv run hdast ...' não vão funcionar. "
            "Instale em https://docs.astral.sh/uv/ e abra um terminal novo.",
        )

    def _products_dir_check(self) -> DoctorCheck:
        if self._host.directory_exists(self._products_dir):
            return _check("products_dir", "ok", f"Pasta de produtos: {self._products_dir}.")
        return _check(
            "products_dir",
            "fail",
            f"A pasta de produtos {self._products_dir} não existe. Crie-a, ou aponte outra com "
            "HDAST_PRODUCTS_DIR ou --products-dir.",
            kind="config",
        )

    def _docker_check(self) -> DoctorCheck:
        try:
            version = self._host.docker_version()
        except ExternalToolError as error:
            hint = error.hint or "Abra o Docker Desktop e espere ele terminar de subir."
            return _check("docker", "fail", f"{error.message} {hint}")
        return _check("docker", "ok", f"Docker {version} respondendo.")

    def _images_check(self, profile: ProductProfile | None) -> DoctorCheck:
        try:
            images = self._host.compose_images(self._services(profile))
            missing = [image for image in images if not self._host.image_present(image)]
        except (ConfigError, ExternalToolError) as error:
            hint = error.hint or ""
            return _check("images", "fail", f"{error.message} {hint}".strip())
        if not missing:
            return _check("images", "ok", f"As {len(images)} imagens da pilha já estão no Docker.")
        shown = ", ".join(_short_image(image) for image in missing[:_MAX_LISTED_IMAGES])
        more = len(missing) - _MAX_LISTED_IMAGES
        suffix = f" e mais {more}" if more > 0 else ""
        return _check(
            "images",
            "warn",
            f"Faltam {len(missing)} de {len(images)} imagens ({shown}{suffix}). Serão baixadas "
            "ou construídas no primeiro 'hdast stack up' (precisa de internet e leva alguns "
            "minutos).",
        )

    @staticmethod
    def _services(profile: ProductProfile | None) -> tuple[str, ...]:
        target = lab_target_for(profile.environment.base_url) if profile else None
        return BASE_SERVICES + (target.main_services if target else ())

    def _port_checks(self, profile: ProductProfile | None) -> list[DoctorCheck]:
        managed = self._states.load() is not None
        wanted = [
            (ZAP_PORT_ENV, self._environ.get(ZAP_PORT_ENV, DEFAULT_ZAP_PORT), "ZAP"),
            (
                PROXY_PORT_ENV,
                self._environ.get(PROXY_PORT_ENV, DEFAULT_PROXY_PORT),
                "proxy de escopo",
            ),
        ]
        checks = [self._port_check(name, raw, what, managed=managed) for name, raw, what in wanted]
        target = lab_target_for(profile.environment.base_url) if profile else None
        if target is CLINICA_PILOTO:
            for port, what in (
                (PILOT_API_PORT, "API da Clínica Piloto"),
                (PILOT_MANAGEMENT_PORT, "gestão da Clínica Piloto"),
            ):
                checks.append(self._port_check(None, str(port), what, managed=managed))
        return checks

    def _port_check(
        self, env_name: str | None, raw: str, what: str, *, managed: bool
    ) -> DoctorCheck:
        port = _parse_port(raw)
        if port is None:
            return _check(
                f"port:{env_name or raw}",
                "fail",
                f"A porta do {what} ({raw!r}) não é um número de 1 a {_MAX_PORT}. "
                f"Corrija {env_name} ou remova a variável.",
                kind="config",
            )
        check_id = f"port:{port}"
        if self._host.port_is_free(port):
            return _check(check_id, "ok", f"Porta {port} ({what}) livre.")
        if managed:
            return _check(
                check_id, "ok", f"Porta {port} ({what}) em uso, provavelmente pela pilha atual."
            )
        change = f"defina {env_name} com outra porta" if env_name else "libere a porta"
        return _check(
            check_id,
            "fail",
            f"A porta {port} ({what}) já está em uso por outro programa. Feche-o ou {change}.",
        )

    # ------------------------------------------------------------------- pilha

    def _stack_checks(self) -> list[DoctorCheck]:
        state = self._states.load()
        if state is None:
            return []
        expires = datetime.fromisoformat(state.not_after)
        if self._clock.now() >= expires:
            return [
                _check(
                    "stack",
                    "warn",
                    f"A pilha de {state.product} venceu em {state.not_after}; o proxy nega "
                    "tudo. Rode 'hdast stack up' de novo antes de varrer.",
                )
            ]
        return [
            _check("stack", "ok", f"Pilha de {state.product} no ar, vale até {state.not_after}.")
        ]

    # ------------------------------------------------------------------ produto

    def _product_checks(self, product: str) -> tuple[list[DoctorCheck], ProductProfile | None]:
        profile_check = self._profile_check(product)
        try:
            profile = self._profiles.load(product)
        except ConfigError:
            # O perfil não carrega: `profile_check` já diz por quê; o resto depende dele.
            return [profile_check], None
        checks = [profile_check]
        checks.extend(
            _from_preflight(check)
            for check in authorization_window_checks(profile, self._clock.now())
        )
        checks.extend(self._secret_checks(profile))
        return checks, profile

    def _profile_check(self, product: str) -> DoctorCheck:
        try:
            report = self._validator.execute(product)
        except ConfigError as error:
            hint = error.hint or "Corrija o target.yml e rode 'hdast profile validate'."
            return _check("profile", "fail", f"{error.message} {hint}", kind="config")
        issues = [issue for issue in report.issues if issue.code not in _REPORTED_ELSEWHERE]
        if not issues:
            return _check("profile", "ok", "O perfil é válido e não tem pendências do modelo.")
        listed = "; ".join(f"[{issue.code}] {issue.field}" for issue in issues[:5])
        return _check(
            "profile",
            "fail",
            f"O perfil tem {len(issues)} pendência(s): {listed}. Rode 'hdast profile validate "
            f"{product}' para ver o que preencher.",
            kind="config",
        )

    def _secret_checks(self, profile: ProductProfile) -> list[DoctorCheck]:
        return [
            _from_preflight(
                secret_presence_check(
                    account.alias, account_secret_fields(account), self._secrets, self._vault
                )
            )
            for account in profile.auth.accounts
        ]


_STATUSES: tuple[DoctorStatus, ...] = ("ok", "warn", "fail")


def _parse_port(raw: str) -> int | None:
    if not raw.isascii() or not raw.isdigit():
        return None
    port = int(raw)
    return port if 1 <= port <= _MAX_PORT else None


def _short_image(reference: str) -> str:
    """Nome da imagem sem o digest (que é longo e não ajuda quem lê)."""
    return reference.split("@", 1)[0]

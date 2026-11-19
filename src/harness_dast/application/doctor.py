"""Caso de uso `doctor`: responde "está tudo pronto para começar?" sem tocar o alvo.

Confere a máquina (Python, `uv`, pasta de produtos, Docker, imagens, portas fixas, validade da
pilha atual) e, se receber um produto, o perfil (estrutura, pendências do modelo, autorização,
janela e presença das variáveis de segredo). Nunca envia requisição ao alvo, nunca sobe
contêiner e nunca mostra o valor de um segredo: só diz se a variável existe.

Dois avisos olham só o perfil (`doctor_checks`): o modo amplo de caminho e a falta de duas contas
do mesmo papel para o `authz`.

Cada conferência vira um `DoctorCheck` (dado, não exceção). `fail` impede começar; `warn` é
algo a saber (imagem auxiliar que será baixada, `uv` fora do PATH). A autorização, a janela e os
segredos usam as regras do `preflight` (`preflight_checks`).
"""

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Protocol

from harness_dast.application.account_session import account_secret_fields
from harness_dast.application.common_ports import (
    Clock,
    ProfileRepository,
    SecretProvider,
    SecretVault,
    StackStateStore,
)
from harness_dast.application.doctor_checks import authz_peer_checks, wide_mode_checks
from harness_dast.application.doctor_ports import HostInspector
from harness_dast.application.doctor_report import DoctorCheck, DoctorReport, make_check
from harness_dast.application.doctor_stack import DoctorStackChecks
from harness_dast.application.lab_targets import lab_target_for
from harness_dast.application.preflight_checks import (
    authorization_window_checks,
    secret_presence_check,
)
from harness_dast.application.preflight_report import PreflightCheck
from harness_dast.application.stack_images import StackImages
from harness_dast.application.validate_profile import ProfileReport
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile

MIN_PYTHON = (3, 12)
# Já reportadas por conferências próprias (`authorization` e `window`).
_REPORTED_ELSEWHERE = frozenset({"AUTHORIZATION_EXPIRED", "WINDOW_CLOSED"})


class ProfileValidator(Protocol):
    """Validação do perfil (`hdast profile validate`)."""

    def execute(self, product: str) -> ProfileReport:
        """Valida o perfil; levanta `ConfigError` se estruturalmente inválido."""
        ...


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
        images: StackImages,
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
            host: Olhos sobre a máquina (Docker, portas, pastas).
            images: Seleção e conferência das imagens da pilha.
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
        self._stack = DoctorStackChecks(host, images, environ)
        self._profiles = profiles
        self._validator = validator
        self._secrets = secrets
        self._vault = vault
        self._states = states
        self._clock = clock
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
        target = lab_target_for(profile.environment.base_url) if profile else None
        checks = (
            self._python_check(),
            self._uv_check(),
            self._products_dir_check(),
            *self._stack.execute(target, managed=self._states.load() is not None),
            *self._stack_checks(),
            *profile_checks,
        )
        return DoctorReport.from_checks(checks, product=product)

    def _python_check(self) -> DoctorCheck:
        major, minor, micro = self._python_version
        text = f"Python {major}.{minor}.{micro}"
        if (major, minor) >= MIN_PYTHON:
            return make_check("python", "ok", f"{text} (mínimo {MIN_PYTHON[0]}.{MIN_PYTHON[1]}).")
        return make_check(
            "python",
            "fail",
            f"{text} é antigo demais; o hdast exige {MIN_PYTHON[0]}.{MIN_PYTHON[1]} ou mais novo. "
            "Rode: uv python install 3.12.",
        )

    def _uv_check(self) -> DoctorCheck:
        version = self._host.uv_version()
        if version is not None:
            return make_check("uv", "ok", f"uv {version} no PATH.")
        return make_check(
            "uv",
            "warn",
            "O uv não está no PATH; os comandos 'uv run hdast ...' não vão funcionar. "
            "Instale em https://docs.astral.sh/uv/ e abra um terminal novo.",
        )

    def _products_dir_check(self) -> DoctorCheck:
        if self._host.directory_exists(self._products_dir):
            return make_check("products_dir", "ok", f"Pasta de produtos: {self._products_dir}.")
        return make_check(
            "products_dir",
            "fail",
            f"A pasta de produtos {self._products_dir} não existe. Crie-a, ou aponte outra com "
            "HDAST_PRODUCTS_DIR ou --products-dir.",
            kind="config",
        )

    # ------------------------------------------------------------------- pilha

    def _stack_checks(self) -> list[DoctorCheck]:
        state = self._states.load()
        if state is None:
            return []
        expires = datetime.fromisoformat(state.not_after)
        if self._clock.now() >= expires:
            return [
                make_check(
                    "stack",
                    "warn",
                    f"A pilha de {state.product} venceu em {state.not_after}; o proxy nega "
                    "tudo. Rode 'hdast stack up' de novo antes de varrer.",
                )
            ]
        return [
            make_check(
                "stack", "ok", f"Pilha de {state.product} no ar, vale até {state.not_after}."
            )
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
        checks.extend(wide_mode_checks(profile))
        checks.extend(authz_peer_checks(profile))
        return checks, profile

    def _profile_check(self, product: str) -> DoctorCheck:
        try:
            report = self._validator.execute(product)
        except ConfigError as error:
            hint = error.hint or "Corrija o target.yml e rode 'hdast profile validate'."
            return make_check("profile", "fail", f"{error.message} {hint}", kind="config")
        issues = [issue for issue in report.issues if issue.code not in _REPORTED_ELSEWHERE]
        if not issues:
            return make_check("profile", "ok", "O perfil é válido e não tem pendências do modelo.")
        listed = "; ".join(f"[{issue.code}] {issue.field}" for issue in issues[:5])
        return make_check(
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

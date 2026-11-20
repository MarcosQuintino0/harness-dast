"""Caso de uso `hdast setup`: os dois atos humanos do cadastro, em ordem e separados (ADR 0114).

Conduz a PESSOA, num terminal, por (1) conferir que o perfil está válido, (2) gravar no cofre as
senhas que faltam e (3) aprovar o escopo diante do resumo. Não junta as decisões: gravar senha e
aprovar escopo continuam sendo `secret set` e `profile approve`, reaproveitados sem cópia. O
agente nunca roda este comando; a CLI o recusa sem terminal interativo.
"""

from pydantic import BaseModel, ConfigDict

from harness_dast.application.common_ports import ProfileRepository
from harness_dast.application.scope_approval import ApproveReport, ScopeApprovals
from harness_dast.application.secret_admin import SecretAdmin
from harness_dast.application.secret_refs import profile_secret_refs
from harness_dast.application.setup_ports import AppliedDefaultsReader, SetupNotifier
from harness_dast.application.validate_profile import ReadinessIssue, ValidateProfile
from harness_dast.domain.errors import ConfigError

_SETUP = "hdast setup"
# A janela fechada não impede aprovar o escopo: ela só vale na hora de executar.
_NOT_A_SETUP_BLOCK = frozenset({"WINDOW_CLOSED"})


class SetupReport(BaseModel):
    """Resultado de `hdast setup`: nomes e estados, nunca valor de segredo.

    Attributes:
        product: Produto.
        secrets_written: Nomes do cofre que a pessoa gravou agora.
        secrets_present: Nomes do cofre que já existiam e não foram pedidos de novo.
        env_secrets: Nomes `env:` citados pelo perfil; vêm do ambiente, não do cofre.
        defaults: Padrões mínimos da CLI que a carta aplicou (`campo = valor`).
        approval: Resultado da aprovação do escopo (igual ao de `profile approve`).
    """

    model_config = ConfigDict(frozen=True)

    product: str
    secrets_written: tuple[str, ...]
    secrets_present: tuple[str, ...]
    env_secrets: tuple[str, ...]
    defaults: tuple[str, ...]
    approval: ApproveReport


class SetupProduct:
    """Conduz a pessoa pelas senhas e pela aprovação do escopo de um produto."""

    def __init__(
        self,
        validator: ValidateProfile,
        profiles: ProfileRepository,
        secrets: SecretAdmin,
        approvals: ScopeApprovals,
        defaults: AppliedDefaultsReader,
        notifier: SetupNotifier,
    ) -> None:
        """Cria o caso de uso.

        Args:
            validator: Validação do perfil (`profile validate`).
            profiles: Repositório COMUM de perfis.
            secrets: Gestão do cofre (`secret set|list`).
            approvals: Aprovação do escopo (`profile approve`), com o prompt que mostra o
                resumo, faz a pausa e pede o nome do produto.
            defaults: Leitor dos padrões mínimos aplicados na carta.
            notifier: Canal de mensagens à pessoa.
        """
        self._validator = validator
        self._profiles = profiles
        self._secrets = secrets
        self._approvals = approvals
        self._defaults = defaults
        self._notifier = notifier

    def run(self, product: str, *, interactive: bool) -> SetupReport:
        """Valida o perfil, grava as senhas que faltam e pede a aprovação do escopo.

        Args:
            product: Slug do produto.
            interactive: Se há terminal interativo e a saída não é `--json`; a CLI calcula.

        Raises:
            ConfigError: Sem terminal interativo (o agente não roda o `setup`), produto ou
                perfil inválido, perfil ainda não executável (nada é pedido antes), cofre
                indisponível ou falha ao gravar.
        """
        if not interactive:
            raise ConfigError(
                "Só uma pessoa, em terminal interativo, roda o setup do produto.",
                hint=f"Rode no seu terminal, sem --json e sem redirecionar a entrada: "
                f"{_SETUP} {product}",
            )
        self._require_ready(product)
        profile = self._profiles.load(product)
        listing = self._secrets.list_secrets(product)
        written: list[str] = []
        for entry in listing.entries:
            if not entry.present:
                self._notifier.say(f"Falta a senha {entry.name} no cofre; digite-a a seguir.")
                self._secrets.set_secret(entry.name, interactive=True)
                written.append(entry.name)
        present = tuple(entry.name for entry in listing.entries if entry.present)
        env_names = tuple(
            sorted({ref.name for _, ref in profile_secret_refs(profile) if ref.kind == "env"})
        )
        if env_names:
            self._notifier.say(
                "Segredos lidos do ambiente, não do cofre (nada a digitar aqui): "
                + ", ".join(env_names)
            )
        applied = self._defaults.read(product)
        approval = self._approvals.approve(product, interactive=True, setup_defaults=applied)
        return SetupReport(
            product=product,
            secrets_written=tuple(written),
            secrets_present=present,
            env_secrets=env_names,
            defaults=applied,
            approval=approval,
        )

    def _require_ready(self, product: str) -> None:
        report = self._validator.execute(product)
        blocking = [i for i in report.issues if i.code not in _NOT_A_SETUP_BLOCK]
        if blocking:
            raise ConfigError(
                f"O perfil de {product} ainda não está pronto; nada foi pedido:\n"
                + "\n".join(_issue_line(issue) for issue in blocking),
                hint="Corrija as pendências (a skill fix-reachability ou a carta) e rode "
                f"{_SETUP} {product} de novo.",
            )


def _issue_line(issue: ReadinessIssue) -> str:
    return f"- [{issue.code}] {issue.field}: {issue.message}"

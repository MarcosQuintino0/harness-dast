"""Caso de uso `authz --draft-matrix`: rascunha a tabela "quem pode o quê" (ADR 0041).

Só LÊ o perfil e o OpenAPI (como o `spec inspect`) e, se houver `--run`, o `exchanges.json` do
`probe`. **Não envia nada ao alvo**, não carrega a aprovação do escopo, não usa a pilha e não
toca o `target.yml`: grava um arquivo à parte que o carregador do perfil não lê. O rascunho é
hipótese e nunca preenche `deny` (veja `domain.authz.matrix_draft`).
"""

from dataclasses import dataclass

from harness_dast.application.authz.ports import AuthzArtifacts, AuthzDraftWriter
from harness_dast.application.common_ports import ProfileRepository, SpecLoader
from harness_dast.domain.authz.matrix_draft import draft_items, render_draft
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.run_ref import require_run_id


@dataclass(frozen=True)
class DraftRequest:
    """Pedido de rascunho.

    Attributes:
        product: Nome do produto.
        run_id: Execução do `probe` cujos pedidos enriquecem o `allow`; `None` deixa-o vazio.
    """

    product: str
    run_id: str | None = None


@dataclass(frozen=True)
class DraftResult:
    """Rascunho gravado.

    Attributes:
        product: Produto.
        path: Arquivo gravado.
        operations: Operações no rascunho.
        with_run: Se o `allow` foi preenchido a partir de um `probe`.
        review: Aviso fixo: o rascunho não vale nada até uma pessoa levá-lo ao perfil.
    """

    product: str
    path: str
    operations: int
    with_run: bool
    review: str


REVIEW_NOTICE = (
    "O rascunho é hipótese e não vale nada até uma pessoa decidir cada linha, levá-la ao "
    "target.yml (authz.access_matrix) e aprovar o escopo com hdast profile approve. O deny "
    "está vazio de propósito: quem proíbe é o dono do produto."
)


class AuthzDraft:
    """Orquestra o rascunho (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        specs: SpecLoader,
        artifacts: AuthzArtifacts,
        writer: AuthzDraftWriter,
    ) -> None:
        """Cria o caso de uso com as portas de que precisa.

        `profiles` é o repositório SEM conferência de aprovação: nada aqui toca o alvo.
        """
        self._profiles = profiles
        self._specs = specs
        self._artifacts = artifacts
        self._writer = writer

    def execute(self, request: DraftRequest) -> DraftResult:
        """Grava `authz-matrix.draft.yml` na pasta do produto.

        Raises:
            ConfigError: Perfil ou OpenAPI inválido, `run_id` de outro produto ou sem
                `exchanges.json`, ou rascunho já existente (nunca é sobrescrito).
        """
        profile = self._profiles.load(request.product)
        spec = self._specs.load(request.product, profile)
        exchanges = self._exchanges(request, profile.product)
        infrastructure = {
            path
            for path in (profile.login_path, profile.probe.health_path, profile.probe.setup_path)
            if path is not None
        }
        items = draft_items(
            spec.operations,
            exchanges,
            {account.alias: account.role for account in profile.auth.accounts},
            profile.authz.role_order,
            profile.authz.public_operations,
            infrastructure,
        )
        text = render_draft(profile.product, items, with_run=request.run_id is not None)
        path = self._writer.write_draft(request.product, text)
        return DraftResult(
            product=profile.product,
            path=path,
            operations=len(items),
            with_run=request.run_id is not None,
            review=REVIEW_NOTICE,
        )

    def _exchanges(self, request: DraftRequest, product: str) -> tuple[ExchangeRecord, ...]:
        if request.run_id is None:
            return ()
        log = self._artifacts.read_exchanges(require_run_id(request.run_id))
        if log.product != product:
            raise ConfigError(
                "A execução informada é de outro produto.",
                hint="Use o run_id do probe deste produto.",
            )
        return log.exchanges

"""Cria proposta neutra vinculada às fontes atuais, sem executar ou ativar estratégia."""

from datetime import datetime

from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_approval import ScopeApproval, check_approval
from harness_dast.domain.strategy import CoverageChoice, Strategy, StrategyReferences
from harness_dast.domain.strategy_basis import make_strategy_basis


def capture_strategy(
    profile: ProductProfile,
    approval: ScopeApproval | None,
    now: datetime,
    *,
    openapi_sha256: str,
    data_rules_sha256: str,
    flows_sha256: str,
    engine_version: str | None,
) -> Strategy:
    """Cria escolha neutra para perfil aprovado e autorização ainda válida.

    Digests e versão devem vir de fontes atuais independentes da estratégia; a obtenção
    dessas fontes pertence à aplicação. O resultado não aprova nem ativa a estratégia.
    """
    check_approval(profile, approval).ensure_approved()
    profile.scope.authorization.ensure_valid(now)
    try:
        basis = make_strategy_basis(
            profile,
            openapi_sha256=openapi_sha256,
            data_rules_sha256=data_rules_sha256,
            flows_sha256=flows_sha256,
            engine_version=engine_version,
        )
    except ValidationError:
        raise ConfigError("Não foi possível vincular os documentos atuais.") from None
    if basis is None:
        raise ConfigError("A versão efetiva do motor está indisponível ou inválida.")
    return Strategy(
        schema_version=1,
        references=StrategyReferences(
            target="target.yml", data_rules="data-rules.yml", flows="flows.yml"
        ),
        choices=(
            CoverageChoice(
                name="coverage",
                value="preserve",
                source="observation",
                reason="preserve_baseline",
                valid_until=profile.scope.authorization.valid_until,
                state="validated",
                basis=basis,
            ),
        ),
    )

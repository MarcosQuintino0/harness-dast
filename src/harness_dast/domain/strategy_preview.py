"""Prévia simbólica de operações e política, sem tráfego e sem afirmar execução."""

from typing import Literal

from harness_dast.domain.api_model import ApiSpec, Operation
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.probe_plan import PlannedOperation, plan_probe
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scan_config import Level
from harness_dast.domain.scan_policy import build_policy
from harness_dast.domain.secret_ref import ProfileModel


class PreviewEntry(ProfileModel):
    """Nome e localização de uma entrada declarada, sem valor de exemplo."""

    name: str
    location: str


class PreviewOperation(ProfileModel):
    """Operação, conta e pré-condições previstos pelo planejador do probe."""

    operation_id: str
    method: str
    path: str
    account: str
    probe_decision: str
    depends_on: tuple[str, ...]
    entries: tuple[PreviewEntry, ...]
    body_entries_complete: Literal[False] = False
    scope_check: Literal["template_only"] = "template_only"
    scan_status: Literal["pending_probe_and_zap"] = "pending_probe_and_zap"


class StrategyPreview(ProfileModel):
    """Matriz simbólica; catálogo de regras e resultados reais ainda são desconhecidos."""

    operations: tuple[PreviewOperation, ...]
    strength: Level
    disabled_rules: tuple[int, ...]
    rules: Literal["enabled_except_disabled_catalog_pending_zap"] = (
        "enabled_except_disabled_catalog_pending_zap"
    )
    injectable_mask: int
    coverage: Literal["pending_probe_and_zap"] = "pending_probe_and_zap"


def _entries(operation: Operation) -> tuple[PreviewEntry, ...]:
    entries = [PreviewEntry(name=p.name, location=p.location) for p in operation.parameters]
    if operation.request_body is not None:
        for media in operation.request_body.media:
            if media.body_schema is not None:
                entries.extend(
                    PreviewEntry(name=name, location=f"body:{media.media_type}")
                    for name in media.body_schema.properties
                )
    return tuple(entries)


def _operation(
    profile: ProductProfile, operation: Operation, plan: PlannedOperation
) -> PreviewOperation:
    return PreviewOperation(
        operation_id=plan.operation_id,
        method=plan.method,
        path=plan.path,
        account=profile.account_for(plan.operation_id, plan.method, plan.path),
        probe_decision=plan.decision,
        depends_on=plan.depends_on,
        entries=_entries(operation),
    )


def preview(profile: ProductProfile, spec: ApiSpec, flows: FlowSpec | None) -> StrategyPreview:
    """Constrói prévia do plano padrão, sem rede nem aprovação e sem valores de entrada."""
    plans = plan_probe(spec, flows, profile.guard(), profile.environment.base_url)
    operations = {operation.operation_id: operation for operation in spec.operations}
    policy = build_policy(profile.scan)
    return StrategyPreview(
        operations=tuple(
            _operation(profile, operations[item.operation_id], item) for item in plans
        ),
        strength=policy.strength,
        disabled_rules=policy.disabled_rules,
        injectable_mask=policy.injectable_mask,
    )

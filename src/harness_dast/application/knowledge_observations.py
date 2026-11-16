"""Extrai receitas comprovadas de uma execução, sem persistir valores ou respostas."""

from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.knowledge import Knowledge
from harness_dast.domain.knowledge_checks import (
    ensure_effect,
    ensure_flow_use,
    ensure_rule_use,
    ensure_run_matches,
)
from harness_dast.domain.knowledge_evidence import KnowledgeRunEvidence
from harness_dast.domain.knowledge_receipts import KnowledgeFlowUse, KnowledgeRuleUse
from harness_dast.domain.probe_result import ArtifactHashes, OperationResult
from harness_dast.domain.profile import ProductProfile


def from_run(
    base: Knowledge,
    evidence: KnowledgeRunEvidence,
    profile: ProductProfile,
    spec: ApiSpec,
    rules: DataRules | None,
    flows: FlowSpec | None,
    hashes: ArtifactHashes,
    engine_version: str,
) -> Knowledge:
    """Vincula somente recibos de operações 2xx e efeito comprovado por authz."""
    ensure_run_matches(evidence, profile, hashes, engine_version)
    successful = {
        item.operation_id: item
        for item in evidence.probe.operations
        if item.outcome == "success"
        and item.status is not None
        and 200 <= item.status < 300
        and item.attempts > 0
    }
    accounts, rule_uses, flow_uses = _collect(evidence, profile, spec, rules, flows, successful)
    for use in evidence.effects:
        ensure_effect(use, profile, spec)
    flags = {
        "account": bool(accounts),
        "authentication": bool(accounts),
        "data": bool(rule_uses),
        "flow": bool(flow_uses),
        "effect": bool(evidence.effects),
    }
    entries = tuple(
        entry.model_copy(
            update={
                "source": "observation" if flags[entry.kind] else "contract",
                "state": "validated" if flags[entry.kind] else "proposed",
            }
        )
        for entry in base.entries
    )
    return Knowledge.from_data(
        base.model_copy(
            update={
                "entries": entries,
                "provenance": evidence.provenance,
                "observed_accounts": tuple(sorted(accounts)),
                "observed_rules": tuple(
                    sorted(
                        rule_uses, key=lambda item: (item.operation, item.rule_index, item.field)
                    )
                ),
                "observed_flows": tuple(
                    sorted(
                        flow_uses,
                        key=lambda item: (item.producer, item.consumer, item.target_field),
                    )
                ),
                "effects": evidence.effects,
            }
        ).model_dump(mode="json")
    )


def _collect(
    evidence: KnowledgeRunEvidence,
    profile: ProductProfile,
    spec: ApiSpec,
    rules: DataRules | None,
    flows: FlowSpec | None,
    successful: dict[str, OperationResult],
) -> tuple[set[str], set[KnowledgeRuleUse], set[KnowledgeFlowUse]]:
    accounts: set[str] = set()
    rule_uses: set[KnowledgeRuleUse] = set()
    flow_uses: set[KnowledgeFlowUse] = set()
    for operation in successful.values():
        if not spec.has_operation(operation.operation_id):
            raise ConfigError("Operacao observada ausente do contrato atual.")
        expected = spec.get_operation(operation.operation_id)
        if expected.method.upper() != operation.method or expected.path != operation.path:
            raise ConfigError("Operacao observada diverge do contrato atual.")
        if operation.account is not None:
            profile.select_account(operation.account)
            if operation.account not in evidence.manifest.accounts:
                raise ConfigError("Conta observada ausente do manifesto.")
            accounts.add(operation.account)
        for use in operation.rule_uses:
            if use.operation != operation.operation_id:
                raise ConfigError("Recibo de regra pertence a outra operacao.")
            ensure_rule_use(use, rules, spec)
            rule_uses.add(use)
        for flow_use in operation.flow_uses:
            if flow_use.consumer != operation.operation_id or flow_use.producer not in successful:
                raise ConfigError("Recibo de fluxo sem produtor ou consumidor comprovado.")
            ensure_flow_use(flow_use, flows, spec)
            flow_uses.add(flow_use)
    return accounts, rule_uses, flow_uses

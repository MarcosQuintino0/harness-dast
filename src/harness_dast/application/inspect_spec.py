"""Caso de uso `spec inspect`: resumo do OpenAPI para o agente mais verificações cruzadas.

Entrega o resumo compacto (`domain.api_summary`) e responde, com dados, às perguntas que o
agente precisa fechar antes de escrever `data-rules.yml` e `flows.yml`: o que nunca será
enviado e por quê, quais regras não casam com campo algum, quais campos obrigatórios ainda
precisam de regra e se `data-rules.yml` e `flows.yml` (quando existem) são válidos e
coerentes com o OpenAPI.

Perfil e OpenAPI inválidos são erro (`ConfigError`). Problemas em `data-rules.yml` e
`flows.yml` viram `issues`: o comando existe justamente para ajudar a corrigi-los.
"""

from collections.abc import Callable

from harness_dast.application.inspect_report import (
    DocumentInfo,
    InspectIssue,
    NeedsRule,
    NotSentOperation,
    OperationAccount,
    SpecInspection,
    UnusedRule,
)
from harness_dast.application.ports import (
    Clock,
    ProductDocuments,
    ProfileRepository,
    SpecLoader,
    ValueSourceFactory,
)
from harness_dast.domain.api_model import ApiSpec, safe_identifier
from harness_dast.domain.api_summary import DEFAULT_BUDGET_CHARS, summarize
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import ConfigError, ScopeViolation
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.probe_plan import PlannedOperation, looks_destructive, plan_probe
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.request_builder import RequestBuilder
from harness_dast.domain.scope import ScopeGuard
from harness_dast.domain.spec_examples import inspect_examples
from harness_dast.domain.spec_hints import suggest_spec_hints

_BUILD_CHECK_SEED = 0
_BUILD_CHECK_TAG = "0000"


def _servers_out_of_scope(spec: ApiSpec, guard: ScopeGuard) -> tuple[str, ...]:
    found: list[str] = []
    for server in spec.servers:
        if "://" not in server:
            continue
        try:
            guard.ensure_origin_allowed(server)
        except ScopeViolation:
            found.append(safe_identifier(server))
    return tuple(found)


def _not_sent(plan: tuple[PlannedOperation, ...]) -> tuple[NotSentOperation, ...]:
    return tuple(
        NotSentOperation(
            operation_id=item.operation_id,
            method=item.method,
            path=item.path,
            reason=item.decision,
            message=item.reason or "",
        )
        for item in plan
        if item.decision != "send"
    )


def _load_document[T](
    loader: Callable[[], T | None], code: str, issues: list[InspectIssue]
) -> T | None:
    try:
        return loader()
    except ConfigError as error:
        issues.append(InspectIssue(code=code, message=error.message, hint=error.hint))
        return None


def _check_against(checker: Callable[[], object], code: str, issues: list[InspectIssue]) -> bool:
    try:
        checker()
    except ConfigError as error:
        issues.append(InspectIssue(code=code, message=error.message, hint=error.hint))
        return False
    return True


class InspectSpec:
    """Monta o `SpecInspection` (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        specs: SpecLoader,
        documents: ProductDocuments,
        value_sources: ValueSourceFactory,
        clock: Clock,
    ) -> None:
        """Cria o caso de uso com as portas de que precisa."""
        self._profiles = profiles
        self._specs = specs
        self._documents = documents
        self._value_sources = value_sources
        self._clock = clock

    def execute(self, product: str, budget_chars: int = DEFAULT_BUDGET_CHARS) -> SpecInspection:
        """Inspeciona o OpenAPI do produto.

        Args:
            product: Nome do produto.
            budget_chars: Teto de caracteres do resumo (o domínio o limita ao mínimo).

        Raises:
            ConfigError: Perfil ou OpenAPI inválido.
        """
        profile = self._profiles.load(product)
        spec = self._specs.load(product, profile)
        issues: list[InspectIssue] = []
        rules, rules_ok = self._rules(product, spec, issues)
        flows, flows_ok = self._flows(product, spec, issues)
        # Sem arquivo válido, o plano e a montagem usam o que for utilizável: flows inválido
        # não pode ordenar nem excluir consumidores.
        usable_flows = flows if flows_ok else None
        guard = profile.guard()
        plan = plan_probe(
            spec, usable_flows, guard, profile.environment.base_url, include_delete=False
        )
        needs, unchecked = self._build_check(spec, plan, rules if rules_ok else None, usable_flows)
        _check_against(
            lambda: profile.auth.ensure_operations_exist([o.operation_id for o in spec.operations]),
            "ACCOUNT_MAP_MISMATCH",
            issues,
        )
        issues.extend(
            InspectIssue(
                code="EXAMPLE_" + code.upper(), message=f"{where}: exemplo incompatível ({code})."
            )
            for where, code in inspect_examples(spec)
        )
        return SpecInspection(
            product=product,
            summary=summarize(spec, budget_chars),
            servers_out_of_scope=_servers_out_of_scope(spec, guard),
            not_sent=_not_sent(plan),
            suspicious_operations=tuple(
                o.operation_id for o in spec.operations if looks_destructive(o)
            ),
            data_rules=_info(
                rules,
                rules_ok,
                len(rules.rules) if rules else 0,
                _failed(issues, "DATA_RULES_INVALID"),
            ),
            flows=_info(
                flows,
                flows_ok,
                len(flows.bindings) if flows else 0,
                _failed(issues, "FLOWS_INVALID"),
            ),
            unused_rules=_unused_rules(rules, spec) if rules_ok else (),
            needs_rule=needs,
            needs_rule_unchecked=unchecked,
            issues=tuple(issues),
            operation_accounts=_operation_accounts(profile, plan),
            hints=suggest_spec_hints(profile, spec.operations, plan),
        )

    def _rules(
        self, product: str, spec: ApiSpec, issues: list[InspectIssue]
    ) -> tuple[DataRules | None, bool]:
        rules = _load_document(
            lambda: self._documents.load_data_rules(product), "DATA_RULES_INVALID", issues
        )
        ok = rules is not None and _check_against(
            lambda: rules.validate_against(spec), "DATA_RULES_MISMATCH", issues
        )
        return rules, ok

    def _flows(
        self, product: str, spec: ApiSpec, issues: list[InspectIssue]
    ) -> tuple[FlowSpec | None, bool]:
        flows = _load_document(lambda: self._documents.load_flows(product), "FLOWS_INVALID", issues)
        ok = flows is not None and _check_against(
            lambda: flows.validate_against(spec), "FLOWS_MISMATCH", issues
        )
        return flows, ok

    def _build_check(
        self,
        spec: ApiSpec,
        plan: tuple[PlannedOperation, ...],
        rules: DataRules | None,
        flows: FlowSpec | None,
    ) -> tuple[tuple[NeedsRule, ...], tuple[str, ...]]:
        consumers = {c.operation for b in flows.bindings for c in b.consumed_by} if flows else set()
        source = self._value_sources(_BUILD_CHECK_SEED, self._clock.now())
        builder = RequestBuilder(
            rules or DataRules(schema_version=1, rules=()), source, _BUILD_CHECK_TAG
        )
        needs: list[NeedsRule] = []
        for item in plan:
            if item.decision != "send" or item.operation_id in consumers:
                continue
            try:
                builder.build(spec.get_operation(item.operation_id))
            except ConfigError as error:
                needs.append(
                    NeedsRule(
                        operation_id=item.operation_id, message=error.message, hint=error.hint
                    )
                )
        return tuple(needs), tuple(sorted(consumers))


def _operation_accounts(
    profile: ProductProfile, plan: tuple[PlannedOperation, ...]
) -> tuple[OperationAccount, ...]:
    return tuple(
        OperationAccount(
            operation_id=item.operation_id,
            account=profile.account_for(item.operation_id, item.method, item.path),
        )
        for item in plan
        if item.decision == "send"
    )


def _failed(issues: list[InspectIssue], code: str) -> bool:
    return any(issue.code == code for issue in issues)


def _info(
    document: DataRules | FlowSpec | None, valid: bool, count: int, unreadable: bool
) -> DocumentInfo:
    # Um arquivo que existe mas não passou na leitura também está presente (e inválido).
    return DocumentInfo(present=document is not None or unreadable, valid=valid, count=count)


def _unused_rules(rules: DataRules | None, spec: ApiSpec) -> tuple[UnusedRule, ...]:
    if rules is None:
        return ()
    return tuple(
        UnusedRule(
            number=index + 1,
            field=rules.rules[index].match.field,
            operation=rules.rules[index].match.operation,
        )
        for index in rules.validate_against(spec)
    )

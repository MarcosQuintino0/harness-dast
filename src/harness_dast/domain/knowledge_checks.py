"""Conferência de recibos contra operação, contrato e configurações atuais."""

from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import (
    Schema,
    flatten_schema,
    split_field_path,
)
from harness_dast.domain.authz_sensitive import classify_field_name
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.knowledge import KnowledgeEffect
from harness_dast.domain.knowledge_evidence import KnowledgeRunEvidence
from harness_dast.domain.knowledge_receipts import KnowledgeFlowUse, KnowledgeRuleUse
from harness_dast.domain.probe_result import ArtifactHashes
from harness_dast.domain.profile import ProductProfile


def ensure_run_matches(
    evidence: KnowledgeRunEvidence, profile: ProductProfile, hashes: ArtifactHashes, version: str
) -> None:
    """Recusa resultado incompleto, de outro contexto ou de fontes diferentes."""
    manifest, probe, run_id = evidence.manifest, evidence.probe, evidence.provenance.run_id
    if (
        manifest.run_id != run_id
        or probe.run_id != run_id
        or manifest.product != profile.product
        or probe.product != profile.product
        or manifest.command != "probe"
        or manifest.status != "completed"
        or manifest.finished_at is None
        or probe.status != "completed"
        or probe.dry_run
        or manifest.hashes != hashes
        or manifest.seed != probe.seed
        or manifest.started_at != probe.started_at
        or len({item.operation_id for item in probe.operations}) != len(probe.operations)
        or manifest.zap_version != version
    ):
        raise ConfigError("Execucao nao corresponde as fontes, motor ou produto atuais.")
    if evidence.provenance.authz_sha256 is not None and (
        evidence.authz_run_id != run_id
        or evidence.authz_product != profile.product
        or evidence.authz_status != "completed"
        or evidence.authz_dry_run is not False
    ):
        raise ConfigError("Artefato authz nao corresponde a execucao concluida.")


def ensure_rule_use(use: KnowledgeRuleUse, rules: DataRules | None, spec: ApiSpec) -> None:
    """Recusa referência que não resolve à mesma regra e operação atuais."""
    if rules is None or use.rule_index >= len(rules.rules) or not spec.has_operation(use.operation):
        raise ConfigError("Recibo de regra nao corresponde aos documentos atuais.")
    operation = spec.get_operation(use.operation)
    if use.location == "body":
        media = operation.request_body.preferred() if operation.request_body else None
        schema = media.body_schema if media else None
        if not _contains_field(schema, use.field):
            raise ConfigError("Campo do recibo nao existe no contrato.")
    elif not (
        any(p.location == use.location and p.name == use.field for p in operation.parameters)
        or (use.location == "path" and use.field in operation.path_placeholders)
    ):
        raise ConfigError("Parametro do recibo nao existe no contrato.")
    resolved = rules.resolve(use.operation, use.location, tuple(use.field.split(".")))
    if (
        resolved is None
        or resolved.index != use.rule_index
        or resolved.rule.generator != use.generator
    ):
        raise ConfigError("Recibo de regra divergente dos documentos atuais.")


def ensure_flow_use(use: KnowledgeFlowUse, flows: FlowSpec | None, spec: ApiSpec) -> None:
    """Recusa referência que não corresponde a um binding atual."""
    if (
        flows is None
        or not spec.has_operation(use.producer)
        or not spec.has_operation(use.consumer)
    ):
        raise ConfigError("Recibo de fluxo nao corresponde aos documentos atuais.")
    if not any(
        binding.produces.operation == use.producer
        and binding.produces.field == use.source_field
        and any(
            c.operation == use.consumer and c.target == (use.target_kind, use.target_field)
            for c in binding.consumed_by
        )
        for binding in flows.bindings
    ):
        raise ConfigError("Recibo de fluxo divergente dos documentos atuais.")


def ensure_effect(use: KnowledgeEffect, profile: ProductProfile, spec: ApiSpec) -> None:
    """Exige conta e operações existentes com métodos apropriados; não autoriza escrita."""
    profile.select_account(use.account)
    if not spec.has_operation(use.write_operation) or not spec.has_operation(use.read_operation):
        raise ConfigError("Receita de efeito cita operacao inexistente.")
    write = spec.get_operation(use.write_operation)
    read = spec.get_operation(use.read_operation)
    if write.method.lower() not in {"post", "put", "patch"} or read.method.lower() != "get":
        raise ConfigError("Receita de efeito usa metodos incompatíveis.")
    media = write.request_body.preferred() if write.request_body else None
    schemas = (media.body_schema if media else None, read.success_schema())
    declared = {field.name for field in profile.authz.mass_assignment_fields}
    if any(
        classify_field_name(name) != "plain"
        or (name not in declared and not any(_contains_field(schema, name) for schema in schemas))
        for name in use.fields
    ):
        raise ConfigError("Campos do efeito nao correspondem ao contrato ou perfil.")


def _contains_field(schema: Schema | None, name: str) -> bool:
    if schema is None:
        return False
    current = schema
    for segment in split_field_path(name):
        current = flatten_schema(current)
        if current.truncated:
            return False
        if current.items is not None:
            current = flatten_schema(current.items)
        if segment not in current.properties:
            return False
        current = current.properties[segment]
    return True

"""Prova observável de receita aplicada e snapshot privado, sem publicar valores."""

import json
from typing import Any

from pydantic import ValidationError

from harness_dast.domain.knowledge import Knowledge
from harness_dast.domain.knowledge_mutation import mutation_key
from harness_dast.domain.mutation_snapshot import MutationSnapshot
from tests.integration.lab_support import LabCli, run_audit
from tests.integration.run_support import record_metrics
from tests.integration.strategy_support import load_artifact


def verify_reuse(cli: LabCli, product: str, mode: str, run_id: str) -> None:
    """Confere eventos reais de leitura e existência de pré-estado seguro persistido."""
    import yaml

    source = (cli.products / product / "knowledge.yml").read_text(encoding="utf-8")
    knowledge = Knowledge.from_data(yaml.safe_load(source))
    rows = run_audit(cli, run_id)
    before = [
        row
        for row in rows
        if row.get("phase") == "result"
        and str(row.get("operation_id", "")).startswith("authz:effect_recipe_before:")
        and row.get("status") == 200
    ]
    after = [
        row
        for row in rows
        if row.get("phase") == "result"
        and str(row.get("operation_id", "")).startswith("authz:effect_recipe_after:")
        and row.get("status") == 200
    ]
    probe = load_artifact(cli, run_id, "probe.json")
    methods = {row["operation_id"]: row["method"] for row in probe["operations"]}
    observed = 0
    for effect in knowledge.effects:
        key = mutation_key(
            product, effect.write_operation, effect.account, methods[effect.write_operation]
        )
        for path in (cli.state / "mutations" / "completed").glob(key + "-*.jsonl"):
            first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
            if first.get("snapshot") is None:
                continue
            try:
                snapshot = MutationSnapshot.model_validate(first["snapshot"])
            except ValidationError:
                raise AssertionError(
                    "Snapshot inválido; não publicar conteúdo do diário."
                ) from None
            if snapshot.source == "observed" and first["previous_state"] == "present":
                observed += 1
    evidence: dict[str, Any] = {
        "product": product,
        "mode": mode,
        "run_id": run_id,
        "observed_rules": len(knowledge.observed_rules),
        "observed_flows": len(knowledge.observed_flows),
        "effects_available": len(knowledge.effects),
        "recipe_before_reads": len(before),
        "recipe_after_reads": len(after),
        "observed_snapshots": observed,
        "snapshot_values_exported": False,
    }
    record_metrics(f"v19-t2-{product}-{mode}-reuse", evidence)
    assert knowledge.provenance is not None
    assert knowledge.observed_rules
    assert knowledge.observed_flows
    if product == "clinica-piloto" and mode == "vulnerable":
        assert knowledge.effects, "Controle de efeito não foi observado no primeiro contexto"
        assert before, "A receita não provocou a leitura atual anterior"
        assert after, "A receita não provocou a releitura atual de comprovação"
        assert observed > 0, "O pré-estado conhecido não chegou ao diário privado"

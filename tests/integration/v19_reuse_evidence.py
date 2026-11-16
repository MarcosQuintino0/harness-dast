"""Prova observável de receita aplicada e snapshot privado, sem publicar valores.

Cada evidência (leitura anterior, escrita, leitura posterior e snapshot do diário) é amarrada à
mesma receita, conta e mutação, na ordem da execução, e só vale dentro do período da rodada.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from harness_dast.domain.knowledge import Knowledge, KnowledgeEffect
from harness_dast.domain.knowledge_mutation import mutation_key
from harness_dast.domain.mutation_snapshot import MutationSnapshot
from tests.integration.lab_support import LabCli, run_audit
from tests.integration.run_support import record_metrics
from tests.integration.strategy_support import load_artifact


@dataclass(frozen=True)
class RecipeTriple:
    """Leitura anterior, escrita e leitura posterior da mesma receita, conta e mutação."""

    before: Mapping[str, Any]
    write: Mapping[str, Any]
    after: Mapping[str, Any]


def _epoch(row: Mapping[str, Any]) -> float:
    return datetime.fromisoformat(str(row["timestamp"])).timestamp()


def _ok(row: Mapping[str, Any], operation_id: str, method: str, account: str) -> bool:
    return (
        row.get("phase") == "result"
        and row.get("operation_id") == operation_id
        and row.get("method") == method
        and row.get("account") == account
    )


def find_recipe_triples(
    rows: Sequence[Mapping[str, Any]], effect: KnowledgeEffect, write_method: str
) -> list[RecipeTriple]:
    """Acha trios anterior < escrita < posterior, sem compartilhar leituras entre escritas.

    Só entram resultados 200 nas leituras e 2xx na escrita, da conta da receita. A leitura anterior
    é a mais recente depois da escrita anterior da mesma operação e conta; a posterior é a
    primeira antes da escrita seguinte.
    """
    account = effect.account
    results = sorted((row for row in rows if row.get("phase") == "result"), key=lambda r: r["seq"])
    write_id = f"authz:{effect.write_operation}"
    before_id = f"authz:effect_recipe_before:{effect.read_operation}"
    after_id = f"authz:effect_recipe_after:{effect.read_operation}"
    writes = [
        row
        for row in results
        if _ok(row, write_id, write_method, account)
        and isinstance(row.get("status"), int)
        and 200 <= row["status"] < 300
    ]
    reads_before = [
        row for row in results if _ok(row, before_id, "GET", account) and row.get("status") == 200
    ]
    reads_after = [
        row for row in results if _ok(row, after_id, "GET", account) and row.get("status") == 200
    ]
    triples: list[RecipeTriple] = []
    previous_seq = 0
    for index, write in enumerate(writes):
        next_seq = writes[index + 1]["seq"] if index + 1 < len(writes) else float("inf")
        before = [r for r in reads_before if previous_seq < r["seq"] < write["seq"]]
        after = [r for r in reads_after if write["seq"] < r["seq"] < next_seq]
        previous_seq = write["seq"]
        if before and after:
            triples.append(RecipeTriple(before[-1], write, after[0]))
    return triples


def _observed_snapshot_files(
    completed: Path, key: str, start: float, end: float
) -> list[MutationSnapshot]:
    """Snapshots observados e válidos de arquivos arquivados dentro da janela da rodada."""
    found: list[MutationSnapshot] = []
    for path in completed.glob(key + "-*.jsonl"):
        if not start <= path.stat().st_mtime <= end:
            continue
        first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        if first.get("snapshot") is None:
            continue
        try:
            snapshot = MutationSnapshot.model_validate(first["snapshot"])
        except ValidationError:
            raise AssertionError("Snapshot inválido; não publicar conteúdo do diário.") from None
        if snapshot.source == "observed" and first.get("previous_state") == "present":
            found.append(snapshot)
    return found


def count_bound_evidence(
    rows: Sequence[Mapping[str, Any]],
    effects: Sequence[KnowledgeEffect],
    methods: Mapping[str, str],
    product: str,
    completed: Path,
) -> dict[str, int]:
    """Conta trios completos e, para cada um, os snapshots observados da mesma mutação e período."""
    triples = 0
    snapshots = 0
    for effect in effects:
        method = methods[effect.write_operation]
        key = mutation_key(product, effect.write_operation, effect.account, method)
        for triple in find_recipe_triples(rows, effect, method):
            triples += 1
            start = _epoch(triple.write)
            end = _epoch(triple.after)
            if _observed_snapshot_files(completed, key, start, end):
                snapshots += 1
    return {"recipe_triples": triples, "observed_snapshots": snapshots}


def recipe_absence(rows: Sequence[Mapping[str, Any]]) -> str:
    """Aceita a lacuna só se a receita nunca foi tentada; leitura de receita sem trio reprova."""
    attempted = [
        row
        for row in rows
        if row.get("phase") == "result"
        and str(row.get("operation_id", "")).startswith("authz:effect_recipe_")
    ]
    if attempted:
        raise AssertionError(
            f"{len(attempted)} leituras de receita sem trio completo; a prova não pode ser lacuna"
        )
    return "never_attempted"


def verify_reuse(cli: LabCli, product: str, mode: str, run_id: str) -> None:
    """Confere trio de leituras e escrita da receita e o snapshot da mesma mutação."""
    import yaml

    source = (cli.products / product / "knowledge.yml").read_text(encoding="utf-8")
    knowledge = Knowledge.from_data(yaml.safe_load(source))
    rows = run_audit(cli, run_id)
    probe = load_artifact(cli, run_id, "probe.json")
    methods = {row["operation_id"]: row["method"] for row in probe["operations"]}
    counts = count_bound_evidence(
        rows, knowledge.effects, methods, product, cli.state / "mutations" / "completed"
    )
    evidence: dict[str, Any] = {
        "product": product,
        "mode": mode,
        "run_id": run_id,
        "observed_rules": len(knowledge.observed_rules),
        "observed_flows": len(knowledge.observed_flows),
        "effects_available": len(knowledge.effects),
        "recipe_triples": counts["recipe_triples"],
        "observed_snapshots": counts["observed_snapshots"],
        "snapshot_values_exported": False,
    }
    record_metrics(f"v19-t2-{product}-{mode}-reuse", evidence)
    assert knowledge.provenance is not None
    assert knowledge.observed_rules
    assert knowledge.observed_flows
    if product == "clinica-piloto" and mode == "vulnerable":
        assert knowledge.effects, "Controle de efeito não foi observado no primeiro contexto"
        # Lacuna de prova conhecida: a receita capturada vem do par criado (conta que só cria) e
        # só se aplica a tarefa de atribuição em massa da mesma operação e conta sem leitor. No
        # laboratório não há tal tarefa. A lacuna só vale se a receita nunca foi tentada.
        if counts["recipe_triples"] == 0:
            record_metrics(
                f"v19-t2-{product}-{mode}-recipe-gap",
                {"recipe_applied": False, "reason": recipe_absence(rows)},
            )
        else:
            assert counts["observed_snapshots"] > 0, (
                "O pré-estado conhecido não chegou ao diário privado da mesma mutação"
            )

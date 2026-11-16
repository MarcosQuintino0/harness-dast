"""Revisão independente das provas para captura de conhecimento."""

from pathlib import Path
from typing import Literal

import pytest

from harness_dast.domain.errors import ConfigError
from tests.unit.application.test_knowledge_observations import EvidenceStore, _prepare


@pytest.mark.parametrize("tamper", ["alias", "rule_index", "generator", "operation"])
def test_v19_independent_rejects_forged_receipt_without_saving(
    tmp_path: Path, tamper: Literal["alias", "rule_index", "generator", "operation"]
) -> None:
    capture, evidence, _ = _prepare(tmp_path)
    operations = list(evidence.probe.operations)
    target = operations[0]
    assert target.rule_uses
    if tamper == "alias":
        changed = target.model_copy(update={"account": "other-account"})
    else:
        name, value = {
            "rule_index": ("rule_index", 9),
            "generator": ("generator", "wrong"),
            "operation": ("operation", "other"),
        }[tamper]
        forged = target.rule_uses[0].model_copy(update={name: value})
        changed = target.model_copy(update={"rule_uses": (forged,)})
    operations[0] = changed
    store = capture._runs
    assert isinstance(store, EvidenceStore)
    store.evidence = evidence.model_copy(
        update={"probe": evidence.probe.model_copy(update={"operations": tuple(operations)})}
    )

    with pytest.raises(ConfigError):
        capture.execute("agenda", evidence.provenance.run_id)

    assert not (tmp_path / "agenda" / "knowledge.captured.yml").exists()


@pytest.mark.parametrize("tamper", ["other_run", "stale_hash"])
def test_v19_independent_rejects_wrong_run_or_stale_hash_before_capture(
    tmp_path: Path, tamper: Literal["other_run", "stale_hash"]
) -> None:
    capture, evidence, _ = _prepare(tmp_path)
    if tamper == "other_run":
        manifest = evidence.manifest.model_copy(update={"run_id": "other-run"})
    else:
        hashes = evidence.manifest.hashes.model_copy(update={"openapi": "0" * 64})
        manifest = evidence.manifest.model_copy(update={"hashes": hashes})
    store = capture._runs
    assert isinstance(store, EvidenceStore)
    store.evidence = evidence.model_copy(update={"manifest": manifest})

    with pytest.raises(ConfigError):
        capture.execute("agenda", evidence.provenance.run_id)

    assert not (tmp_path / "agenda" / "knowledge.captured.yml").exists()

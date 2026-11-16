"""Verificador da T2: amarra leitura anterior, escrita, leitura posterior e snapshot."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from harness_dast.domain.knowledge import KnowledgeEffect
from harness_dast.domain.knowledge_mutation import mutation_key
from tests.integration.v19_reuse_evidence import (
    count_bound_evidence,
    find_recipe_triples,
    recipe_absence,
)

_BASE = datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC)
_SNAPSHOT = {"field": "balance", "value": 3, "source": "observed"}


def _row(
    seq: int, op: str, method: str, account: str = "pac_a", status: int = 200
) -> dict[str, Any]:
    return {
        "seq": seq,
        "phase": "result",
        "timestamp": (_BASE + timedelta(seconds=seq)).isoformat(),
        "operation_id": op,
        "method": method,
        "account": account,
        "status": status,
    }


def _effect(account: str = "pac_a") -> KnowledgeEffect:
    return KnowledgeEffect(
        write_operation="upd",
        read_operation="rd",
        account=account,
        fields=("balance",),
        proof="readback_verified",
    )


def _good(start: int = 1, account: str = "pac_a") -> list[dict[str, Any]]:
    return [
        _row(start, "authz:effect_recipe_before:rd", "GET", account),
        _row(start + 1, "authz:upd", "PUT", account),
        _row(start + 2, "authz:effect_recipe_after:rd", "GET", account),
    ]


def _journal(completed: Path, account: str, seq: int) -> Path:
    completed.mkdir(parents=True)
    key = mutation_key("prod", "upd", account, "PUT")
    path = completed / f"{key}-x.jsonl"
    path.write_text(
        json.dumps({"intent": "mutation", "previous_state": "present", "snapshot": _SNAPSHOT})
        + "\n"
        + json.dumps({"outcome": "succeeded"})
        + "\n",
        encoding="utf-8",
    )
    stamp = (_BASE + timedelta(seconds=seq)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def test_trio_na_ordem_certa_e_snapshot_da_mesma_mutacao_contam(tmp_path: Path) -> None:
    _journal(tmp_path / "c", "pac_a", 2)

    counts = count_bound_evidence(_good(), (_effect(),), {"upd": "PUT"}, "prod", tmp_path / "c")

    assert counts == {"recipe_triples": 1, "observed_snapshots": 1}


def test_leituras_de_outra_conta_nao_formam_trio() -> None:
    rows = [_row(1, "authz:effect_recipe_before:rd", "GET", "pac_b"), *_good(2)[1:]]

    assert find_recipe_triples(rows, _effect(), "PUT") == []


def test_leitura_posterior_antes_da_escrita_nao_forma_trio() -> None:
    rows = [
        _row(1, "authz:effect_recipe_before:rd", "GET"),
        _row(2, "authz:effect_recipe_after:rd", "GET"),
        _row(3, "authz:upd", "PUT"),
    ]

    assert find_recipe_triples(rows, _effect(), "PUT") == []


def test_escrita_com_falha_nao_forma_trio() -> None:
    rows = _good()
    rows[1]["status"] = 500

    assert find_recipe_triples(rows, _effect(), "PUT") == []


def test_leitura_anterior_nao_e_compartilhada_entre_duas_escritas() -> None:
    rows = [*_good(1), _row(4, "authz:upd", "PUT"), _row(5, "authz:effect_recipe_after:rd", "GET")]

    assert len(find_recipe_triples(rows, _effect(), "PUT")) == 1


def test_snapshot_de_outra_conta_nao_conta(tmp_path: Path) -> None:
    _journal(tmp_path / "c", "pac_b", 2)

    counts = count_bound_evidence(_good(), (_effect(),), {"upd": "PUT"}, "prod", tmp_path / "c")

    assert counts == {"recipe_triples": 1, "observed_snapshots": 0}


def test_snapshot_de_rodada_anterior_nao_conta(tmp_path: Path) -> None:
    _journal(tmp_path / "c", "pac_a", -3600)

    counts = count_bound_evidence(_good(), (_effect(),), {"upd": "PUT"}, "prod", tmp_path / "c")

    assert counts == {"recipe_triples": 1, "observed_snapshots": 0}


def test_snapshot_da_restauracao_depois_da_leitura_posterior_nao_conta(tmp_path: Path) -> None:
    # A restauração grava o seu próprio snapshot depois da leitura posterior (seq 3).
    _journal(tmp_path / "c", "pac_a", 5)

    counts = count_bound_evidence(_good(), (_effect(),), {"upd": "PUT"}, "prod", tmp_path / "c")

    assert counts == {"recipe_triples": 1, "observed_snapshots": 0}


def test_snapshot_gravado_antes_da_escrita_nao_conta(tmp_path: Path) -> None:
    _journal(tmp_path / "c", "pac_a", 1)

    counts = count_bound_evidence(_good(), (_effect(),), {"upd": "PUT"}, "prod", tmp_path / "c")

    assert counts == {"recipe_triples": 1, "observed_snapshots": 0}


def test_lacuna_so_vale_quando_a_receita_nunca_foi_tentada() -> None:
    rows = [_row(1, "authz:upd", "PUT"), _row(2, "authz:pair:x", "GET")]

    assert recipe_absence(rows) == "never_attempted"


def test_leitura_de_receita_sem_trio_reprova_a_prova() -> None:
    import pytest

    rows = [_row(1, "authz:effect_recipe_before:rd", "GET"), _row(2, "authz:upd", "PUT")]

    with pytest.raises(AssertionError, match="sem trio"):
        recipe_absence(rows)

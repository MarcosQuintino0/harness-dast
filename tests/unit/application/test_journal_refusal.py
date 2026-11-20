"""Recusa do portão antes de qualquer byte da mutação não deixa pendência no diário."""

from pathlib import Path

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.domain.knowledge_mutation import mutation_key
from tests.fakes.negative_rig import CREATE, NegativeRig
from tests.unit.application.authz.test_created_pair import execute, make_rig


class WindowClosesAfterReservation:
    """Janela que fecha logo depois que o diário reservou a mutação, antes do envio."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def engaged(self) -> bool:
        return any(self._directory.glob("*.jsonl"))


def test_negative_janela_fechada_antes_do_envio_libera_a_reserva(tmp_path: Path) -> None:
    from harness_dast.application.negative import NegativeRequest

    rig = NegativeRig(allow_writes=True)
    probe = rig.seed(CREATE)
    journal = FileMutationJournal(tmp_path)
    service = rig.negative(WindowClosesAfterReservation(tmp_path), journal)
    result = service.execute(NegativeRequest(product="agenda", run_id=probe.run_id))

    assert result.status == "stopped_window"
    assert rig.sent("POST") == []
    assert list(tmp_path.glob("*.jsonl")) == []
    key = mutation_key("agenda", CREATE.operation_id, CREATE.account, "POST")
    journal.begin(key, "unknown")


def test_authz_janela_fechada_antes_do_envio_libera_a_reserva(tmp_path: Path) -> None:
    rig = make_rig("api/widgets", exposed=True)
    journal = FileMutationJournal(tmp_path)

    result = execute(
        rig,
        "api/widgets",
        journal=journal,
        kill_switch=WindowClosesAfterReservation(tmp_path),
    )

    assert result.status == "stopped_window"
    assert not [r for r in rig.target.requests if r.operation_id == "authz:pair:createSynthetic"]
    assert list(tmp_path.glob("*.jsonl")) == []

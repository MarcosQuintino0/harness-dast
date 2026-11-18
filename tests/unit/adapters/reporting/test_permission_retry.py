"""Nova tentativa limitada para arquivo momentaneamente preso."""

from pathlib import Path

import pytest

from harness_dast.adapters.reporting.permission_retry import (
    REPLACE_ATTEMPTS,
    retry_on_permission_error,
)
from harness_dast.adapters.reporting.wait_files import FileWaitReader

RUN_ID = "2026-11-13T10-00-00Z-demo-aaaa"


def test_retry_devolve_o_resultado_depois_de_recusas_passageiras() -> None:
    pauses: list[float] = []
    refusals = [2]

    def action() -> str:
        if refusals[0] > 0:
            refusals[0] -= 1
            raise PermissionError("preso")
        return "ok"

    assert retry_on_permission_error(action, pauses.append) == "ok"
    assert len(pauses) == 2


def test_retry_desiste_no_limite_e_sem_pausa_nem_repeticao_para_outro_erro() -> None:
    pauses: list[float] = []
    calls = [0]

    def locked() -> None:
        calls[0] += 1
        raise PermissionError("preso")

    with pytest.raises(PermissionError):
        retry_on_permission_error(locked, pauses.append)
    assert calls[0] == REPLACE_ATTEMPTS
    assert len(pauses) == REPLACE_ATTEMPTS - 1
    assert max(pauses) <= 0.2

    other = [0]

    def broken() -> None:
        other[0] += 1
        raise FileNotFoundError("ausente")

    with pytest.raises(FileNotFoundError):
        retry_on_permission_error(broken, pauses.append)
    assert other[0] == 1


def test_leitor_do_wait_tolera_arquivo_preso_e_le_quando_libera(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / RUN_ID
    directory.mkdir()
    (directory / "scan-progress.json").write_text(
        f'{{"run_id": "{RUN_ID}", "phase": "scanning", "status": "running", "index": 1,'
        ' "total": 2, "updated_at": "t"}',
        encoding="utf-8",
    )
    real_read = Path.read_text
    refusals = [3]

    def flaky(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "scan-progress.json" and refusals[0] > 0:
            refusals[0] -= 1
            raise PermissionError("preso")
        return real_read(self, *args, **kwargs)  # type: ignore[arg-type]  # repassa os argumentos

    monkeypatch.setattr(Path, "read_text", flaky)
    reader = FileWaitReader(tmp_path, lambda: None, sleep=lambda _s: None)

    progress = reader._progress(directory, RUN_ID)

    assert progress is not None
    assert progress.phase == "scanning"


def test_leitor_do_wait_sem_andamento_quando_arquivo_segue_preso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / RUN_ID
    directory.mkdir()
    (directory / "scan-progress.json").write_text("{}", encoding="utf-8")

    def locked(self: Path, *args: object, **kwargs: object) -> str:
        raise PermissionError("preso")

    monkeypatch.setattr(Path, "read_text", locked)
    reader = FileWaitReader(tmp_path, lambda: None, sleep=lambda _s: None)

    assert reader._progress(directory, RUN_ID) is None

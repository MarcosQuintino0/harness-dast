"""Campos `signals` e `signal_skip` da trilha de auditoria e da leitura dela (ADR 0049)."""

import io
import json
from pathlib import Path

import pytest

from harness_dast.adapters.scope_proxy.audit import AuditLog, AuditRecord
from harness_dast.adapters.scope_proxy.audit_reader import FileProxyAudit
from harness_dast.domain.errors import ConfigError


def record(**changes: object) -> AuditRecord:
    data: dict[str, object] = {
        "ts": "2026-11-13T12:00:00.000+00:00",
        "run_id": "2026-11-13T00-00-00Z-lab-0001",
        "method": "GET",
        "scheme": "https",
        "host": "api.exemplo.com",
        "port": 443,
        "path": "/api/users",
        "query_params": ("page",),
        "decision": "allow",
        "reason": "allowed",
    }
    data.update(changes)
    return AuditRecord.model_validate(data)


def _line(**changes: object) -> str:
    base = {
        "ts": "2026-11-13T10:00:00.000+00:00",
        "method": "GET",
        "decision": "allow",
        "reason": "allowed",
        "path": "/x",
    }
    return json.dumps({**base, **changes})


def test_write_inclui_signals_e_signal_skip_so_quando_existem() -> None:
    file = io.StringIO()
    log = AuditLog(file=file, stdout=io.StringIO(), on_failure=lambda: None)

    log.write(record(status=500, signals=("sql_error", "stack_trace_java")))
    log.write(record(status=200, signal_skip="type"))
    log.write(record(status=200))

    first, second, third = (json.loads(line) for line in file.getvalue().splitlines())
    assert first["signals"] == ["sql_error", "stack_trace_java"]
    assert "signal_skip" not in first
    assert second["signal_skip"] == "type"
    assert "signals" not in second
    assert "signals" not in third
    assert "signal_skip" not in third


def test_registro_recusa_categoria_que_nao_e_do_catalogo() -> None:
    with pytest.raises(ValueError, match="signals"):
        record(signals=("senha_do_banco_vazada",))


def test_registro_recusa_motivo_de_pulo_desconhecido() -> None:
    with pytest.raises(ValueError, match="signal_skip"):
        record(signal_skip="ORA-00933 texto do corpo")


def test_registro_continua_recusando_campo_desconhecido() -> None:
    with pytest.raises(ValueError, match="body"):
        record(body="ORA-00933")


def test_write_so_grava_categorias_nunca_o_texto_do_corpo() -> None:
    file = io.StringIO()
    log = AuditLog(file=file, stdout=io.StringIO(), on_failure=lambda: None)

    log.write(record(status=500, signals=("sql_error",)))

    assert "ORA-" not in file.getvalue()


def test_leitor_le_status_caminho_e_sinais_da_linha(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text(
        _line(path="/api/x", status=500, query_params=["q"], signals=["sql_error"])
        + "\n"
        + _line(status=200, signal_skip="encoding")
        + "\n"
    )

    first, second = FileProxyAudit(path).rows()

    assert (first.path, first.status, first.query_params) == ("/api/x", 500, ("q",))
    assert first.signals == ("sql_error",)
    assert second.signal_skip == "encoding"
    assert second.signals == ()


def test_leitor_le_linha_antiga_sem_os_campos_novos(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text(_line() + "\n")

    (row,) = FileProxyAudit(path).rows()

    assert row.status is None
    assert row.signals == ()
    assert row.signal_skip is None
    assert row.query_params == ()


@pytest.mark.parametrize(
    "changes",
    [{"signals": "sql_error"}, {"signals": [1]}, {"status": "ok"}, {"query_params": 3}],
)
def test_leitor_recusa_campo_novo_malformado(tmp_path: Path, changes: dict[str, object]) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text(_line(**changes) + "\n")

    with pytest.raises(ConfigError, match="ilegível"):
        FileProxyAudit(path).rows()

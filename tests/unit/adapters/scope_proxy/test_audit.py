import io
import json
from typing import TextIO

import pytest

from harness_dast.adapters.scope_proxy.audit import AuditLog, AuditRecord, describe_target

SEGREDO = "tok3n-SECRETO-123"


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


def test_describe_target_guarda_so_os_nomes_dos_parametros() -> None:
    url = f"https://api.exemplo.com/api/users?token={SEGREDO}&page=2&vazio="

    path, names = describe_target("GET", url, "/api/users", f"token={SEGREDO}&page=2&vazio=")

    assert path == "/api/users"
    assert names == ["token", "page", "vazio"]
    assert SEGREDO not in json.dumps([path, names])


def test_describe_target_nao_vaza_valor_de_consulta_sem_igual() -> None:
    _, names = describe_target("GET", "https://a.exemplo.com/x", "/x", "a=1&b&c=%20")

    assert names == ["a", "b", "c"]


def test_describe_target_normaliza_o_caminho_decodificado() -> None:
    path, _ = describe_target("GET", "https://a.exemplo.com/a%20b/c", "/a%20b/c", "")

    assert path == "/a b/c"


def test_describe_target_escapa_e_trunca_caminho_malformado() -> None:
    raw = "/x;y/" + "z" * 500 + "\n\x1b[31m"

    path, _ = describe_target("GET", "https://a.exemplo.com" + raw, raw, "")

    assert len(path) <= 120
    assert "\n" not in path
    assert "\x1b" not in path


def test_describe_target_limita_quantidade_de_nomes() -> None:
    query = "&".join(f"p{i}=1" for i in range(500))

    _, names = describe_target("GET", "https://a.exemplo.com/x", "/x", query)

    assert len(names) == 50


def test_write_emite_uma_linha_json_no_arquivo_e_na_saida() -> None:
    file, out = io.StringIO(), io.StringIO()
    log = AuditLog(file=file, stdout=out, on_failure=lambda: None)

    log.write(record(status=200, bytes=12, duration_ms=3))

    assert file.getvalue() == out.getvalue()
    assert file.getvalue().count("\n") == 1
    data = json.loads(file.getvalue())
    assert data["host"] == "api.exemplo.com"
    assert data["query_params"] == ["page"]
    assert set(data) == {
        "ts", "run_id", "method", "scheme", "host", "port", "path", "query_params",
        "decision", "reason", "status", "bytes", "duration_ms", "waited_ms",
    }  # fmt: skip


def test_write_nao_tem_campo_para_cabecalhos_nem_corpo() -> None:
    with pytest.raises(ValueError, match="headers"):
        record(headers={"Authorization": "Bearer x"})


def test_write_aciona_on_failure_quando_a_gravacao_falha() -> None:
    class Broken(io.StringIO):
        def write(self, text: str, /) -> int:
            raise OSError("disco cheio")

    failures: list[str] = []
    stream: TextIO = Broken()
    log = AuditLog(file=stream, stdout=io.StringIO(), on_failure=lambda: failures.append("x"))

    log.write(record())

    assert failures == ["x"]

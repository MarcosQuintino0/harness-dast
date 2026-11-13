import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from harness_dast.adapters.scope_proxy.decision import ALLOW, Reason
from harness_dast.adapters.scope_proxy.engine import ScopeProxyEngine
from harness_dast.adapters.scope_proxy.policy import KILL_FLAG_NAME
from tests.unit.adapters.scope_proxy.helpers import make_policy

START = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


class Clocks:
    def __init__(self) -> None:
        self.wall = START
        self.mono = 1000.0

    def now(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.mono


class Rig:
    def __init__(self, tmp_path: Path, **policy: object) -> None:
        self.clocks = Clocks()
        self.dir = tmp_path
        self.audit = io.StringIO()
        self.stdout = io.StringIO()
        self.engine = ScopeProxyEngine(
            make_policy(**policy),
            policy_dir=tmp_path,
            audit_file=self.audit,
            stdout=self.stdout,
            now=self.clocks.now,
            monotonic=self.clocks.monotonic,
        )

    def lines(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.audit.getvalue().splitlines()]


def request(rig: Rig, **overrides: object) -> Reason:
    args: dict[str, object] = {
        "method": "GET",
        "url": "https://api.exemplo.com/api/users",
        "host_header": "api.exemplo.com",
        "wants_upgrade": False,
    }
    args.update(overrides)
    return rig.engine.check_request(**args).reason  # type: ignore[arg-type]  # dict heterogêneo de teste


def test_check_request_permite_requisicao_dentro_do_escopo(tmp_path: Path) -> None:
    assert request(Rig(tmp_path)) is Reason.ALLOWED


def test_check_request_permite_host_header_com_porta_explicita_igual_a_padrao(
    tmp_path: Path,
) -> None:
    assert request(Rig(tmp_path), host_header="API.exemplo.com:443") is Reason.ALLOWED


@pytest.mark.parametrize("header", [None, "", "evil.example", "api.exemplo.com:8443", "a@b"])
def test_check_request_recusa_host_header_que_nao_confere_com_a_url(
    tmp_path: Path, header: str | None
) -> None:
    assert request(Rig(tmp_path), host_header=header) is Reason.HOST_HEADER_MISMATCH


def test_check_request_recusa_upgrade(tmp_path: Path) -> None:
    assert request(Rig(tmp_path), wants_upgrade=True) is Reason.UPGRADE_REFUSED


def test_check_request_da_o_motivo_do_scope_guard_mesmo_com_host_header_errado(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path)

    assert (
        request(rig, url="https://api.exemplo.com/fora", host_header="x") is Reason.PATH_NOT_ALLOWED
    )


def test_check_request_e_check_connect_negam_depois_do_arquivo_sinal(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    assert request(rig) is Reason.ALLOWED

    (tmp_path / KILL_FLAG_NAME).touch()

    assert request(rig) is Reason.KILL_SWITCH
    assert rig.engine.check_connect("api.exemplo.com", 443).reason is Reason.KILL_SWITCH
    assert rig.engine.recheck_after_wait().reason is Reason.KILL_SWITCH


def test_check_request_nega_depois_do_prazo_da_politica(tmp_path: Path) -> None:
    rig = Rig(tmp_path, not_after="2026-11-13T12:10:00Z")
    assert request(rig) is Reason.ALLOWED

    rig.clocks.wall = START + timedelta(minutes=10)

    assert request(rig) is Reason.RUN_EXPIRED


def test_check_request_nega_depois_da_duracao_maxima(tmp_path: Path) -> None:
    rig = Rig(tmp_path)  # max_duration_minutes = 60

    rig.clocks.wall = START + timedelta(minutes=61)

    assert request(rig) is Reason.RUN_EXPIRED


def test_check_connect_decide_por_host_e_porta(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    assert rig.engine.check_connect("api.exemplo.com", 443) == ALLOW
    assert rig.engine.check_connect("api.exemplo.com", 22).allowed is False
    assert rig.engine.check_connect("outro.com", 443).allowed is False


def test_reserve_slot_aplica_a_taxa_da_politica_e_a_fila(tmp_path: Path) -> None:
    rig = Rig(tmp_path, max_queued_requests=2)  # 10 req/s

    delays = [rig.engine.reserve_slot() for _ in range(3)]

    assert delays[0] == 0
    assert delays[1] == pytest.approx(0.1)
    assert delays[2] is None


def test_check_destination_so_aceita_endereco_interno_com_allow_local(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    assert rig.engine.check_destination("vampi", 5000, ["172.18.0.5"]).allowed is True
    # Mesmo host, outra porta: a regra com allow_local não vale para ela.
    assert rig.engine.check_destination("vampi", 5001, ["172.18.0.5"]).allowed is False
    # Host público da lista não tem allow_local.
    assert rig.engine.check_destination("api.exemplo.com", 443, ["10.0.0.5"]).allowed is False
    assert rig.engine.check_destination("api.exemplo.com", 443, ["93.184.216.34"]).allowed is True


def test_check_destination_recusa_metadados_mesmo_com_allow_local(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    assert rig.engine.check_destination("vampi", 5000, ["169.254.169.254"]).allowed is False


def test_tls_verify_upstream_vem_da_politica(tmp_path: Path) -> None:
    assert Rig(tmp_path).engine.tls_verify_upstream is True


def test_log_grava_nomes_de_parametros_e_nunca_valores(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    rig.engine.log(
        method="GET",
        url="https://api.exemplo.com/api/users?token=SEGREDO123",
        scheme="https",
        at=START,
        host="api.exemplo.com",
        port=443,
        raw_path="/api/users",
        raw_query="token=SEGREDO123",
        verdict=ALLOW,
        status=200,
        size=10,
        duration_ms=5,
    )

    assert "SEGREDO123" not in rig.audit.getvalue()
    assert "SEGREDO123" not in rig.stdout.getvalue()
    line = rig.lines()[0]
    assert line["query_params"] == ["token"]
    assert line["run_id"] == "2026-11-13T00-00-00Z-lab-0001"
    assert line["decision"] == "allow"
    assert line["ts"] == "2026-11-13T12:00:00.000+00:00"


def test_falha_na_auditoria_trava_a_execucao(tmp_path: Path) -> None:
    class Broken(io.StringIO):
        def write(self, text: str, /) -> int:
            raise OSError("disco cheio")

    clocks = Clocks()
    engine = ScopeProxyEngine(
        make_policy(),
        policy_dir=tmp_path,
        audit_file=Broken(),
        stdout=io.StringIO(),
        now=clocks.now,
        monotonic=clocks.monotonic,
    )

    engine.log(
        method="GET",
        url="https://api.exemplo.com/api/users",
        scheme="https",
        at=START,
        host="api.exemplo.com",
        port=443,
        raw_path="/api/users",
        raw_query="",
        verdict=ALLOW,
    )

    assert engine.check_connect("api.exemplo.com", 443).reason is Reason.AUDIT_FAILURE

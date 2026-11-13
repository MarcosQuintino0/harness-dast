import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from harness_dast.adapters.scope_proxy.policy import (
    MAX_POLICY_BYTES,
    deadline_of,
    load_policy,
    parse_policy,
)
from harness_dast.domain.errors import ConfigError
from tests.unit.adapters.scope_proxy.helpers import BASE_POLICY, make_policy, policy_data


def dump(data: dict[str, Any]) -> bytes:
    return json.dumps(data).encode()


def test_parse_policy_aceita_politica_valida() -> None:
    policy = make_policy()

    assert policy.run_id == "2026-11-13T00-00-00Z-lab-0001"
    assert policy.tls_verify_upstream is True
    assert policy.scope.allow[0].host == "api.exemplo.com"
    assert policy.limits.requests_per_second == 10


def test_load_policy_levanta_config_error_quando_arquivo_nao_existe(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Não foi possível ler"):
        load_policy(tmp_path / "policy.json")


def test_load_policy_le_arquivo_valido(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_bytes(dump(BASE_POLICY))

    assert load_policy(path).run_id.endswith("lab-0001")


def test_load_policy_recusa_arquivo_grande_demais(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_bytes(b" " * (MAX_POLICY_BYTES + 1))

    with pytest.raises(ConfigError, match="passa de"):
        load_policy(path)


@pytest.mark.parametrize(
    "raw",
    [b"", b"{", b"[]", b'"texto"', b"\xff\xfe", b'{"a": NaN}', b'{"a": Infinity}'],
)
def test_parse_policy_recusa_json_malformado_ou_nao_objeto(raw: bytes) -> None:
    with pytest.raises(ConfigError):
        parse_policy(raw)


def test_parse_policy_recusa_chave_repetida() -> None:
    # Um parser comum ficaria com o último valor e um revisor leria o primeiro.
    raw = dump(BASE_POLICY).replace(b'"deny_paths"', b'"deny_paths": [], "deny_paths"')

    with pytest.raises(ConfigError, match="chave repetida"):
        parse_policy(raw)


@pytest.mark.parametrize("campo", ["schema_version", "run_id", "scope", "limits", "not_after"])
def test_parse_policy_recusa_campo_obrigatorio_ausente(campo: str) -> None:
    data = copy.deepcopy(BASE_POLICY)
    del data[campo]

    with pytest.raises(ConfigError, match=campo):
        parse_policy(dump(data))


@pytest.mark.parametrize("extra", [{"allow_all": True}, {"scope_extra": 1}])
def test_parse_policy_recusa_campo_desconhecido_no_topo(extra: dict[str, Any]) -> None:
    with pytest.raises(ConfigError, match="Extra inputs"):
        parse_policy(dump(policy_data(**extra)))


def test_parse_policy_recusa_campo_desconhecido_dentro_da_regra() -> None:
    data = policy_data()
    data["scope"]["allow"][0]["any_path"] = True

    with pytest.raises(ConfigError, match="Extra inputs"):
        parse_policy(dump(data))


@pytest.mark.parametrize("version", [0, 2, "1", True, 1.0, None])
def test_parse_policy_recusa_schema_version_diferente_de_1(version: object) -> None:
    with pytest.raises(ConfigError, match="schema_version"):
        parse_policy(dump(policy_data(schema_version=version)))


@pytest.mark.parametrize(
    "run_id", ["", "x", "../../etc", "2026-11-13T00-00-00Z-lab", "2026-13-40T00-00-00Z-lab-0001"]
)
def test_parse_policy_recusa_run_id_fora_do_formato(run_id: str) -> None:
    with pytest.raises(ConfigError, match="run_id"):
        parse_policy(dump(policy_data(run_id=run_id)))


@pytest.mark.parametrize("not_after", ["2030-01-01T00:00:00", "2030-01-01", "amanhã", 1893456000])
def test_parse_policy_recusa_not_after_sem_fuso_ou_invalido(not_after: object) -> None:
    with pytest.raises(ConfigError, match="not_after"):
        parse_policy(dump(policy_data(not_after=not_after)))


@pytest.mark.parametrize(
    "host",
    ["*", "*.exemplo.com", "api.exemplo.com/api", "user@exemplo.com", "api.exemplo.com:8443"],
)
def test_parse_policy_recusa_host_que_alargaria_o_escopo(host: str) -> None:
    data = policy_data()
    data["scope"]["allow"][0]["host"] = host

    with pytest.raises(ConfigError, match="host"):
        parse_policy(dump(data))


@pytest.mark.parametrize("paths", [["/api/*x"], ["api"], [], ["/a/../b"], ["/a;b"]])
def test_parse_policy_recusa_caminho_invalido_ou_vazio(paths: list[str]) -> None:
    data = policy_data()
    data["scope"]["allow"][0]["paths"] = paths

    with pytest.raises(ConfigError, match="paths"):
        parse_policy(dump(data))


def test_parse_policy_recusa_escopo_sem_regra_de_permissao() -> None:
    data = policy_data()
    data["scope"]["allow"] = []

    with pytest.raises(ConfigError, match="allow"):
        parse_policy(dump(data))


def test_parse_policy_recusa_host_local_sem_allow_local() -> None:
    data = policy_data()
    data["scope"]["allow"][1]["allow_local"] = False

    with pytest.raises(ConfigError, match="allow_local"):
        parse_policy(dump(data))


@pytest.mark.parametrize(
    "limits",
    [
        {"requests_per_second": 0, "max_duration_minutes": 60, "zap_threads_per_host": 2},
        {"requests_per_second": 5000, "max_duration_minutes": 60, "zap_threads_per_host": 2},
        {"requests_per_second": 10, "max_duration_minutes": 100000, "zap_threads_per_host": 2},
        {"requests_per_second": "10", "max_duration_minutes": 60, "zap_threads_per_host": 2},
        {"requests_per_second": 10, "max_duration_minutes": 60},
    ],
)
def test_parse_policy_recusa_limites_fora_do_teto(limits: dict[str, Any]) -> None:
    with pytest.raises(ConfigError, match="limits"):
        parse_policy(dump(policy_data(limits=limits)))


def test_parse_policy_recusa_tls_sem_verificacao_para_alvo_nao_local() -> None:
    # Desligar a verificação de certificado só vale para laboratório; com um host público
    # na lista seria aceitar certificado falso em ambiente real.
    with pytest.raises(ConfigError, match="allow_local"):
        parse_policy(dump(policy_data(tls_verify_upstream=False)))


def test_parse_policy_aceita_tls_sem_verificacao_quando_todo_alvo_e_local() -> None:
    data = policy_data(tls_verify_upstream=False)
    data["scope"]["allow"] = [data["scope"]["allow"][1]]

    assert parse_policy(dump(data)).tls_verify_upstream is False


@pytest.mark.parametrize("valor", ["false", 0, None])
def test_parse_policy_recusa_tls_verify_que_nao_e_booleano(valor: object) -> None:
    with pytest.raises(ConfigError, match="tls_verify_upstream"):
        parse_policy(dump(policy_data(tls_verify_upstream=valor)))


@pytest.mark.parametrize("fila", [0, -1, 1001, "10", 1.5])
def test_parse_policy_recusa_fila_fora_do_intervalo(fila: object) -> None:
    with pytest.raises(ConfigError, match="max_queued_requests"):
        parse_policy(dump(policy_data(max_queued_requests=fila)))


def test_mensagem_de_erro_nao_repete_valores_do_arquivo() -> None:
    data = policy_data()
    data["scope"]["allow"][0]["host"] = "segredo-no-lugar-errado@exemplo.com"

    with pytest.raises(ConfigError) as info:
        parse_policy(dump(data))

    assert "segredo-no-lugar-errado" not in info.value.message


def test_deadline_of_usa_o_menor_entre_prazo_e_duracao() -> None:
    started = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
    policy = make_policy(not_after="2026-11-13T12:30:00Z")

    assert deadline_of(policy, started) == datetime(2026, 11, 13, 12, 30, tzinfo=UTC)


def test_deadline_of_limita_pela_duracao_maxima_quando_prazo_e_distante() -> None:
    started = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

    assert deadline_of(make_policy(), started) == datetime(2026, 11, 13, 13, 0, tzinfo=UTC)

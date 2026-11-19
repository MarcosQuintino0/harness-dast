"""Arquivo `-sf` do Nuclei: formato seguro, modo, dono e remoção."""

import stat
import sys
from pathlib import Path

import pytest
import yaml

from harness_dast.adapters.nuclei.secrets_file import (
    NUCLEI_CONTAINER_UID,
    NucleiSecretsFile,
    render_secrets_yaml,
)
from harness_dast.application.nuclei_ports import NucleiSecret
from harness_dast.domain.errors import ConfigError

SECRET = NucleiSecret(
    domains=("api.hml.acme-teste.net.br", "api.hml.acme-teste.net.br:443"),
    header="Authorization",
    value="Bearer TOKEN-SINTETICO",
)
POSIX = pytest.mark.skipif(sys.platform == "win32", reason="modo de arquivo POSIX")


def _writer(tmp_path: Path, chown: object = None) -> NucleiSecretsFile:
    calls: list[tuple[Path, int, int]] = []

    def record(path: Path, uid: int, gid: int) -> None:
        calls.append((path, uid, gid))

    writer = NucleiSecretsFile(base_dir=tmp_path, chown=chown or record)  # type: ignore[arg-type]
    writer.calls = calls  # type: ignore[attr-defined]
    return writer


def test_conteudo_e_yaml_static_header_so_para_os_dominios_da_origem() -> None:
    data = yaml.safe_load(render_secrets_yaml(SECRET))

    assert data == {
        "static": [
            {
                "type": "header",
                "domains": ["api.hml.acme-teste.net.br", "api.hml.acme-teste.net.br:443"],
                "headers": [{"key": "Authorization", "value": "Bearer TOKEN-SINTETICO"}],
            }
        ]
    }


@pytest.mark.parametrize(
    "value",
    ['abc"\n  - type: dsl', "abc': {x: y}", "a: b # c", "- x", "\\n", 'a"b', "é: ü"],
)
def test_valor_hostil_nunca_vira_outra_chave(value: str) -> None:
    if not value.isprintable():
        pytest.skip("controle é recusado em outro teste")
    secret = NucleiSecret(domains=("alvo",), header="X-Api-Key", value=value)

    data = yaml.safe_load(render_secrets_yaml(secret))

    assert data["static"][0]["headers"] == [{"key": "X-Api-Key", "value": value}]
    assert len(data["static"]) == 1


@pytest.mark.parametrize("value", ["", "a\nb", "a\x00b", "a\rb"])
def test_valor_vazio_ou_com_controle_e_recusado(value: str) -> None:
    secret = NucleiSecret(domains=("alvo",), header="Authorization", value=value)

    with pytest.raises(ConfigError, match="não pôde ser gravado"):
        render_secrets_yaml(secret)


@pytest.mark.parametrize("header", ["", "A B", "A:B", "A\nB", "Autorização"])
def test_nome_de_cabecalho_invalido_e_recusado(header: str) -> None:
    secret = NucleiSecret(domains=("alvo",), header=header, value="x")

    with pytest.raises(ConfigError, match="cabeçalho"):
        render_secrets_yaml(secret)


@pytest.mark.parametrize("domains", [(), ("a b",), ("a\nb",), ("",)])
def test_dominio_invalido_e_recusado(domains: tuple[str, ...]) -> None:
    secret = NucleiSecret(domains=domains, header="Authorization", value="x")

    with pytest.raises(ConfigError, match="Domínio"):
        render_secrets_yaml(secret)


def test_grava_o_arquivo_e_remove_apaga_o_arquivo_e_a_pasta(tmp_path: Path) -> None:
    writer = _writer(tmp_path)

    path = writer.write(SECRET)

    assert yaml.safe_load(path.read_text(encoding="utf-8"))["static"][0]["headers"]
    assert path.parent.parent == tmp_path
    writer.remove(path)
    assert not path.exists()
    assert not path.parent.exists()


def test_remove_e_idempotente(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    path = writer.write(SECRET)

    writer.remove(path)
    writer.remove(path)

    assert not path.parent.exists()


def test_remove_nao_apaga_o_que_nao_foi_criado_por_ele(tmp_path: Path) -> None:
    foreign = tmp_path / "importante.txt"
    foreign.write_text("x", encoding="utf-8")

    _writer(tmp_path).remove(foreign)

    assert foreign.exists()


def test_troca_o_dono_para_o_usuario_do_conteiner(tmp_path: Path) -> None:
    writer = _writer(tmp_path)

    path = writer.write(SECRET)

    assert writer.calls == [(path, NUCLEI_CONTAINER_UID, NUCLEI_CONTAINER_UID)]  # type: ignore[attr-defined]


@POSIX
def test_com_dono_trocado_o_arquivo_fica_0400_numa_pasta_0700(tmp_path: Path) -> None:
    path = _writer(tmp_path).write(SECRET)

    assert stat.S_IMODE(path.stat().st_mode) == 0o400
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


@POSIX
def test_sem_privilegio_para_trocar_o_dono_o_arquivo_fica_legivel_na_pasta_privada(
    tmp_path: Path,
) -> None:
    def denied(path: Path, uid: int, gid: int) -> None:
        raise PermissionError

    path = _writer(tmp_path, chown=denied).write(SECRET)

    assert stat.S_IMODE(path.stat().st_mode) == 0o444
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_sem_chown_no_sistema_a_gravacao_funciona_e_a_remocao_tambem(tmp_path: Path) -> None:
    writer = NucleiSecretsFile(base_dir=tmp_path, chown=None)
    writer._chown = None  # sistema sem chown (Windows)

    path = writer.write(SECRET)
    writer.remove(path)

    assert not path.parent.exists()


def test_falha_de_escrita_nao_deixa_nada_no_disco(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(path: Path, text: str) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(NucleiSecretsFile, "_create", staticmethod(boom))

    with pytest.raises(ConfigError, match="gravar o arquivo de segredos"):
        _writer(tmp_path).write(SECRET)

    assert list(tmp_path.iterdir()) == []


def test_mensagem_de_erro_nao_traz_o_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(path: Path, text: str) -> None:
        raise OSError(text)

    monkeypatch.setattr(NucleiSecretsFile, "_create", staticmethod(boom))

    with pytest.raises(ConfigError) as caught:
        _writer(tmp_path).write(SECRET)

    assert "TOKEN-SINTETICO" not in str(caught.value)
    assert "TOKEN-SINTETICO" not in repr(SECRET)

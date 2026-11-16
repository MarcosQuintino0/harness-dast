"""Leitura do vínculo da pilha e dos arquivos de agora (ADR 0081)."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from harness_dast.adapters.scope_proxy.binding_source import FileStackBindingSource
from harness_dast.adapters.scope_proxy.generate import (
    POLICY_FILE_NAME,
    FileProxyPolicyStore,
    build_proxy_policy,
)
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.run import RunId
from harness_dast.domain.scope_approval import create_approval
from harness_dast.domain.stack_binding import compare_digests
from tests.fakes.profile_data import valid_profile

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)
RUN_ID = RunId.create(started_at=NOW, product="demo", suffix="abcdef")


class Sources:
    """Pastas de produto e de aprovação, e a política gerada de verdade pelo `stack up`."""

    def __init__(self, tmp_path: Path) -> None:
        self.products = tmp_path / "products"
        self.approvals = tmp_path / "approvals"
        self.policy_dir = tmp_path / "policy"
        (self.products / "demo").mkdir(parents=True)
        self.approvals.mkdir()
        (self.products / "demo" / "target.yml").write_bytes(b"profile bytes")
        approval = create_approval(valid_profile(), NOW, ()).model_dump_json().encode()
        (self.approvals / "demo.json").write_bytes(approval)
        profile = valid_profile()
        FileProxyPolicyStore(self.products, self.approvals, lambda _: profile).publish(
            profile, RUN_ID, NOW, self.policy_dir
        )
        self.source = FileStackBindingSource(self.products, self.approvals)


def test_vinculo_gravado_pelo_stack_up_bate_com_os_arquivos_de_agora(tmp_path: Path) -> None:
    sources = Sources(tmp_path)

    recorded = sources.source.recorded(sources.policy_dir)
    assert recorded is not None
    result = compare_digests(recorded, sources.source.current("demo"))

    assert result.state == "fresh"
    assert recorded.profile_sha256 == hashlib.sha256(b"profile bytes").hexdigest()


def test_editar_o_perfil_depois_do_stack_up_deixa_a_pilha_velha_so_no_perfil(
    tmp_path: Path,
) -> None:
    sources = Sources(tmp_path)
    (sources.products / "demo" / "target.yml").write_bytes(b"profile bytes\nauth: edited\n")

    recorded = sources.source.recorded(sources.policy_dir)
    assert recorded is not None
    result = compare_digests(recorded, sources.source.current("demo"))

    assert result.state == "stale"
    assert result.stale_parts == ("profile",)


def test_current_devolve_none_para_arquivo_ausente_e_grande_demais(tmp_path: Path) -> None:
    sources = Sources(tmp_path)
    (sources.approvals / "demo.json").unlink()
    (sources.products / "demo" / "target.yml").write_bytes(b"x" * (1024 * 1024 + 1))

    current = sources.source.current("demo")

    assert current.profile_sha256 is None
    assert current.approval_sha256 is None


def test_recorded_devolve_none_quando_a_politica_nao_prende_fontes(tmp_path: Path) -> None:
    policy = build_proxy_policy(valid_profile(), RUN_ID, NOW)
    directory = tmp_path / "policy"
    directory.mkdir()
    (directory / POLICY_FILE_NAME).write_text(policy.model_dump_json(), encoding="utf-8")

    assert FileStackBindingSource(tmp_path, tmp_path).recorded(directory) is None


@pytest.mark.parametrize(
    "content",
    [None, b"", b"{", b"[]", b'{"schema_version": 1}', b"\xff\xfe", b"x" * (1024 * 1024 + 1)],
)
def test_recorded_falha_fechado_com_politica_ausente_ilegivel_ou_invalida(
    tmp_path: Path, content: bytes | None
) -> None:
    directory = tmp_path / "policy"
    directory.mkdir()
    if content is not None:
        (directory / POLICY_FILE_NAME).write_bytes(content)

    with pytest.raises(ConfigError):
        FileStackBindingSource(tmp_path, tmp_path).recorded(directory)

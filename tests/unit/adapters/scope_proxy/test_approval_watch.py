import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import harness_dast.adapters.scope_proxy.approval_watch as watch_module
import harness_dast.adapters.scope_proxy.generate as generate_module
from harness_dast.adapters.scope_proxy.approval_watch import FileWatch, file_signature
from harness_dast.adapters.scope_proxy.generate import FileProxyPolicyStore
from harness_dast.adapters.scope_proxy.policy import load_policy
from harness_dast.adapters.storage.approval_store import FileApprovalStore
from harness_dast.domain.run import RunId
from harness_dast.domain.scope_approval import create_approval
from tests.fakes.profile_data import valid_profile
from tests.integration.stale_watch_support import diagnose

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)


def _sources(tmp_path: Path) -> tuple[Path, Path, bytes]:
    products = tmp_path / "products"
    product = products / "demo"
    approvals = tmp_path / "approvals"
    product.mkdir(parents=True)
    approvals.mkdir()
    (product / "target.yml").write_bytes(b"profile bytes")
    raw = create_approval(valid_profile(), NOW, ()).model_dump_json().encode()
    (approvals / "demo.json").write_bytes(raw)
    return products, approvals, raw


def test_watcher_recusa_substituicao_atomica_mesmo_com_conteudo_igual(tmp_path: Path) -> None:
    _, approvals, raw = _sources(tmp_path)
    path = approvals / "demo.json"
    watch = FileWatch(path, hashlib.sha256(raw).hexdigest(), product="demo")
    assert watch.unchanged()
    replacement = approvals / "new.json"
    replacement.write_bytes(raw)
    replacement.replace(path)
    assert not watch.unchanged()


def test_watcher_recusa_conteudo_malformado_mesmo_com_hash_correto(tmp_path: Path) -> None:
    path = tmp_path / "demo.json"
    raw = b"not-json"
    path.write_bytes(raw)
    watch = FileWatch(path, hashlib.sha256(raw).hexdigest(), product="demo")
    assert not watch.unchanged()


def test_leitura_da_aprovacao_nao_invalida_watcher_em_arquivo_local(tmp_path: Path) -> None:
    _, approvals, raw = _sources(tmp_path)
    watch = FileWatch(approvals / "demo.json", hashlib.sha256(raw).hexdigest(), product="demo")

    assert FileApprovalStore(tmp_path).read("demo") is not None
    assert watch.unchanged()


def test_diagnostico_sanitizado_quando_fontes_sinteticas_estao_validas(tmp_path: Path) -> None:
    products, approvals, raw = _sources(tmp_path)
    profile = valid_profile()
    store = FileProxyPolicyStore(products, approvals, lambda _: profile)
    run_id = RunId.create(started_at=NOW, product="demo", suffix="abcdef")
    policy_path = store.publish(profile, run_id, NOW, tmp_path / "policy")

    result = diagnose(policy_path, approvals, products / "demo", 0)

    assert result["policy_valid"] is True
    assert result["approval_metadata"] == {
        "accessible": True,
        "descriptor_stable": True,
        "path_matches_descriptor": True,
        "device_matches_descriptor": True,
        "inode_matches_descriptor": True,
        "size_matches_descriptor": True,
        "mtime_matches_descriptor": True,
        "ctime_matches_descriptor": True,
    }
    output = json.dumps(result)
    assert raw.decode() not in output
    assert hashlib.sha256(raw).hexdigest() not in output
    assert "profile bytes" not in output


def test_publish_vincula_aprovacao_validada_e_perfil_congelado(tmp_path: Path) -> None:
    products, approvals, raw = _sources(tmp_path)
    profile = valid_profile()
    store = FileProxyPolicyStore(products, approvals, lambda _: profile)
    run_id = RunId.create(started_at=NOW, product="demo", suffix="abcdef")
    path = store.publish(profile, run_id, NOW, tmp_path / "policy")
    binding = load_policy(path).binding
    assert binding is not None
    assert binding.approval_sha256 == hashlib.sha256(raw).hexdigest()
    assert binding.profile_sha256 == hashlib.sha256(b"profile bytes").hexdigest()


def test_releitura_aceita_ctime_divergente_no_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "target.yml"
    raw = b"original"
    path.write_bytes(raw)
    real_stat = Path.stat

    def stat_with_different_ctime(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        value = real_stat(self, follow_symlinks=follow_symlinks)
        if self != path:
            return value
        # O dubl? representa o ctime divergente observado entre stat e fstat no Windows.
        return cast(
            os.stat_result,
            SimpleNamespace(
                st_dev=value.st_dev,
                st_ino=value.st_ino,
                st_size=value.st_size,
                st_mtime_ns=value.st_mtime_ns,
                st_ctime_ns=value.st_ctime_ns + 1,
            ),
        )

    def windows_signature(value: os.stat_result) -> tuple[int, int, int, int, int]:
        return file_signature(value, windows=True)

    monkeypatch.setattr(watch_module, "file_signature", windows_signature)
    monkeypatch.setattr(generate_module, "file_signature", windows_signature)
    monkeypatch.setattr(Path, "stat", stat_with_different_ctime)

    snapshot, _ = generate_module._read_snapshot(path)
    watch = FileWatch(path, hashlib.sha256(raw).hexdigest())
    assert snapshot == raw
    assert watch.unchanged()


def test_hash_recusa_mutacao_com_tamanho_e_mtime_preservados(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "target.yml"
    raw = b"original"
    path.write_bytes(raw)
    monkeypatch.setattr(
        watch_module, "file_signature", lambda value: file_signature(value, windows=True)
    )
    watch = FileWatch(path, hashlib.sha256(raw).hexdigest())
    before = path.stat()
    original_signature = file_signature(before, windows=True)

    path.write_bytes(b"alterado")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

    assert file_signature(path.stat(), windows=True) == original_signature
    assert not watch.unchanged()

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from harness_dast.adapters.scope_proxy.approval_watch import FileWatch
from harness_dast.adapters.scope_proxy.generate import FileProxyPolicyStore
from harness_dast.adapters.scope_proxy.policy import load_policy
from harness_dast.domain.run import RunId
from harness_dast.domain.scope_approval import create_approval
from tests.fakes.profile_data import valid_profile

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

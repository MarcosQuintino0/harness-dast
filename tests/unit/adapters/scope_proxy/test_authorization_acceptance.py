"""Aceite da revogação por concessão com arquivos temporários e sem rede."""

import asyncio
import hashlib
import io
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO

import pytest

from harness_dast.adapters.scope_proxy.decision import Reason
from harness_dast.adapters.scope_proxy.engine import ScopeProxyEngine
from harness_dast.adapters.scope_proxy.grant_queue import GrantQueue
from harness_dast.adapters.scope_proxy.policy import ApprovalBinding
from harness_dast.domain.profile import ProductProfile
from tests.fakes.approvals import approval_for
from tests.fakes.profile_data import dump_yaml, valid_profile_data
from tests.unit.adapters.scope_proxy.helpers import make_policy
from tests.unit.adapters.scope_proxy.test_engine import Clocks


def rig(
    root: Path, window: str = "seg-dom 00:00-24:00 UTC"
) -> tuple[ScopeProxyEngine, Clocks, Path, Path]:
    data = valid_profile_data()
    data["scope"]["windows"] = [window]
    profile = ProductProfile.from_data(data)
    approval_dir = root / "approvals"
    profile_dir = root / "product"
    approval_dir.mkdir()
    profile_dir.mkdir()
    approval = approval_dir / "demo.json"
    target = profile_dir / "target.yml"
    approval.write_text(approval_for(profile).model_dump_json(), encoding="utf-8")
    target.write_text(dump_yaml(data), encoding="utf-8")
    binding = ApprovalBinding(
        product=profile.product,
        approval_sha256=hashlib.sha256(approval.read_bytes()).hexdigest(),
        profile_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        authorization=profile.scope.authorization,
        windows=profile.scope.windows,
    )
    policy = make_policy().model_copy(update={"binding": binding})
    clocks = Clocks()
    engine = ScopeProxyEngine(
        policy,
        policy_dir=root,
        approval_dir=approval_dir,
        profile_dir=profile_dir,
        audit_file=io.StringIO(),
        stdout=io.StringIO(),
        now=clocks.now,
        monotonic=clocks.monotonic,
    )
    return engine, clocks, approval, target


def test_revogar_apos_compilar_impede_envio(tmp_path: Path) -> None:
    engine, _, approval, _ = rig(tmp_path)
    approval.unlink()
    sent: list[str] = []

    async def scenario() -> None:
        result = await GrantQueue(engine, sleep=asyncio.sleep).acquire()
        if result.allowed:
            sent.append("upstream")
        assert result.reason is Reason.APPROVAL_CHANGED

    asyncio.run(scenario())
    assert sent == []


def test_revogar_durante_espera_impede_concessao(tmp_path: Path) -> None:
    engine, clocks, approval, _ = rig(tmp_path)
    engine.grant_slot()
    sent: list[str] = []

    async def sleep(delay: float) -> None:
        approval.unlink()
        clocks.mono += delay

    async def scenario() -> None:
        result = await GrantQueue(engine, sleep=sleep).acquire()
        if result.allowed:
            sent.append("upstream")
        assert result.reason is Reason.APPROVAL_CHANGED

    asyncio.run(scenario())
    assert sent == []


@pytest.mark.parametrize("source", ["approval", "profile"])
def test_substituicao_atomica_de_fonte_fecha_concessao(tmp_path: Path, source: str) -> None:
    engine, _, approval, target = rig(tmp_path)
    path = approval if source == "approval" else target
    replacement = path.with_suffix(".new")
    replacement.write_bytes(path.read_bytes() + b" ")
    replacement.replace(path)

    assert (
        asyncio.run(GrantQueue(engine, sleep=asyncio.sleep).acquire()).reason
        is Reason.APPROVAL_CHANGED
    )


def test_outro_produto_nao_revoga_o_produto_atual(tmp_path: Path) -> None:
    engine, _, approval, _ = rig(tmp_path)
    (approval.parent / "outro.json").write_text("alterado", encoding="utf-8")

    assert asyncio.run(GrantQueue(engine, sleep=asyncio.sleep).acquire()).allowed


def test_aprovacao_restaurada_nao_religa_pilha(tmp_path: Path) -> None:
    engine, _, approval, _ = rig(tmp_path)
    original = approval.read_bytes()
    approval.unlink()

    async def scenario() -> None:
        queue = GrantQueue(engine, sleep=asyncio.sleep)
        assert (await queue.acquire()).reason is Reason.APPROVAL_CHANGED
        approval.write_bytes(original)
        assert (await queue.acquire()).reason is Reason.APPROVAL_CHANGED

    asyncio.run(scenario())


def test_falha_de_leitura_fecha_concessao(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, _, approval, _ = rig(tmp_path)
    original_open = Path.open

    def deny_read(path: Path, mode: str = "r") -> BinaryIO:
        if path == approval:
            raise PermissionError("inacessível")
        assert mode == "rb"
        return original_open(path, "rb")

    monkeypatch.setattr(Path, "open", deny_read)
    assert (
        asyncio.run(GrantQueue(engine, sleep=asyncio.sleep).acquire()).reason
        is Reason.APPROVAL_CHANGED
    )


def test_stop_durante_espera_fecha_concessao(tmp_path: Path) -> None:
    engine, clocks, _, _ = rig(tmp_path)
    engine.grant_slot()

    async def sleep(delay: float) -> None:
        clocks.mono += delay
        (tmp_path / "KILL").touch()

    assert asyncio.run(GrantQueue(engine, sleep=sleep).acquire()).reason is Reason.KILL_SWITCH


def test_revogacao_tem_prioridade_sobre_recuo(tmp_path: Path) -> None:
    engine, _, approval, _ = rig(tmp_path)

    async def scenario() -> None:
        queue = GrantQueue(engine, sleep=asyncio.sleep)
        queue.defer(60)
        approval.unlink()
        assert (await queue.acquire()).reason is Reason.APPROVAL_CHANGED

    asyncio.run(scenario())


def test_prazo_durante_espera_fecha_concessao(tmp_path: Path) -> None:
    engine, clocks, _, _ = rig(tmp_path)
    engine.grant_slot()

    async def sleep(delay: float) -> None:
        clocks.mono += delay
        clocks.wall += timedelta(days=2)

    assert asyncio.run(GrantQueue(engine, sleep=sleep).acquire()).reason is Reason.RUN_EXPIRED


def test_fim_da_janela_durante_espera_fecha_concessao(tmp_path: Path) -> None:
    engine, clocks, _, _ = rig(tmp_path, "sex 12:00-12:01 UTC")
    engine.grant_slot()

    async def sleep(delay: float) -> None:
        clocks.mono += delay
        clocks.wall += timedelta(minutes=1)

    assert asyncio.run(GrantQueue(engine, sleep=sleep).acquire()).reason is Reason.RUN_EXPIRED

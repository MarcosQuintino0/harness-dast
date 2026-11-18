"""Propriedade dos projetos da prova com inventário sintético, sem Docker."""

import pytest

from tests.integration.lab_resource_support import (
    Inventory,
    ResourceGuard,
    ResourceSafetyError,
    inventory,
    verified_down,
)

EMPTY = Inventory(frozenset(), frozenset(), frozenset())
OWNED = Inventory(frozenset({"a" * 64}), frozenset({"b" * 64}), frozenset({("v", "t1")}))


class FakeInventory:
    """Retorna a situação atual ou simula uma falha de consulta."""

    def __init__(self) -> None:
        self.current = EMPTY
        self.fail = False

    def read(self) -> Inventory:
        if self.fail:
            raise OSError("falha sintética")
        return self.current


@pytest.mark.parametrize(
    "occupied",
    [
        Inventory(frozenset({"a"}), frozenset(), frozenset()),
        Inventory(frozenset(), frozenset({"b"}), frozenset()),
        Inventory(frozenset(), frozenset(), frozenset({("v", "t")})),
    ],
)
def test_recusa_subida_com_recurso_ocupado(occupied: Inventory) -> None:
    source = FakeInventory()
    source.current = occupied
    with pytest.raises(ResourceSafetyError, match="ocupados"):
        ResourceGuard(source.read).before_up()


@pytest.mark.parametrize(
    "changed",
    [
        Inventory(frozenset({"c" * 64}), OWNED.networks, OWNED.volumes),
        Inventory(OWNED.containers, frozenset({"d" * 64}), OWNED.volumes),
        Inventory(OWNED.containers, OWNED.networks, frozenset({("v", "t2")})),
    ],
)
def test_recusa_down_quando_identidade_muda(changed: Inventory) -> None:
    source = FakeInventory()
    guard = ResourceGuard(source.read)
    guard.before_up()
    source.current = OWNED
    guard.capture()
    source.current = changed
    with pytest.raises(ResourceSafetyError, match="Down recusado"):
        guard.before_down()


def test_recusa_down_quando_up_parcial_nao_tem_inventario() -> None:
    source = FakeInventory()
    guard = ResourceGuard(source.read)
    guard.before_up()
    source.current = OWNED
    actions: list[str] = []
    records: dict[str, object] = {}

    def down() -> int:
        actions.append("down")
        return 0

    with pytest.raises(ResourceSafetyError, match="inventário ausente"):
        verified_down(guard, down, records)
    assert actions == []
    assert "intervenção humana" in str(records["down_recusado"])


def test_recusa_down_quando_consulta_falha() -> None:
    source = FakeInventory()
    guard = ResourceGuard(source.read)
    source.current = OWNED
    guard.capture()
    source.fail = True
    with pytest.raises(ResourceSafetyError, match="intervenção humana"):
        guard.before_down()


def test_falha_no_segundo_inventario_nao_autoriza_down() -> None:
    calls = 0

    def inspect() -> Inventory:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("falha sintética")
        return OWNED

    guard = ResourceGuard(inspect)
    with pytest.raises(ResourceSafetyError, match="intervenção humana"):
        guard.capture()
    assert guard.created is None
    with pytest.raises(ResourceSafetyError, match="inventário ausente"):
        guard.before_down()


def test_autoriza_down_com_identidades_iguais_e_confere_ausencia() -> None:
    source = FakeInventory()
    guard = ResourceGuard(source.read)
    guard.before_up()
    source.current = OWNED
    guard.capture()
    guard.before_down()
    source.current = EMPTY
    guard.after_down()


def test_recusa_final_quando_recurso_permanece() -> None:
    source = FakeInventory()
    source.current = OWNED
    with pytest.raises(ResourceSafetyError, match="restantes"):
        ResourceGuard(source.read).after_down()


def test_verifica_ausencia_mesmo_se_down_falhar() -> None:
    source = FakeInventory()
    source.current = OWNED
    guard = ResourceGuard(source.read)
    guard.capture()
    records: dict[str, object] = {}

    def down() -> int:
        source.current = EMPTY
        return 1

    with pytest.raises(AssertionError, match="stack down"):
        verified_down(guard, down, records)
    assert records["verificacao_ausencia"] == "sem recursos"


@pytest.mark.parametrize(("base", "network"), [("hdast", "lab_net"), ("hdast-crapi", "crapi_net")])
@pytest.mark.parametrize("suffix", ["", "-claude"])
@pytest.mark.parametrize("kind", ["container", "network", "volume"])
def test_inventario_detecta_nome_reservado_mesmo_sem_rotulo(
    kind: str, suffix: str, base: str, network: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HDAST_IT_STACK_SUFFIX", suffix)
    project = base + suffix

    def run(args: tuple[str, ...]) -> str:
        if args[:2] == ("volume", "inspect"):
            return "2026-01-01T00:00:00Z"
        if kind == "container" and args[0] == "ps" and f"name=^/{project}-" in args:
            assert "-a" in args[1]  # inclui contêineres parados
            return "a" * 64
        if (
            kind == "network"
            and args[:2] == ("network", "ls")
            and f"name=^{project}_{network}$" in args
        ):
            return "b" * 64
        if kind == "volume" and args[:2] == ("volume", "ls") and f"name=^{project}_" in args:
            return project + "_data"
        return ""

    with pytest.raises(ResourceSafetyError, match="ocupados"):
        ResourceGuard(lambda: inventory(run)).before_up()

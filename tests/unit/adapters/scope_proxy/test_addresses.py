import pytest

from harness_dast.adapters.scope_proxy.addresses import check_addresses
from harness_dast.adapters.scope_proxy.decision import Reason


@pytest.mark.parametrize("address", ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"])
def test_check_addresses_permite_endereco_global_sem_allow_local(address: str) -> None:
    assert check_addresses([address], allow_local=False).allowed is True


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "::1",
        "10.255.0.7",
        "172.16.5.4",
        "192.168.1.1",
        "100.64.0.9",
        "fc00::1",
        "169.254.169.254",
        "169.254.1.1",
        "fe80::1",
        "fd00:ec2::254",
        "0.0.0.0",  # noqa: S104 - endereço usado como dado de teste, não como bind
        "224.0.0.1",
        "240.0.0.1",
        "::ffff:10.0.0.1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "not-an-ip",
        "",
    ],
)
def test_check_addresses_recusa_endereco_interno_sem_allow_local(address: str) -> None:
    verdict = check_addresses([address], allow_local=False)

    assert verdict.allowed is False
    assert verdict.reason is Reason.ADDRESS_FORBIDDEN


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "::1", "10.255.0.7", "172.18.0.5", "192.168.1.1", "100.64.0.9"]
)
def test_check_addresses_permite_rede_local_com_allow_local(address: str) -> None:
    assert check_addresses([address], allow_local=True).allowed is True


@pytest.mark.parametrize(
    "address",
    [
        "169.254.169.254",
        "169.254.1.1",
        "fe80::1",
        "fd00:ec2::254",
        "0.0.0.0",  # noqa: S104 - dado de teste, não é bind
        "224.0.0.1",
        "::ffff:169.254.169.254",
    ],
)
def test_check_addresses_recusa_link_local_e_metadados_mesmo_com_allow_local(address: str) -> None:
    assert check_addresses([address], allow_local=True).allowed is False


def test_check_addresses_recusa_se_um_dos_enderecos_for_proibido() -> None:
    # Um nome com A público e A privado: basta um para recusar (o cliente poderia usar qualquer).
    verdict = check_addresses(["93.184.216.34", "10.0.0.5"], allow_local=False)

    assert verdict.allowed is False


def test_check_addresses_recusa_lista_vazia_como_falha_de_dns() -> None:
    verdict = check_addresses([], allow_local=True)

    assert verdict.allowed is False
    assert verdict.reason is Reason.DNS_FAILURE


@pytest.mark.parametrize(
    "address",
    [
        "64:ff9b::a9fe:a9fe",  # NAT64 para 169.254.169.254 (metadados da nuvem)
        "64:ff9b::7f00:1",  # NAT64 para 127.0.0.1
        "64:ff9b::a00:1",  # NAT64 para 10.0.0.1
        "64:ff9b:1::1",  # NAT64 de uso local
    ],
)
def test_check_addresses_recusa_nat64_que_aponta_para_endereco_interno(address: str) -> None:
    # O Python 3.13 (a imagem do proxy) trata 64:ff9b::/96 como global; a regra tem de valer
    # em qualquer versão.
    assert check_addresses([address], allow_local=False).allowed is False


@pytest.mark.parametrize("address", ["64:ff9b::a9fe:a9fe", "64:ff9b:1::1"])
def test_check_addresses_nunca_libera_metadados_nem_nat64_local_nem_com_allow_local(
    address: str,
) -> None:
    assert check_addresses([address], allow_local=True).allowed is False


def test_check_addresses_permite_nat64_que_aponta_para_endereco_publico() -> None:
    assert (
        check_addresses(["64:ff9b::5db8:d822"], allow_local=False).allowed is True
    )  # 93.184.216.34

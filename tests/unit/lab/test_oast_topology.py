"""Contratos estáticos dos overlays de retorno do laboratório."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_ponte_encaminha_apenas_ao_callback_do_zap() -> None:
    overlay = yaml.safe_load((ROOT / "lab/oast/compose.yaml").read_text(encoding="utf-8"))
    gateway = overlay["services"]["oast-gateway"]
    assert gateway["command"] == ["-d", "-d", "TCP-LISTEN:8090,fork,reuseaddr", "TCP:zap:8090"]
    assert set(gateway["networks"]) == {"zap_net", "oast_net"}
    assert "ports" not in gateway
    assert overlay["networks"]["oast_net"]["internal"] is True


def test_overlay_conecta_somente_workshop_a_rede_de_retorno() -> None:
    overlay = yaml.safe_load((ROOT / "lab/crapi/compose.oast.yaml").read_text(encoding="utf-8"))
    assert overlay["services"] == {"crapi-workshop": {"networks": ["oast_net"]}}
    assert overlay["networks"]["oast_net"]["external"] is True

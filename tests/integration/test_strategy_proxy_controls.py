"""Controles T2 e captura pública com a variante B nas duas APIs e modos."""

from pathlib import Path

import pytest

from tests.integration import test_lab_strategy as strategy_cases

pytestmark = [pytest.mark.integration, pytest.mark.lab_prova]


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize("mode", ["vulnerable", "secure"])
def test_v18_controles_e_captura_com_proxy(tmp_path: Path, product: str, mode: str) -> None:
    strategy_cases.test_strategy_preserva_controles_direcionados(
        tmp_path, product, mode, pacing="proxy"
    )

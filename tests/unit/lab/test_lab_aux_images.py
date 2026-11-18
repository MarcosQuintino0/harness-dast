"""Imagens auxiliares por arquivo de teste, sem Docker."""

import pytest

from tests.integration.lab_aux_images import auxiliary_images, main, oracle_image
from tests.integration.oast_support import PYTHON_IMAGE


def test_auxiliary_images_devolve_o_cliente_python_quando_o_arquivo_e_a_prova_oast() -> None:
    assert auxiliary_images("test_lab_oast.py") == (PYTHON_IMAGE,)


def test_auxiliary_images_devolve_o_oracle_do_compose_quando_o_arquivo_e_de_limpeza() -> None:
    image = oracle_image()

    assert auxiliary_images("test_run_cleanup_oracle.py") == (image,)
    assert image.startswith("gvenzl/oracle-free:23-slim-faststart@sha256:")


def test_auxiliary_images_nao_pede_nada_quando_o_arquivo_nao_usa_imagem_auxiliar() -> None:
    assert auxiliary_images("test_lab_negative.py") == ()


def test_main_recusa_quando_falta_o_arquivo(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "Uso:" in capsys.readouterr().err

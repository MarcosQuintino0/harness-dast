"""Montagem manual das dependências: o único lugar que instancia adaptadores concretos.

Sem contêiner de injeção. Cada função devolve um caso de uso pronto, com as portas ligadas
aos adaptadores reais.
"""

from pathlib import Path

from harness_dast.adapters.storage.product_scaffolder import (
    FileProductScaffolder,
    default_template_dir,
)
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.application.init_product import InitProduct
from harness_dast.application.validate_profile import ValidateProfile
from harness_dast.config.settings import load_settings


def _products_dir(override: Path | None) -> Path:
    # A flag tem precedência sobre HDAST_PRODUCTS_DIR; ela só escolhe a pasta, não amplia nada.
    return override if override is not None else load_settings().products_dir


def build_init_product(products_dir: Path | None) -> InitProduct:
    """Monta o caso de uso `hdast init`.

    Args:
        products_dir: Valor de `--products-dir`, ou `None` para usar `HDAST_PRODUCTS_DIR`.
    """
    scaffolder = FileProductScaffolder(_products_dir(products_dir), default_template_dir())
    return InitProduct(scaffolder)


def build_validate_profile(products_dir: Path | None) -> ValidateProfile:
    """Monta o caso de uso `hdast profile validate`.

    Args:
        products_dir: Valor de `--products-dir`, ou `None` para usar `HDAST_PRODUCTS_DIR`.
    """
    repository = FileProfileRepository(_products_dir(products_dir))
    return ValidateProfile(repository, SystemClock())

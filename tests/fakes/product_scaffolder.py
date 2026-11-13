"""Criador de produtos em memória, com o comportamento da porta `ProductScaffolder`."""

from harness_dast.application.ports import ScaffoldedProduct
from harness_dast.domain.errors import ConfigError


class InMemoryScaffolder:
    """Registra os produtos criados e recusa criar o mesmo nome duas vezes."""

    def __init__(self, files: tuple[str, ...] = ("target.yml", "README.md")) -> None:
        self._files = files
        self.created: dict[str, ScaffoldedProduct] = {}
        self.cleanup_requested: dict[str, bool] = {}

    def scaffold(self, product: str, *, with_cleanup: bool = False) -> ScaffoldedProduct:
        if product in self.created:
            raise ConfigError(f"O produto {product} já existe.", hint="Escolha outro nome.")
        result = ScaffoldedProduct(directory=f"/produtos/{product}", files=self._files)
        self.created[product] = result
        self.cleanup_requested[product] = with_cleanup
        return result

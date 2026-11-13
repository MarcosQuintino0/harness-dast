"""Caso de uso: criar a pasta de um produto novo a partir do modelo."""

from harness_dast.application.ports import ProductScaffolder, ScaffoldedProduct


class InitProduct:
    """Cria `<produtos>/<produto>/` com os arquivos do modelo, sem sobrescrever nada."""

    def __init__(self, scaffolder: ProductScaffolder) -> None:
        """Cria o caso de uso.

        Args:
            scaffolder: Criador da pasta do produto.
        """
        self._scaffolder = scaffolder

    def execute(self, product: str) -> ScaffoldedProduct:
        """Cria o produto.

        Args:
            product: Nome (slug) do produto.

        Returns:
            A pasta criada e os arquivos copiados.

        Raises:
            ConfigError: Se o nome for inválido ou o produto já existir (veja
                `ProductScaffolder.scaffold`).
        """
        return self._scaffolder.scaffold(product)

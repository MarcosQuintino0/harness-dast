"""Portas da camada `application`: o que os casos de uso exigem do mundo externo.

Cada porta é um `typing.Protocol` declarado aqui por quem a consome. Os adaptadores
(`adapters/`) as implementam; os testes usam falsos em memória (`tests/fakes/`).
Nenhuma porta decide regra de negócio: elas só buscam e gravam.
"""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.profile import ProductProfile


class ReferencedFile(BaseModel):
    """Arquivo para o qual o perfil aponta.

    Attributes:
        field: Campo do perfil que o referencia (ex.: `openapi`, `cleanup.script`).
        path: Caminho relativo à pasta do produto, como escrito no perfil.
    """

    model_config = ConfigDict(frozen=True)

    field: str
    path: str


class ScaffoldedProduct(BaseModel):
    """Pasta de produto recém-criada.

    Attributes:
        directory: Caminho absoluto da pasta criada, com barras normais.
        files: Caminhos dos arquivos criados, relativos à pasta, em ordem alfabética.
    """

    model_config = ConfigDict(frozen=True)

    directory: str
    files: tuple[str, ...]


class Clock(Protocol):
    """Relógio. Existe para que janela e validade da autorização sejam testáveis."""

    def now(self) -> datetime:
        """Devolve o instante atual, sempre com fuso horário."""
        ...


class ProfileRepository(Protocol):
    """Fonte dos perfis de produto."""

    def load(self, product: str) -> ProductProfile:
        """Carrega e valida o perfil do produto.

        Garante: o perfil é estruturalmente válido, seu campo `product` é o nome pedido e
        todo arquivo que ele referencia fica DENTRO da pasta do produto.

        Raises:
            ConfigError: Nome de produto inválido, pasta ou perfil ausente ou ilegível,
                YAML inválido ou inseguro, perfil inválido, referência para fora da pasta.
                A mensagem nunca repete o conteúdo do arquivo.
        """
        ...

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        """Lista os arquivos referenciados pelo perfil que ainda não existem.

        Só verifica existência: não lê o conteúdo.

        Raises:
            ConfigError: Se o produto for inválido ou algum caminho sair da pasta do produto.
        """
        ...


class ProductScaffolder(Protocol):
    """Criador da pasta de um produto novo a partir do modelo."""

    def scaffold(self, product: str) -> ScaffoldedProduct:
        """Cria a pasta do produto com os arquivos do modelo.

        Garante: nunca sobrescreve uma pasta existente e nunca cria nada fora da pasta de
        produtos; em caso de falha no meio da cópia, não deixa pasta parcial.

        Raises:
            ConfigError: Nome inválido, pasta de produtos ausente, produto já existente,
                modelo indisponível ou falha de escrita.
        """
        ...

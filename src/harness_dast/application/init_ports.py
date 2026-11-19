"""Portas consumidas pela capacidade init; assinaturas e docstrings preservadas."""

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class ScaffoldedProduct(BaseModel):
    """Pasta de produto recém-criada.

    Attributes:
        directory: Caminho absoluto da pasta criada, com barras normais.
        files: Caminhos dos arquivos criados, relativos à pasta, em ordem alfabética.
    """

    model_config = ConfigDict(frozen=True)

    directory: str
    files: tuple[str, ...]


class ProductScaffolder(Protocol):
    """Criador da pasta de um produto novo a partir do modelo."""

    def scaffold(
        self, product: str, *, with_cleanup: bool = False, target_text: str | None = None
    ) -> ScaffoldedProduct:
        """Cria a pasta do produto com os arquivos do modelo.

        Por padrão a subpasta `cleanup/` do modelo NÃO é copiada: a limpeza de dados é opcional
        e o script é de autoria humana. `with_cleanup=True` a copia (README e exemplo).
        `target_text` (ADR 0036) substitui o `target.yml` do modelo pelo texto gerado da carta;
        o texto é gravado como veio, em UTF-8 com quebras LF.

        Garante: nunca sobrescreve uma pasta existente e nunca cria nada fora da pasta de
        produtos; em caso de falha no meio da cópia, não deixa pasta parcial.

        Raises:
            ConfigError: Nome inválido, pasta de produtos ausente, produto já existente,
                modelo indisponível ou falha de escrita.
        """
        ...


class LetterReader(Protocol):
    """Leitor da carta de autorização estruturada (`carta.yml`)."""

    def read(self, path: Path) -> Mapping[str, object]:
        """Lê a carta como mapa, recusando YAML perigoso.

        Raises:
            ConfigError: Arquivo ausente, grande demais, fora de UTF-8 ou YAML inválido ou
                com construção proibida. A mensagem nunca traz o conteúdo do arquivo.
        """
        ...


class SpecPathReader(Protocol):
    """Leitor dos caminhos de um OpenAPI que ainda não está na pasta do produto."""

    def read_paths(self, base_dir: Path, relative: str) -> tuple[str, ...]:
        """Devolve os modelos de caminho (`/users/{id}`) do OpenAPI, sem repetição.

        Só lê arquivo dentro de `base_dir` (a pasta da carta) e não envia nada a ninguém.

        Raises:
            ConfigError: Caminho fora de `base_dir`, arquivo ausente ou OpenAPI inválido.
        """
        ...

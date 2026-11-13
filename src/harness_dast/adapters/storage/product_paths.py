"""Resolução segura de caminhos de produto dentro da pasta de produtos.

Único lugar que transforma um nome de produto (vindo da linha de comando) em caminho. A
garantia: o resultado é sempre uma pasta DIRETAMENTE dentro de `products_dir`, mesmo que haja
links simbólicos pelo caminho.
"""

import re
from pathlib import Path

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.run import SLUG_PATTERN

_SLUG = re.compile(SLUG_PATTERN)
# Nomes que o Windows trata como dispositivo; criar uma pasta com eles falha ou engana.
_WINDOWS_RESERVED = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{n}" for n in range(1, 10)),
        *(f"lpt{n}" for n in range(1, 10)),
    }
)
_PRODUCT_HINT = "Use um slug: minúsculas, dígitos e '-', de 1 a 40 caracteres (ex.: meu-produto)."


def validate_product_name(product: str) -> str:
    """Confere que o nome é um slug seguro para virar nome de pasta.

    Args:
        product: Nome informado.

    Returns:
        O mesmo nome, validado.

    Raises:
        ConfigError: Se não for slug, ou for nome reservado do Windows. A mensagem não repete
            o valor recebido.
    """
    if not _SLUG.fullmatch(product) or product in _WINDOWS_RESERVED:
        raise ConfigError("Nome de produto inválido.", hint=_PRODUCT_HINT)
    return product


def resolve_products_dir(products_dir: Path) -> Path:
    """Resolve a pasta de produtos, que precisa existir.

    Raises:
        ConfigError: Se a pasta não existir ou não for diretório.
    """
    try:
        resolved = products_dir.resolve()
        exists = resolved.is_dir()
    except (OSError, RuntimeError):
        exists = False
    if not exists:
        raise ConfigError(
            f"A pasta de produtos {products_dir} não existe ou não é um diretório.",
            hint="Crie a pasta, ou informe outra com --products-dir ou HDAST_PRODUCTS_DIR.",
        )
    return resolved


def product_dir_path(products_dir: Path, product: str) -> Path:
    """Devolve o caminho (resolvido) da pasta do produto, sem exigir que ela exista.

    Args:
        products_dir: Pasta de produtos, já existente.
        product: Nome do produto.

    Raises:
        ConfigError: Nome inválido, pasta de produtos inexistente, ou o caminho resolvido
            (por link simbólico, por exemplo) saiu de `products_dir`.
    """
    root = resolve_products_dir(products_dir)
    candidate = root / validate_product_name(product)
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        raise ConfigError(
            "Não foi possível resolver a pasta do produto.",
            hint="Confira se há link simbólico quebrado ou circular.",
        ) from None
    if resolved.parent != root:
        raise ConfigError(
            "A pasta do produto aponta para fora da pasta de produtos.",
            hint="Remova o link simbólico; a pasta do produto deve ficar dentro de products_dir.",
        )
    return resolved


def resolve_product_file(products_dir: Path, product: str, relative: str) -> Path:
    """Resolve um arquivo do produto e garante que ele fica DENTRO da pasta do produto.

    Não exige que o arquivo exista. O caminho `relative` já foi validado como relativo e sem
    `..` pelo perfil; aqui se confere o resultado final, que pode sair por link simbólico.

    Raises:
        ConfigError: Nome de produto inválido, pasta inexistente ou caminho que sai da pasta.
    """
    directory = product_dir_path(products_dir, product)
    try:
        resolved = (directory / relative).resolve()
    except (OSError, RuntimeError):
        raise ConfigError(
            "Não foi possível resolver o caminho de um arquivo do produto.",
            hint="Confira se há link simbólico quebrado ou circular.",
        ) from None
    if not resolved.is_relative_to(directory):
        raise ConfigError(
            "Um arquivo do produto aponta para fora da pasta do produto.",
            hint="Mantenha os arquivos do produto dentro da pasta dele (sem links para fora).",
        )
    return resolved

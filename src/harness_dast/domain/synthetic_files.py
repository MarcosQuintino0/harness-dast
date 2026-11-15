"""Arquivos sintéticos de lista fechada para o envio `multipart/form-data` do `probe` (ADR 0052).

O conteúdo é uma CONSTANTE deste módulo: pequeno (no máximo 1 KiB), inofensivo, determinístico
e nunca executável. Nada dele vem do OpenAPI, do alvo, de arquivo em disco, do usuário ou do
relógio. Nome do arquivo e nome do campo seguem uma regra ASCII estrita, sem barra, sem `..`,
sem aspas e sem CR/LF, para que nenhum nome vire injeção de cabeçalho. Este módulo é puro.
"""

import re
from typing import Final, Literal, get_args

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.errors import ConfigError

FileKind = Literal["text", "csv", "json", "png"]
FILE_KINDS: Final[tuple[str, ...]] = get_args(FileKind)
DEFAULT_KIND: Final[FileKind] = "text"
MAX_FILE_BYTES: Final = 1024
MAX_MULTIPART_BYTES: Final = 16_384
MAX_PARTS: Final = 20
NAME_PATTERN: Final = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\Z", re.ASCII)

_PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
    "0000000a4944415478da6360000000020001e527defc0000000049454e44ae426082"
)
_CONTENT: Final[dict[str, bytes]] = {
    "text": b"synthetic file\n",
    "csv": b"id,value\n1,synthetic\n",
    "json": b'{"synthetic":true}\n',
    "png": _PNG_1X1,
}
_CONTENT_TYPE: Final[dict[str, str]] = {
    "text": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
    "png": "image/png",
}
_EXTENSION: Final[dict[str, str]] = {"text": ".txt", "csv": ".csv", "json": ".json", "png": ".png"}
_DEFAULT_NAME: Final[dict[str, str]] = {kind: f"synthetic{ext}" for kind, ext in _EXTENSION.items()}
_KIND_BY_NAME: Final[dict[str, FileKind]] = {kind: kind for kind in get_args(FileKind)}
_BY_CONTENT_TYPE: Final[dict[str, FileKind]] = {
    value: _KIND_BY_NAME[kind] for kind, value in _CONTENT_TYPE.items()
}
_NAME_HINT = (
    "Use 1 a 64 caracteres ASCII (letras, dígitos, '_', '.', '-'), sem barra, sem '..' e sem aspas."
)


class FileSpec(ApiModel):
    """Um campo de arquivo de um corpo multipart: nome do campo, tipo e nome do arquivo.

    Attributes:
        field: Nome do campo multipart.
        kind: Tipo sintético (lista fechada).
        filename: Nome do arquivo enviado (extensão coerente com o tipo).
    """

    field: str
    kind: FileKind
    filename: str


def default_filename(kind: FileKind) -> str:
    """Nome padrão do arquivo do tipo (`synthetic.txt`, `synthetic.png`...)."""
    return _DEFAULT_NAME[kind]


def file_content(kind: FileKind) -> bytes:
    """Bytes constantes do arquivo sintético do tipo (no máximo `MAX_FILE_BYTES`)."""
    return _CONTENT[kind]


def file_content_type(kind: FileKind) -> str:
    """`Content-Type` fixo do tipo."""
    return _CONTENT_TYPE[kind]


def is_safe_name(name: str) -> bool:
    """Nome de campo ou de arquivo aceito: ASCII estrito, sem `..`, sem barra nem aspas."""
    return NAME_PATTERN.fullmatch(name) is not None and ".." not in name


def require_safe_name(name: str, what: str) -> str:
    """Devolve `name` se for seguro.

    Raises:
        ConfigError: Nome fora da regra (a mensagem não repete o valor).
    """
    if not is_safe_name(name):
        raise ConfigError(f"{what} inválido para multipart.", hint=_NAME_HINT)
    return name


def kind_from_content_type(declared: str | None) -> FileKind | None:
    """Tipo sintético que corresponde a um `Content-Type` declarado, ou `None` se não há.

    Só `image/png`, `text/csv`, `application/json` e `text/plain` têm tipo; qualquer outro
    (`image/jpeg`, `application/pdf`...) devolve `None` e o chamador volta ao padrão.
    """
    if declared is None:
        return None
    return _BY_CONTENT_TYPE.get(declared.split(";")[0].strip().lower())


def validate_file(kind: str, filename: str) -> tuple[FileKind, str]:
    """Confere tipo (lista fechada) e nome (regra ASCII, extensão coerente com o tipo).

    Raises:
        ConfigError: Tipo desconhecido, nome fora da regra ou extensão que não bate.
    """
    known = _KIND_BY_NAME.get(kind)
    if known is None:
        raise ConfigError(
            "Tipo de arquivo sintético desconhecido.",
            hint=f"Tipos aceitos: {', '.join(FILE_KINDS)}.",
        )
    checked = require_safe_name(filename, "Nome de arquivo")
    if not checked.lower().endswith(_EXTENSION[known]):
        raise ConfigError(
            f"A extensão do nome do arquivo não combina com o tipo {known}.",
            hint=f"Para o tipo {known} o nome termina em {_EXTENSION[known]}.",
        )
    return known, checked


def resolve_file(kind: str, filename: str | None) -> tuple[FileKind, str]:
    """Como `validate_file`, mas sem nome usa o padrão do tipo (`synthetic.png`...).

    Raises:
        ConfigError: Tipo desconhecido, nome fora da regra ou extensão que não bate.
    """
    known = _KIND_BY_NAME.get(kind)
    if known is None or filename is not None:
        return validate_file(kind, filename if filename is not None else "")
    return known, _DEFAULT_NAME[known]


def parse_file_spec(text: str) -> tuple[FileKind, str]:
    """Lê `tipo:nome` (saída do gerador `synthetic_file`).

    Raises:
        ConfigError: Formato inesperado, tipo desconhecido ou nome inválido.
    """
    kind, separator, filename = text.partition(":")
    if not separator:
        raise ConfigError(
            "Descrição de arquivo sintético fora do formato tipo:nome.",
            hint="Use o gerador synthetic_file para o campo de arquivo.",
        )
    return validate_file(kind, filename)

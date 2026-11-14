"""Construção e verificação em memória de um multipart exclusivamente sintético.

Este módulo não recebe dados do OpenAPI, não acessa arquivos nem rede e não participa do
caminho de envio. A prova cobre somente o formato mínimo produzido aqui.
"""

import hashlib
import re
from email import policy
from email.parser import BytesParser

from harness_dast.domain.errors import ConfigError

_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\Z", re.ASCII)
_FIELD_VALUE = b"synthetic"
_FILE_VALUE = b"synthetic file\n"
_FILENAME = "synthetic.txt"


def encode_synthetic_multipart(field_name: str, file_field_name: str) -> tuple[str, bytes]:
    """Monta duas partes fixas em memória, com nomes ASCII limitados e distintos.

    Retorna Content-Type e bytes; o arquivo é sempre sintético e pequeno. A boundary
    determinística deriva dos nomes e dos conteúdos fixos e não aparece em nenhum conteúdo.

    Raises:
        ConfigError: Nomes inválidos, repetidos ou colisão de boundary.
    """
    if not _NAME.fullmatch(field_name) or not _NAME.fullmatch(file_field_name):
        raise ConfigError(
            "Nome de campo multipart inválido.", hint="Use 1 a 64 caracteres ASCII seguros."
        )
    if field_name == file_field_name:
        raise ConfigError("Nomes multipart repetidos.", hint="Use nomes de campo distintos.")
    seed = f"{field_name}\0{file_field_name}".encode() + _FIELD_VALUE + _FILE_VALUE
    boundary = "harness-" + hashlib.sha256(seed).hexdigest()[:62]
    marker = boundary.encode()
    if marker in _FIELD_VALUE or marker in _FILE_VALUE:
        raise ConfigError("Colisão de boundary multipart.", hint="Use outros nomes sintéticos.")
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"\r\n\r\n'.encode()
        + _FIELD_VALUE
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="{file_field_name}"; '
        f'filename="{_FILENAME}"\r\nContent-Type: text/plain\r\n\r\n'.encode()
        + _FILE_VALUE
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return f"multipart/form-data; boundary={boundary}", body


def verify_synthetic_multipart() -> bool:
    """Monta e interpreta as duas partes em memória, sem expor corpo ou cabeçalhos.

    Retorna verdadeiro apenas se o parser padrão recuperar os nomes, conteúdo e arquivo
    esperados sem defeitos; não valida o esquema nem a aceitação por um servidor real.
    """
    content_type, body = encode_synthetic_multipart("field", "file")
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    )
    if message.defects or not message.is_multipart():
        return False
    parts = list(message.iter_parts())
    if len(parts) != 2 or any(part.defects for part in parts):
        return False
    field, file = parts
    return (
        field.get_content_disposition() == "form-data"
        and field.get_param("name", header="content-disposition") == "field"
        and field.get_payload(decode=True) == _FIELD_VALUE
        and file.get_content_disposition() == "form-data"
        and file.get_param("name", header="content-disposition") == "file"
        and file.get_filename() == _FILENAME
        and file.get_content_type() == "text/plain"
        and file.get_payload(decode=True) == _FILE_VALUE
    )

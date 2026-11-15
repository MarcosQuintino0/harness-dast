"""Construção, leitura e verificação de `multipart/form-data` exclusivamente sintético.

`encode_synthetic_multipart` e `verify_synthetic_multipart` são a prova em memória do ADR 0048.
`encode_multipart` (ADR 0052) monta o corpo que o `probe` envia: campos de texto mais arquivos
de `synthetic_files` (lista fechada, constantes). Nada aqui lê arquivo, rede ou o alvo; nome de
campo e de arquivo seguem `is_safe_name` e a fronteira é determinística e ausente de todo
conteúdo. `summarize_multipart` lê um corpo e devolve só nome, tipo e tamanho das partes.
"""

import hashlib
import re
from collections.abc import Sequence
from email import policy
from email.parser import BytesParser
from typing import Final, Literal

from pydantic import Field

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.synthetic_files import (
    MAX_FILE_BYTES,
    MAX_MULTIPART_BYTES,
    MAX_PARTS,
    FileSpec,
    file_content,
    file_content_type,
    is_safe_name,
    require_safe_name,
)

_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\Z", re.ASCII)
_FIELD_VALUE = b"synthetic"
_FILE_VALUE = b"synthetic file\n"
_FILENAME = "synthetic.txt"
MULTIPART_MEDIA_TYPE: Final = "multipart/form-data"


class MultipartPart(ApiModel):
    """Resumo de uma parte multipart: nunca o conteúdo.

    Attributes:
        name: Nome do campo.
        kind: `field` (texto) ou `file` (arquivo).
        filename: Nome do arquivo (só em `file`).
        content_type: `Content-Type` da parte (só em `file`).
        size: Tamanho do conteúdo em bytes.
    """

    name: str = Field(max_length=64)
    kind: Literal["field", "file"]
    filename: str | None = Field(default=None, max_length=64)
    content_type: str | None = Field(default=None, max_length=100)
    size: int = Field(ge=0)


class MultipartSummary(ApiModel):
    """Resumo de um corpo multipart: partes (sem valores nem fronteira) e o total de bytes.

    Attributes:
        parts: Partes, na ordem do corpo.
        total_bytes: Soma dos tamanhos dos conteúdos das partes.
    """

    parts: tuple[MultipartPart, ...] = Field(default=(), max_length=MAX_PARTS)
    total_bytes: int = Field(default=0, ge=0)


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


def encode_multipart(
    fields: Sequence[tuple[str, str]], files: Sequence[FileSpec]
) -> tuple[str, bytes]:
    """Monta um corpo multipart com campos de texto e arquivos sintéticos.

    Args:
        fields: Pares (nome, valor de texto), na ordem em que vão no corpo.
        files: Campos de arquivo (nome, tipo e nome do arquivo), depois dos campos.

    Returns:
        `Content-Type` com a fronteira e os bytes do corpo. A fronteira é determinística
        (SHA-256 dos nomes e conteúdos) e nunca aparece em nenhum conteúdo.

    Raises:
        ConfigError: Nenhuma parte, mais de 20 partes, nome fora da regra ou repetido, nome
            de arquivo fora da regra, corpo acima de 16 KiB ou colisão de fronteira.
    """
    total = len(fields) + len(files)
    if total == 0 or total > MAX_PARTS:
        raise ConfigError(
            f"O corpo multipart precisa de 1 a {MAX_PARTS} partes (tem {total}).",
            hint="Confira o esquema do corpo multipart no OpenAPI.",
        )
    names = [name for name, _ in fields] + [spec.field for spec in files]
    for name in names:
        require_safe_name(name, "Nome de campo")
    if len(set(names)) != len(names):
        raise ConfigError("Nomes de campo multipart repetidos.", hint="Use nomes distintos.")
    contents: list[tuple[str, str | None, str | None, bytes]] = [
        (name, None, None, value.encode("utf-8")) for name, value in fields
    ]
    for spec in files:
        require_safe_name(spec.filename, "Nome de arquivo")
        data = file_content(spec.kind)
        if len(data) > MAX_FILE_BYTES:
            raise ConfigError("Arquivo sintético acima do limite.", hint="Erro interno do tipo.")
        contents.append((spec.field, spec.filename, file_content_type(spec.kind), data))
    seed = b"\0".join(
        f"{name}\0{filename}\0{ctype}".encode() + b"\0" + data
        for name, filename, ctype, data in contents
    )
    boundary = "harness-" + hashlib.sha256(seed).hexdigest()[:62]
    marker = boundary.encode()
    if any(marker in data for *_, data in contents):
        raise ConfigError("Colisão de boundary multipart.", hint="Use outros valores de campo.")
    chunks: list[bytes] = []
    for name, filename, ctype, data in contents:
        head = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
        if filename is not None:
            head += f'; filename="{filename}"\r\nContent-Type: {ctype}'
        chunks.append(head.encode() + b"\r\n\r\n" + data + b"\r\n")
    body = b"".join(chunks) + f"--{boundary}--\r\n".encode()
    if len(body) > MAX_MULTIPART_BYTES:
        raise ConfigError(
            f"O corpo multipart passa de {MAX_MULTIPART_BYTES} bytes.",
            hint="Reduza os campos de texto do corpo (regra em data-rules.yml).",
        )
    return f"{MULTIPART_MEDIA_TYPE}; boundary={boundary}", body


def summarize_multipart(content_type: str, body: bytes) -> MultipartSummary | None:
    """Lê um corpo multipart e devolve só nome, tipo e tamanho das partes.

    Retorna `None` se o corpo não é um multipart bem formado, tem mais de 20 partes ou alguma
    parte sem nome seguro. Nunca devolve conteúdo, valores de campo nem a fronteira.
    """
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    )
    if message.defects or not message.is_multipart():
        return None
    raw = list(message.iter_parts())
    if not raw or len(raw) > MAX_PARTS:
        return None
    parts: list[MultipartPart] = []
    for part in raw:
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        if (
            part.defects
            or not isinstance(name, str)
            or not is_safe_name(name)
            or not isinstance(payload, bytes)
            or (filename is not None and not is_safe_name(filename))
        ):
            return None
        is_file = filename is not None
        parts.append(
            MultipartPart(
                name=name,
                kind="file" if is_file else "field",
                filename=filename,
                content_type=part.get_content_type() if is_file else None,
                size=len(payload),
            )
        )
    return MultipartSummary(parts=tuple(parts), total_bytes=sum(item.size for item in parts))

"""Logs estruturados em JSON no stderr, com redação de segredos.

O stdout é reservado ao resultado do comando; por isso os logs vão sempre ao stderr.
A redação é feita por um processador do structlog, de modo que nada sensível chega ao
renderizador, seja por chave (ex.: `authorization`), por valor registrado no
`SecretRegistry`, por padrão de JWT ou por CPF formatado.
"""

import logging
import re
import sys
from collections.abc import Callable, MutableMapping
from typing import TextIO, cast

import structlog
from structlog.typing import EventDict, WrappedLogger

MASK = "***"

# Fragmentos de chave (já normalizada para minúsculas e "_") cujo valor é sempre mascarado.
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "password",
    "passwd",
    "pwd",
    "senha",
    "token",
    "secret",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "bearer",
    "session",
)
# Nome de campo/cabeçalho (sem espaços): distingue o par ("Authorization", "x") de um par
# de textos livres como ("token expirado", "x"), que não deve ser mascarado.
_KEY_NAME = re.compile(r"[\w.\-]+")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
# Só CPF formatado: 11 dígitos soltos colidiriam com ids e timestamps.
_CPF = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")


class SecretRegistry:
    """Conjunto de valores secretos conhecidos em tempo de execução, mascarados onde aparecerem."""

    def __init__(self) -> None:
        """Cria um registro vazio."""
        self._values: set[str] = set()

    def register(self, value: str) -> None:
        """Registra um valor secreto. Valores vazios são ignorados.

        Args:
            value: O segredo em claro.
        """
        if value:
            self._values.add(value)

    def mask(self, text: str) -> str:
        """Substitui por `***` toda ocorrência de segredo registrado.

        Args:
            text: Texto de entrada (não é alterado).

        Returns:
            O texto com os segredos mascarados.
        """
        # Mais longos primeiro, para que um segredo contido em outro não deixe sobra.
        for value in sorted(self._values, key=len, reverse=True):
            text = text.replace(value, MASK)
        return text


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_value(value: object, registry: SecretRegistry) -> object:
    """Devolve cópia de `value` com dados sensíveis mascarados.

    Args:
        value: Valor arbitrário de log. Texto, bytes, dict, listas, tuplas e conjuntos são
            percorridos; um par `(chave, valor)` de chave sensível (cabeçalhos HTTP como
            lista de pares) tem o valor mascarado; qualquer outro objeto (exceção, objeto
            com `repr` próprio) vira texto e o texto é redigido; números, booleanos e
            `None` passam intactos.
        registry: Segredos conhecidos.

    Returns:
        Nova estrutura; o argumento original não é alterado.
    """
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _CPF.sub(MASK, _JWT.sub(MASK, registry.mask(value)))
    if isinstance(value, bytes | bytearray):
        return redact_value(bytes(value).decode("utf-8", errors="replace"), registry)
    if isinstance(value, dict):
        return {
            k: MASK if isinstance(k, str) and _is_sensitive_key(k) else redact_value(v, registry)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        return _redact_sequence(value, registry)
    # Segurança: objeto desconhecido (exceção, conexão...) seria renderizado depois, sem
    # redação, pelo repr/str dele; por isso a forma textual é redigida aqui.
    return redact_value(_describe(value), registry)


def _describe(value: object) -> str:
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {value}"
    return str(value)


def _redact_sequence(
    items: list[object] | tuple[object, ...] | set[object] | frozenset[object],
    registry: SecretRegistry,
) -> list[object]:
    if _is_sensitive_pair(items):
        pair = list(items)
        return [redact_value(pair[0], registry), MASK]
    return [redact_value(item, registry) for item in items]


def _is_sensitive_pair(items: object) -> bool:
    # ("Authorization", "...") é a forma usual de cabeçalhos HTTP em clientes e no ZAP.
    if not isinstance(items, list | tuple) or len(items) != 2:
        return False
    key = items[0]
    return isinstance(key, str) and bool(_KEY_NAME.fullmatch(key)) and _is_sensitive_key(key)


def build_redactor(
    registry: SecretRegistry,
) -> Callable[[WrappedLogger, str, MutableMapping[str, object]], EventDict]:
    """Cria o processador structlog que aplica a redação.

    Args:
        registry: Segredos conhecidos, consultados a cada evento.

    Returns:
        Processador compatível com `structlog.configure(processors=...)`.
    """

    def redact(
        _logger: WrappedLogger, _method: str, event_dict: MutableMapping[str, object]
    ) -> EventDict:
        return {
            key: MASK if _is_sensitive_key(key) else redact_value(value, registry)
            for key, value in event_dict.items()
        }

    return redact


class _CurrentStderr:
    """Destino de log que procura o `sys.stderr` a cada escrita.

    A configuração do structlog é global e vive mais que quem a criou. Guardar o objeto
    `sys.stderr` do momento da configuração faz o log escrever num fluxo antigo, que pode já
    estar fechado quando o stderr foi trocado depois (redirecionamento, captura em teste).
    """

    def write(self, text: str) -> int:
        """Escreve no stderr vigente e devolve o total de caracteres escritos."""
        return sys.stderr.write(text)

    def flush(self) -> None:
        """Descarrega o stderr vigente."""
        sys.stderr.flush()


def configure_logging(level: str, registry: SecretRegistry, stream: TextIO | None = None) -> None:
    """Configura o structlog para JSON no stderr com redação.

    Args:
        level: Nome do nível mínimo (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
        registry: Segredos conhecidos a mascarar.
        stream: Destino dos logs; por padrão o stderr vigente no momento de cada escrita.
    """
    # O PrintLogger só usa `write` e `flush`; o cast evita herdar de uma classe de E/S.
    target = stream if stream is not None else cast("TextIO", _CurrentStderr())
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            build_redactor(registry),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(file=target),
        cache_logger_on_first_use=False,
    )

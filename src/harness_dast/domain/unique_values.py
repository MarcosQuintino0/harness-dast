"""Esquema de valores únicos por execução, rastreáveis pela limpeza.

Problema: dados que não podem repetir (CPF, código numérico, e-mail) não podem colidir
nem com a execução anterior nem com outra operação da mesma execução (HTTP 409), e a
limpeza precisa achar depois o que foi criado.

Esquema (contrato público; a limpeza SQL do produto se apoia nele):

- **Etiqueta da execução** (`run_tag`): o sufixo hexadecimal do `RunId` (4 a 8 dígitos
  hex). Duas execuções têm etiquetas diferentes com alta probabilidade.
- **Contador**: inteiro de 0 em diante, um só por execução, avançado a cada valor único
  pedido (em qualquer regra). Dois valores da mesma execução nunca usam o mesmo contador.
- **Texto** (`unique_token`): `etiqueta` + contador em 4 dígitos hex (`7f3a0012`). Se o
  campo for curto, a etiqueta é cortada pela direita; o contador nunca é cortado.
  Capacidade: 65 536 valores por execução.
- **Dígitos** (`unique_digits`): `largura` dígitos decimais, com o contador nos últimos
  `c` dígitos (`c` = a largura inteira se for até 4; senão metade da largura, no mínimo 4)
  e o restante preenchido com `int(etiqueta, 16) % 10**p` (p = dígitos restantes). Capacidade:
  `10**c` valores por execução (10 000 para CPF e CNPJ). Para achar: o prefixo é recalculável
  a partir da etiqueta.

Este módulo é puro: quem sorteia o resto do valor é o adaptador, com semente injetada.
"""

import re

from harness_dast.domain.errors import ConfigError

_RUN_TAG = re.compile(r"[0-9a-f]{4,8}")
COUNTER_HEX_DIGITS = 4
MAX_UNIQUE_TOKENS = 16**COUNTER_HEX_DIGITS


def validate_run_tag(run_tag: str) -> str:
    """Confere que a etiqueta tem 4 a 8 dígitos hexadecimais minúsculos.

    Raises:
        ConfigError: Se a etiqueta for inválida.
    """
    if not _RUN_TAG.fullmatch(run_tag):
        raise ConfigError(
            "Etiqueta de execução inválida: esperados 4 a 8 dígitos hexadecimais minúsculos.",
            hint="Use o sufixo do identificador da execução (RunId).",
        )
    return run_tag


def run_tag_from_run_id(run_id: str) -> str:
    """Extrai a etiqueta (último trecho após o hífen) de um identificador de execução.

    Raises:
        ConfigError: Se o trecho final não for uma etiqueta válida.
    """
    return validate_run_tag(run_id.rsplit("-", 1)[-1])


def unique_token(run_tag: str, counter: int, max_length: int | None = None) -> str:
    """Monta o texto único `etiqueta + contador(4 hex)`, cabendo em `max_length`.

    Args:
        run_tag: Etiqueta da execução.
        counter: Contador do valor, de 0 a 65 535.
        max_length: Tamanho máximo permitido pelo campo, ou `None`.

    Returns:
        O texto; a etiqueta é cortada pela direita se for preciso, o contador nunca.

    Raises:
        ConfigError: Contador fora da capacidade ou campo curto demais para o contador.
    """
    if not 0 <= counter < MAX_UNIQUE_TOKENS:
        raise ConfigError(
            f"Foram pedidos mais de {MAX_UNIQUE_TOKENS} valores únicos nesta execução.",
            hint="Divida o teste em execuções menores.",
        )
    suffix = f"{counter:0{COUNTER_HEX_DIGITS}x}"
    if max_length is None:
        return run_tag + suffix
    if max_length < COUNTER_HEX_DIGITS:
        raise ConfigError(
            f"Campo único com tamanho máximo menor que {COUNTER_HEX_DIGITS} caracteres.",
            hint="Use uma regra com gerador numérico ou constante para este campo.",
        )
    return run_tag[: max_length - COUNTER_HEX_DIGITS] + suffix


def counter_digits(width: int) -> int:
    """Quantos dígitos decimais do final de um número de `width` dígitos guardam o contador."""
    return width if width <= COUNTER_HEX_DIGITS else max(COUNTER_HEX_DIGITS, width // 2)


def unique_digits(run_tag: str, counter: int, width: int) -> str:
    """Monta `width` dígitos decimais únicos: prefixo da etiqueta + contador.

    Args:
        run_tag: Etiqueta da execução.
        counter: Contador do valor.
        width: Quantidade de dígitos pedida (pelo menos 1).

    Returns:
        Texto de exatamente `width` dígitos.

    Raises:
        ConfigError: Se `counter` não cabe nos dígitos reservados ao contador.
    """
    tail = counter_digits(width)
    if counter < 0 or counter >= 10**tail:
        raise ConfigError(
            f"Foram pedidos mais de {10**tail} valores únicos de {width} dígitos nesta execução.",
            hint="Aumente os dígitos do gerador ou divida o teste em execuções menores.",
        )
    head = width - tail
    prefix = str(int(run_tag, 16) % 10**head).zfill(head) if head else ""
    return prefix + str(counter).zfill(tail)

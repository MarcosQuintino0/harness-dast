"""Classe de um nome de campo: segredo, dado pessoal ou comum (lista fixa e testada).

Usada pela verificação de exposição excessiva (a severidade sobe quando o NOME do campo
indica segredo ou dado pessoal) e pelo `probe` ao gravar corpos de requisição (campo com nome
de segredo nunca é gravado). A decisão olha só o nome, em palavras (`senhaHash` vira `senha` e
`hash`), nunca o valor. A lista é conservadora de propósito: acertar o nome é decisão de
severidade, então uma palavra ambígua fica de fora. Este módulo é puro.
"""

import re
from typing import Final, Literal

FieldClass = Literal["secret", "personal", "plain"]

SECRET_WORDS: Final[frozenset[str]] = frozenset(
    {
        "senha",
        "password",
        "passwd",
        "pwd",
        "hash",
        "token",
        "secret",
        "segredo",
        "salt",
        "otp",
        "credential",
        "credentials",
        "credencial",
        "credenciais",
        "apikey",
        "cvv",
    }
)
"""Palavras que, sozinhas, marcam um campo como segredo."""

SECRET_COMPOUNDS: Final[tuple[str, ...]] = (
    "apikey",
    "privatekey",
    "secretkey",
    "accesskey",
    "chaveprivada",
    "chavesecreta",
)
"""Nomes compostos (sem separador) que marcam segredo: `api_key`, `privateKey`..."""

PERSONAL_WORDS: Final[frozenset[str]] = frozenset(
    {
        "cpf",
        "cnpj",
        "rg",
        "ssn",
        "passaporte",
        "passport",
        "email",
        "telefone",
        "phone",
        "celular",
        "nascimento",
        "birth",
        "birthdate",
        "endereco",
        "address",
        "cartao",
        "card",
        "salario",
        "salary",
        "prontuario",
        "diagnostico",
    }
)
"""Palavras que marcam dado pessoal."""

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SEPARATORS = re.compile(r"[^A-Za-z0-9]+")


def _words(name: str) -> tuple[str, ...]:
    spaced = _CAMEL.sub(" ", name)
    return tuple(word.lower() for word in _SEPARATORS.sub(" ", spaced).split() if word)


def classify_field_name(name: str) -> FieldClass:
    """Classifica o NOME de um campo: `secret`, `personal` ou `plain`.

    Segredo vence dado pessoal (`emailToken` é segredo). A decisão usa só o nome.
    """
    words = _words(name)
    joined = "".join(words)
    if any(word in SECRET_WORDS for word in words) or any(c in joined for c in SECRET_COMPOUNDS):
        return "secret"
    if any(word in PERSONAL_WORDS for word in words):
        return "personal"
    return "plain"

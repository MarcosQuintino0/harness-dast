"""Bloco opcional `probe` do `target.yml`: como reconhecer sucesso e onde checar a saúde.

Por que existe: o spike do M0 mostrou alvos que respondem HTTP 200 com o corpo
`{"status":"fail"}`. Contar só o código HTTP superestimaria a alcançabilidade. O perfil pode
declarar uma regra de corpo pequena; sem ela, vale "2xx". Este módulo é puro.
"""

import re
from typing import Literal, Self

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.pathpattern import parse_pattern
from harness_dast.domain.secret_ref import ProfileModel

_DOTTED_PATH = re.compile(r"[A-Za-z0-9_-]{1,64}(?:\.[A-Za-z0-9_-]{1,64}){0,9}")


def read_field(body: JsonValue, dotted: str) -> JsonValue:
    """Valor no caminho pontuado, ou `None` se o corpo não é objeto ou falta algum segmento."""
    current: JsonValue = body
    for segment in dotted.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


class JsonFieldRule(ProfileModel):
    """Campo do corpo JSON que denuncia falha lógica quando tem um valor conhecido.

    Attributes:
        field: Caminho pontuado do campo na resposta (`status`, `data.result`).
        value: Valor de FALHA (texto, inteiro ou booleano). O tipo importa: `1` não é `true`.
    """

    field: str
    value: StrictStr | StrictInt | StrictBool

    @field_validator("field")
    @classmethod
    def validate_field(cls, value: str) -> str:
        """Confere o caminho pontuado."""
        if not _DOTTED_PATH.fullmatch(value):
            raise ValueError("caminho de campo inválido (ex.: status ou data.result)")
        return value

    def is_failure(self, body: JsonValue) -> bool:
        """Diz se o corpo traz o campo com o valor de falha.

        Campo ausente, corpo que não é objeto e valor diferente (inclusive de outro tipo)
        significam "não é falha".
        """
        found = read_field(body, self.field)
        return type(found) is type(self.value) and found == self.value


class SuccessCriteria(ProfileModel):
    """Critério de sucesso além do código HTTP (padrão: apenas 2xx).

    Attributes:
        json_field_absent_or_not_equal: Uma resposta 2xx só é sucesso se o campo estiver
            ausente OU tiver valor diferente do de falha informado.
    """

    json_field_absent_or_not_equal: JsonFieldRule | None = None


ErrorOutcome = Literal[
    "validation_error",
    "conflict",
    "auth_error",
    "csrf_error",
    "not_found",
    "rate_limited",
    "client_error",
    "server_error",
]
"""Classes de resultado que `probe.error_codes` pode atribuir a um código de erro do alvo."""

_ERROR_CODE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
MAX_ERROR_CODES = 100


class ErrorCodes(ProfileModel):
    """Mapa de códigos de erro do corpo JSON do alvo para classes de resultado.

    Com ele, o `probe` classifica pelo código declarado (exato) em vez de heurística por
    status HTTP. Código ausente da resposta ou não declarado cai na heurística de sempre.

    Attributes:
        field: Caminho pontuado do campo com o código (`code`, `error.code`).
        outcomes: Classe de resultado -> códigos. Um código só pode estar numa classe.
    """

    field: str
    outcomes: dict[ErrorOutcome, tuple[str, ...]] = Field(min_length=1)

    @field_validator("field")
    @classmethod
    def validate_field(cls, value: str) -> str:
        """Confere o caminho pontuado."""
        if not _DOTTED_PATH.fullmatch(value):
            raise ValueError("caminho de campo inválido (ex.: code ou error.code)")
        return value

    @model_validator(mode="after")
    def validate_codes(self) -> Self:
        """Confere o formato dos códigos, a unicidade entre classes e o teto de quantidade."""
        seen: set[str] = set()
        for codes in self.outcomes.values():
            for code in codes:
                if not _ERROR_CODE.fullmatch(code):
                    raise ValueError("código de erro inválido; use letras, dígitos e _ . : -")
                if code in seen:
                    raise ValueError("um código de erro só pode estar em uma classe de resultado")
                seen.add(code)
        if len(seen) > MAX_ERROR_CODES:
            raise ValueError(f"no máximo {MAX_ERROR_CODES} códigos de erro")
        return self

    def outcome_for(self, body: JsonValue) -> ErrorOutcome | None:
        """Classe declarada para o código presente no corpo, ou `None`.

        Só texto e inteiro são códigos válidos; qualquer outra coisa (ausente, lista,
        objeto) não classifica.
        """
        found = read_field(body, self.field)
        if isinstance(found, bool) or not isinstance(found, str | int):
            return None
        code = str(found)
        for outcome, codes in self.outcomes.items():
            if code in codes:
                return outcome
        return None


class ProbeConfig(ProfileModel):
    """Configuração opcional do `probe` e do `preflight`.

    Attributes:
        success: Critério de sucesso.
        health_path: Caminho literal de um GET leve usado pelo `preflight` para checar a saúde
            do alvo; ausente, usa a raiz da `base_url`. Precisa estar no escopo (GET).
        error_codes: Classificação exata por código de erro do corpo, opcional.
    """

    success: SuccessCriteria = SuccessCriteria()
    health_path: str | None = None
    error_codes: ErrorCodes | None = None

    @field_validator("health_path")
    @classmethod
    def validate_health_path(cls, value: str | None) -> str | None:
        """Exige caminho literal começando com '/', sem curingas."""
        if value is None:
            return value
        parse_pattern(value)
        if "*" in value:
            raise ValueError("health_path deve ser um caminho literal, sem curingas")
        return value

"""Bloco opcional `probe` do `target.yml`: como reconhecer sucesso e onde checar a saúde.

Por que existe: o spike do M0 mostrou alvos que respondem HTTP 200 com o corpo
`{"status":"fail"}`. Contar só o código HTTP superestimaria a alcançabilidade. O perfil pode
declarar uma regra de corpo pequena; sem ela, vale "2xx". Este módulo é puro.
"""

import re

from pydantic import StrictBool, StrictInt, StrictStr, field_validator

from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.pathpattern import parse_pattern
from harness_dast.domain.secret_ref import ProfileModel

_DOTTED_PATH = re.compile(r"[A-Za-z0-9_-]{1,64}(?:\.[A-Za-z0-9_-]{1,64}){0,9}")


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
        current: JsonValue = body
        for segment in self.field.split("."):
            if not isinstance(current, dict) or segment not in current:
                return False
            current = current[segment]
        return type(current) is type(self.value) and current == self.value


class SuccessCriteria(ProfileModel):
    """Critério de sucesso além do código HTTP (padrão: apenas 2xx).

    Attributes:
        json_field_absent_or_not_equal: Uma resposta 2xx só é sucesso se o campo estiver
            ausente OU tiver valor diferente do de falha informado.
    """

    json_field_absent_or_not_equal: JsonFieldRule | None = None


class ProbeConfig(ProfileModel):
    """Configuração opcional do `probe` e do `preflight`.

    Attributes:
        success: Critério de sucesso.
        health_path: Caminho literal de um GET leve usado pelo `preflight` para checar a saúde
            do alvo; ausente, usa a raiz da `base_url`. Precisa estar no escopo (GET).
    """

    success: SuccessCriteria = SuccessCriteria()
    health_path: str | None = None

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

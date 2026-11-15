"""Bloco opcional `negative` do `target.yml`: o teste de valores que o esquema proíbe (ADR 0051).

Nada aqui amplia escopo, métodos permitidos pelo escopo, janela ou limites (o `ScopeGuard`
continua decidindo). Mas `allow_writes` escreve no alvo, `max_*` é carga e `disabled_classes`
esconde achado: por isso o bloco entra na impressão digital da aprovação humana quando difere do
padrão (ADR 0037). `allow_writes` vem da carta (`attack.allow_invalid_input_writes`); os demais
campos o agente ajusta, e a aprovação os trava. Este módulo é puro.
"""

from typing import Final

from pydantic import Field, StrictBool, StrictInt, field_validator

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.negative_values import CLASS_ORDER, CaseClass
from harness_dast.domain.secret_ref import ProfileModel

DEFAULT_CASES_PER_OPERATION: Final = 6
MAX_CASES_PER_OPERATION: Final = 20
DEFAULT_MAX_REQUESTS: Final = 200
MAX_REQUESTS_CEILING: Final = 1_000


class NegativeConfig(ProfileModel):
    """Configuração do teste negativo de validação de entrada.

    Attributes:
        allow_writes: Se o teste pode gravar dado inválido no ambiente (`POST`, `PUT`, `PATCH`).
            Padrão `false`; `true` só vem da carta. Campo próprio: não reaproveita
            `authz.allow_writes`.
        max_cases_per_operation: Teto de casos por operação (1 a 20).
        max_requests: Teto de envios do estágio inteiro, casos e restaurações (1 a 1 000).
        disabled_classes: Classes que não se testam (só reduz); sem repetição.
    """

    allow_writes: StrictBool = False
    max_cases_per_operation: StrictInt = Field(
        default=DEFAULT_CASES_PER_OPERATION, ge=1, le=MAX_CASES_PER_OPERATION
    )
    max_requests: StrictInt = Field(default=DEFAULT_MAX_REQUESTS, ge=1, le=MAX_REQUESTS_CEILING)
    disabled_classes: tuple[CaseClass, ...] = Field(default=(), max_length=len(CLASS_ORDER))

    @field_validator("disabled_classes")
    @classmethod
    def validate_unique(cls, value: tuple[CaseClass, ...]) -> tuple[CaseClass, ...]:
        """Recusa classe repetida."""
        if len(set(value)) != len(value):
            raise ValueError("classe repetida em disabled_classes")
        return value

    def effective_max_requests(self, asked: int | None) -> int:
        """Teto de envios depois de `--max-requests`: a flag só reduz.

        Raises:
            ConfigError: Pedido menor que 1 ou acima do teto do perfil.
        """
        if asked is None:
            return self.max_requests
        if asked < 1 or asked > self.max_requests:
            raise ConfigError(
                "--max-requests precisa ficar entre 1 e o teto do perfil "
                f"(negative.max_requests: {self.max_requests}).",
                hint="Flags só reduzem a carga; para aumentar o teto, mude o perfil e aprove.",
            )
        return asked

    def is_default(self) -> bool:
        """Se o bloco vale o padrão (a impressão digital o deixa de fora, ADR 0051)."""
        return self == type(self)()

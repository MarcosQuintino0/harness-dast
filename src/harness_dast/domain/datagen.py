"""Regras de dados declarativas (`data-rules.yml`): modelo, validação e resolução.

Uma regra diz "no campo X (opcionalmente só na operação Y e/ou só no local Z) use o gerador
G com estes argumentos, único ou não". O agente escreve as regras; este módulo valida cada
uma contra o catálogo fechado de geradores e decide qual regra vale para cada campo.

**Precedência (contrato).** Para um campo da requisição, entre as regras que casam vale a
mais específica, comparando nesta ordem: (1) tem `operation`; (2) tem mais segmentos em
`field` (`endereco.cpf` vence `cpf`); (3) tem `location`. Duas regras com o mesmo
`match` completo são ambíguas e o arquivo é recusado: não existe empate silencioso. Este
módulo é puro.
"""

from collections.abc import Iterator
from typing import Literal, Self

from pydantic import Field, StrictBool, model_validator

from harness_dast.domain.api_model import ApiSpec, Operation, safe_identifier
from harness_dast.domain.api_schema import ApiModel, Schema, flatten_schema
from harness_dast.domain.datagen_catalog import get_generator, validate_args
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.synthetic_files import resolve_file
from harness_dast.domain.versioned import validate_versioned

RuleLocation = Literal["path", "query", "header", "cookie", "body"]
MAX_RULES = 500
_RULES_HINT = "Corrija os campos indicados no data-rules.yml do produto."
_FIELD_PATTERN = r"^[^\s.\x00-\x1f]{1,100}(\.[^\s.\x00-\x1f]{1,100}){0,9}$"
_MAX_SCAN_DEPTH = 8


class RuleMatch(ApiModel):
    """Onde uma regra vale.

    Attributes:
        field: Nome do campo (`cpf`) ou caminho com pontos (`endereco.cpf`), comparado com
            o FINAL do caminho do campo na requisição, sem distinguir índices de lista.
        operation: Restringe a uma operação (`operation_id`).
        location: Restringe a `path`, `query`, `header`, `cookie` ou `body`.
    """

    field: str = Field(pattern=_FIELD_PATTERN)
    operation: str | None = Field(default=None, min_length=1, max_length=200)
    location: RuleLocation | None = None

    @property
    def segments(self) -> tuple[str, ...]:
        """Segmentos de `field`."""
        return tuple(self.field.split("."))

    def key(self) -> tuple[str, str | None, str | None]:
        """Identidade completa do casamento, usada para detectar regras ambíguas."""
        return (self.field, self.operation, self.location)

    def specificity(self) -> tuple[bool, int, bool]:
        """Chave de comparação da precedência (maior = mais específica)."""
        return (self.operation is not None, len(self.segments), self.location is not None)

    def applies_to(self, operation_id: str, location: str, field_path: tuple[str, ...]) -> bool:
        """Diz se o casamento vale para este campo."""
        return (
            self.operation in (None, operation_id)
            and self.location in (None, location)
            and field_path[-len(self.segments) :] == self.segments
        )


class DataRule(ApiModel):
    """Uma regra: casamento, gerador, argumentos e unicidade.

    Attributes:
        match: Onde a regra vale.
        generator: Nome no catálogo fechado.
        args: Argumentos do gerador (validados contra o catálogo).
        unique: Se cada requisição precisa de um valor novo na execução.
    """

    match: RuleMatch
    generator: str = Field(min_length=1, max_length=40)
    args: dict[str, object] = Field(default_factory=dict)
    unique: StrictBool = False

    @model_validator(mode="after")
    def validate_generator(self) -> Self:
        """Confere gerador, argumentos e se ele aceita `unique`."""
        try:
            definition = get_generator(self.generator)
            checked = validate_args(definition, self.args)
            if definition.name == "synthetic_file":
                name = checked.get("name")
                resolve_file(str(checked.get("kind")), name if isinstance(name, str) else None)
        except ConfigError as error:
            raise ValueError(error.message) from None
        if self.unique and not definition.supports_unique:
            raise ValueError(f"o gerador '{definition.name}' não aceita unique: true")
        return self


class ResolvedRule(ApiModel):
    """Regra escolhida para um campo, com sua posição no arquivo (começa em 0)."""

    index: int
    rule: DataRule


class DataRules(ApiModel):
    """O `data-rules.yml` completo, já validado em si mesmo.

    Attributes:
        schema_version: Versão do schema (somente 1).
        rules: As regras, na ordem do arquivo.
    """

    schema_version: int
    rules: tuple[DataRule, ...] = Field(default=(), max_length=MAX_RULES)

    @model_validator(mode="after")
    def validate_no_ambiguity(self) -> Self:
        """Recusa duas regras com o mesmo `match` (qual valeria seria arbitrário)."""
        seen: dict[tuple[str, str | None, str | None], int] = {}
        for index, rule in enumerate(self.rules):
            key = rule.match.key()
            if key in seen:
                raise ValueError(
                    f"regras {seen[key] + 1} e {index + 1} têm o mesmo match (ambíguo); "
                    "mantenha só uma"
                )
            seen[key] = index
        return self

    @classmethod
    def from_data(cls, data: object) -> Self:
        """Constrói as regras a partir do YAML já lido.

        Raises:
            ConfigError: Estrutura inválida, gerador desconhecido, argumento inválido,
                `unique` num gerador que não o aceita ou regras ambíguas. A mensagem lista
                cada problema por caminho (`rules[2].generator`) sem repetir valores.
        """
        return validate_versioned(cls, data, document="data-rules.yml", hint=_RULES_HINT)

    def resolve(
        self, operation_id: str, location: RuleLocation, field_path: tuple[str, ...]
    ) -> ResolvedRule | None:
        """Escolhe a regra mais específica para um campo, ou `None` se nenhuma casa.

        Args:
            operation_id: Operação que está sendo montada.
            location: Local do campo na requisição.
            field_path: Caminho do campo sem índices de lista (`("endereco", "cpf")`).

        Returns:
            A regra vencedora com seu índice, ou `None`.
        """
        best: ResolvedRule | None = None
        for index, rule in enumerate(self.rules):
            if not rule.match.applies_to(operation_id, location, field_path):
                continue
            if best is None or rule.match.specificity() > best.rule.match.specificity():
                best = ResolvedRule(index=index, rule=rule)
        return best

    def validate_against(self, spec: ApiSpec) -> tuple[int, ...]:
        """Confere as regras contra o OpenAPI e aponta as que não casam com nenhum campo.

        Returns:
            Índices (a partir de 0) das regras que não casam com campo algum da API: costumam
            ser erro de digitação. Não é erro, porque uma regra global pode sobrar.

        Raises:
            ConfigError: Alguma regra cita uma `operation` inexistente.
        """
        for rule in self.rules:
            if rule.match.operation is not None and not spec.has_operation(rule.match.operation):
                raise ConfigError(
                    f"Uma regra cita a operação {safe_identifier(rule.match.operation)}, que "
                    "não existe no OpenAPI.",
                    hint="Corrija match.operation em data-rules.yml.",
                )
        positions = [
            (op.operation_id, location, path)
            for op in spec.operations
            for location, path in _field_positions(op)
        ]
        return tuple(
            index
            for index, rule in enumerate(self.rules)
            if not any(rule.match.applies_to(*position) for position in positions)
        )


def _field_positions(operation: Operation) -> Iterator[tuple[str, tuple[str, ...]]]:
    for parameter in operation.parameters:
        yield parameter.location, (parameter.name,)
    media = operation.request_body.preferred() if operation.request_body else None
    if media is not None and media.body_schema is not None:
        for path in _property_paths(media.body_schema, (), 0):
            yield "body", path


def _property_paths(
    schema: Schema, prefix: tuple[str, ...], depth: int
) -> Iterator[tuple[str, ...]]:
    if depth >= _MAX_SCAN_DEPTH:
        return
    flat = flatten_schema(schema)
    if flat.items is not None:
        yield from _property_paths(flat.items, prefix, depth + 1)
    for name, sub in flat.properties.items():
        yield (*prefix, name)
        yield from _property_paths(sub, (*prefix, name), depth + 1)

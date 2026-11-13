"""Encadeamento de dados entre operações (`flows.yml`): modelo, validação e ordenação.

Um *binding* diz: a operação P PRODUZ um valor (campo da resposta) e as operações C1, C2...
o CONSOMEM (num parâmetro ou num campo do corpo). Exemplo: `criarPaciente` devolve `id`;
`buscarPaciente` o usa no parâmetro `pacienteId`.

**Vários níveis (DAG).** Uma operação pode consumir de uma e produzir para outra:
`convenio -> paciente -> consulta -> receita` é aceito. O encadeamento é um grafo dirigido
sem ciclos. Continuam recusados: ciclo (`A -> B -> A`) e auto-referência (`A -> A`) e uma
cadeia mais funda que `MAX_FLOW_DEPTH` operações. Continua permitido um produtor para vários
consumidores e um consumidor com vários produtores (`A1 -> B` e `A2 -> B`), desde que cada
alvo (`B.param` ou `B.field`) tenha uma só fonte.

Este módulo é puro: a resposta do produtor chega como dado já decodificado.
"""

import heapq
from collections.abc import Mapping, Sequence
from typing import Self

from pydantic import Field, model_validator

from harness_dast.domain.api_model import ApiSpec, Operation, safe_identifier
from harness_dast.domain.api_schema import (
    ApiModel,
    JsonValue,
    Schema,
    find_property_path,
    split_field_path,
)
from harness_dast.domain.errors import ConfigError, TargetError
from harness_dast.domain.versioned import validate_versioned

_FLOWS_HINT = "Corrija os campos indicados no flows.yml do produto."
MAX_BINDINGS = 200
MAX_CONSUMERS = 50
MAX_FLOW_DEPTH = 6
"""Maior número de operações numa cadeia produtor -> consumidor (a V1 do pilot usa 4)."""
_FIELD_PATH = r"^[^\s.]{1,100}(\.[^\s.]{1,100}){0,9}$"

type BoundValue = str | int


class ProducedRef(ApiModel):
    """Origem de um valor: a operação e o caminho do campo na resposta (`id`, `data.id`)."""

    operation: str = Field(min_length=1, max_length=200)
    field: str = Field(pattern=_FIELD_PATH)


class ConsumerRef(ApiModel):
    """Destino de um valor: uma operação e UM entre `param` (parâmetro) e `field` (corpo)."""

    operation: str = Field(min_length=1, max_length=200)
    param: str | None = Field(default=None, min_length=1, max_length=200)
    field: str | None = Field(default=None, pattern=_FIELD_PATH)

    @model_validator(mode="after")
    def validate_exactly_one_target(self) -> Self:
        """Exige exatamente um entre `param` e `field`."""
        if (self.param is None) == (self.field is None):
            raise ValueError("informe exatamente um entre 'param' e 'field'")
        return self

    @property
    def target(self) -> tuple[str, str]:
        """Par (`param` ou `field`, nome) que identifica o destino na operação."""
        if self.param is not None:
            return "param", self.param
        return "field", self.field or ""


class Binding(ApiModel):
    """Um produtor e os consumidores do valor que ele produz."""

    produces: ProducedRef
    consumed_by: tuple[ConsumerRef, ...] = Field(min_length=1, max_length=MAX_CONSUMERS)


class ResolvedBindings(ApiModel):
    """Valores já extraídos para uma operação consumidora.

    Attributes:
        params: Nome do parâmetro -> valor.
        fields: Caminho do campo do corpo -> valor.
    """

    params: dict[str, BoundValue] = Field(default_factory=dict)
    fields: dict[str, BoundValue] = Field(default_factory=dict)


def extract_value(body: JsonValue, path: str) -> BoundValue:
    """Extrai de um corpo de resposta o valor no caminho `path` (`id`, `data.id`, `items.0.id`).

    Segmento numérico indexa uma lista. Só texto e inteiro servem como valor encadeado.

    Raises:
        TargetError: O caminho não existe na resposta, ou o valor não é texto nem inteiro.
            A mensagem cita o caminho, nunca o conteúdo da resposta.
    """
    current = body
    for segment in split_field_path(path):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            raise TargetError(
                f"A resposta não contém o campo {safe_identifier(path)}.",
                hint="Confira o caminho em flows.yml ou se a operação produtora teve sucesso.",
            )
    if isinstance(current, bool) or not isinstance(current, str | int):
        raise TargetError(
            f"O campo {safe_identifier(path)} da resposta não é texto nem inteiro.",
            hint="Só valores simples (texto ou inteiro) podem ser encadeados.",
        )
    return current


def _find_cycle(edges: Mapping[str, tuple[str, ...]]) -> list[str] | None:
    """Acha um ciclo (DFS iterativa, determinística); devolve o caminho ou `None`."""
    state: dict[str, int] = {}
    for root in edges:
        if root in state:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        path: list[str] = [root]
        state[root] = 1
        while stack:
            node, index = stack[-1]
            targets = edges.get(node, ())
            if index >= len(targets):
                state[node] = 2
                stack.pop()
                path.pop()
                continue
            stack[-1] = (node, index + 1)
            nxt = targets[index]
            if state.get(nxt) == 1:
                return [*path[path.index(nxt) :], nxt]
            if nxt not in state:
                state[nxt] = 1
                stack.append((nxt, 0))
                path.append(nxt)
    return None


def _longest_chain(edges: Mapping[str, tuple[str, ...]]) -> int:
    """Número de operações do maior caminho; o grafo já não tem ciclo."""
    memo: dict[str, int] = {}

    def depth(node: str) -> int:
        if node not in memo:
            memo[node] = 1 + max((depth(nxt) for nxt in edges.get(node, ())), default=0)
        return memo[node]

    return max((depth(node) for node in edges), default=0)


class FlowSpec(ApiModel):
    """O `flows.yml` completo, já validado em si mesmo.

    Attributes:
        schema_version: Versão do schema (somente 1).
        bindings: Os encadeamentos declarados.
    """

    schema_version: int
    bindings: tuple[Binding, ...] = Field(default=(), max_length=MAX_BINDINGS)

    @model_validator(mode="after")
    def validate_structure(self) -> Self:
        """Rejeita alvo repetido, ciclo (inclui auto-referência) e cadeia funda demais."""
        targets: set[tuple[str, str, str]] = set()
        for binding in self.bindings:
            for consumer in binding.consumed_by:
                key = (consumer.operation, *consumer.target)
                if key in targets:
                    raise ValueError(
                        f"o destino {safe_identifier(consumer.operation)}."
                        f"{safe_identifier(key[2])} recebe valor de mais de uma fonte"
                    )
                targets.add(key)
        edges = self._edges()
        cycle = _find_cycle(edges)
        if cycle is not None:
            names = " -> ".join(safe_identifier(name) for name in cycle)
            raise ValueError(f"ciclo entre operações: {names}; o encadeamento não pode ter ciclos")
        depth = _longest_chain(edges)
        if depth > MAX_FLOW_DEPTH:
            raise ValueError(
                f"cadeia de {depth} operações; o máximo é {MAX_FLOW_DEPTH} "
                "(divida o encadeamento ou use valores constantes)"
            )
        return self

    def _edges(self) -> dict[str, tuple[str, ...]]:
        edges: dict[str, list[str]] = {}
        for binding in self.bindings:
            targets = edges.setdefault(binding.produces.operation, [])
            targets.extend(c.operation for c in binding.consumed_by)
        return {name: tuple(dict.fromkeys(targets)) for name, targets in edges.items()}

    @classmethod
    def from_data(cls, data: object) -> Self:
        """Constrói o `FlowSpec` a partir do YAML já lido.

        Raises:
            ConfigError: Estrutura inválida, alvo repetido, ciclo ou mais de um nível. A
                mensagem lista cada problema por caminho e não repete valores recebidos.
        """
        return validate_versioned(cls, data, document="flows.yml", hint=_FLOWS_HINT)

    def validate_against(self, spec: ApiSpec) -> None:
        """Confere operações, parâmetros e campos do `flows.yml` contra o OpenAPI.

        O campo produzido é conferido no esquema da resposta de sucesso. Se a operação não
        declara esquema de resposta, o campo não pode ser conferido e é aceito.

        Raises:
            ConfigError: Operação, parâmetro ou campo inexistente.
        """
        for binding in self.bindings:
            producer = spec.get_operation(binding.produces.operation)
            _check_produced(producer, binding.produces.field)
            for consumer in binding.consumed_by:
                _check_consumed(spec.get_operation(consumer.operation), consumer)

    def execution_order(self, operation_ids: Sequence[str]) -> tuple[str, ...]:
        """Ordena as operações para que todo produtor venha antes de seus consumidores.

        Sem dependência entre duas operações, vale a ordem de `operation_ids` (estável e
        determinística). Operações do `flows.yml` ausentes da lista são ignoradas.

        Args:
            operation_ids: Todas as operações a executar, na ordem do OpenAPI.

        Returns:
            As mesmas operações, reordenadas.
        """
        position = {name: index for index, name in enumerate(operation_ids)}
        waiting: dict[str, set[str]] = {name: set() for name in operation_ids}
        followers: dict[str, list[str]] = {}
        for binding in self.bindings:
            producer = binding.produces.operation
            for consumer in binding.consumed_by:
                if producer in position and consumer.operation in position:
                    waiting[consumer.operation].add(producer)
                    followers.setdefault(producer, []).append(consumer.operation)
        ready = [position[name] for name, deps in waiting.items() if not deps]
        heapq.heapify(ready)
        order: list[str] = []
        while ready:
            name = operation_ids[heapq.heappop(ready)]
            order.append(name)
            for follower in followers.get(name, ()):
                waiting[follower].discard(name)
                if not waiting[follower]:
                    heapq.heappush(ready, position[follower])
        return tuple(order)

    def resolve_bindings(
        self, operation_id: str, responses: Mapping[str, JsonValue]
    ) -> ResolvedBindings:
        """Extrai das respostas dos produtores os valores que `operation_id` consome.

        Args:
            operation_id: A operação consumidora.
            responses: Corpo JSON da resposta de cada produtor, por `operation_id`.

        Returns:
            Os valores por parâmetro e por campo (vazio se a operação não consome nada).

        Raises:
            TargetError: Falta a resposta de um produtor ou o campo nela.
        """
        params: dict[str, BoundValue] = {}
        fields: dict[str, BoundValue] = {}
        for binding in self.bindings:
            for consumer in binding.consumed_by:
                if consumer.operation != operation_id:
                    continue
                producer = binding.produces.operation
                if producer not in responses:
                    raise TargetError(
                        f"Falta a resposta da operação {safe_identifier(producer)}, que "
                        f"produz um valor para {safe_identifier(operation_id)}.",
                        hint="Execute a operação produtora antes e confira se ela teve sucesso.",
                    )
                value = extract_value(responses[producer], binding.produces.field)
                kind, name = consumer.target
                (params if kind == "param" else fields)[name] = value
        return ResolvedBindings(params=params, fields=fields)


def _check_produced(operation: Operation, field: str) -> None:
    schema = operation.success_schema()
    if schema is not None and find_property_path(schema, split_field_path(field)) is None:
        raise ConfigError(
            f"A operação {safe_identifier(operation.operation_id)} não tem o campo "
            f"{safe_identifier(field)} na resposta de sucesso.",
            hint="Corrija o caminho em produces.field de flows.yml.",
        )


def _body_schema(operation: Operation) -> Schema | None:
    media = operation.request_body.preferred() if operation.request_body else None
    return media.body_schema if media else None


def _check_consumed(operation: Operation, consumer: ConsumerRef) -> None:
    name = safe_identifier(operation.operation_id)
    if consumer.param is not None:
        if not any(p.name == consumer.param for p in operation.parameters):
            raise ConfigError(
                f"A operação {name} não tem o parâmetro {safe_identifier(consumer.param)}.",
                hint="Corrija consumed_by[].param de flows.yml.",
            )
        return
    schema = _body_schema(operation)
    field = consumer.field or ""
    if schema is None or find_property_path(schema, split_field_path(field)) is None:
        raise ConfigError(
            f"A operação {name} não tem o campo {safe_identifier(field)} no corpo.",
            hint="Corrija consumed_by[].field de flows.yml.",
        )

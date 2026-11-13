"""Leitor de YAML endurecido para o perfil do produto.

Por que não basta `yaml.safe_load`: ele aceita âncoras, aliases e chaves de mesclagem (`<<`),
que escondem o que de fato está configurado e permitem expansão exponencial ("billion laughs");
aceita chave duplicada (a última vence em silêncio, e um `deny_paths` repetido poderia sumir);
e aceita tags além do esquema básico (`!!binary`, `!!set`...). Aqui tudo isso vira `ConfigError`.

As mensagens trazem só linha e coluna, nunca o conteúdo: o arquivo pode ter um segredo
digitado no lugar errado.
"""

from typing import Final

import yaml
from yaml.constructor import SafeConstructor
from yaml.events import AliasEvent, CollectionStartEvent, ScalarEvent
from yaml.nodes import MappingNode, Node

from harness_dast.domain.errors import ConfigError

MAX_PROFILE_BYTES: Final = 256 * 1024
"""Tamanho máximo, em bytes, de um arquivo de perfil."""

_MAX_DEPTH = 40
_CORE_TAGS = frozenset(
    f"tag:yaml.org,2002:{name}" for name in ("str", "int", "float", "bool", "null", "seq", "map")
)
_MERGE_TAG = "tag:yaml.org,2002:merge"
_HINT = (
    "Use YAML simples: sem âncoras (&), aliases (*), chaves '<<', tags (!!) nem chaves repetidas."
)


class _Rejected(Exception):
    """Construção proibida; guarda só a posição e um texto fixo."""

    def __init__(self, reason: str, line: int, column: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.line = line
        self.column = column


class _StrictLoader(yaml.SafeLoader):
    """`SafeLoader` que recusa âncoras, aliases, mesclagem, tags não básicas e duplicatas."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._depth = 0

    def compose_node(self, parent: Node | None, index: int) -> Node | None:
        # Os stubs do PyYAML não tipam peek_event; ele devolve o próximo evento sem consumi-lo.
        event = self.peek_event()  # type: ignore[no-untyped-call]
        mark = event.start_mark
        if isinstance(event, AliasEvent):
            raise _Rejected("alias (*) não é permitido", mark.line + 1, mark.column + 1)
        if isinstance(event, ScalarEvent | CollectionStartEvent):
            if event.anchor is not None:
                raise _Rejected("âncora (&) não é permitida", mark.line + 1, mark.column + 1)
            if event.tag is not None and event.tag not in _CORE_TAGS:
                raise _Rejected("tag explícita não é permitida", mark.line + 1, mark.column + 1)
        self._depth += 1
        if self._depth > _MAX_DEPTH:
            raise _Rejected("aninhamento profundo demais", mark.line + 1, mark.column + 1)
        try:
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[object, object]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            mark = key_node.start_mark
            if key_node.tag == _MERGE_TAG:
                raise _Rejected(
                    "chave de mesclagem (<<) não é permitida", mark.line + 1, mark.column + 1
                )
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, str):
                raise _Rejected("chave que não é texto", mark.line + 1, mark.column + 1)
            if key in seen:
                raise _Rejected("chave repetida", mark.line + 1, mark.column + 1)
            seen.add(key)
        return SafeConstructor.construct_mapping(self, node, deep=deep)


def _syntax_error(error: Exception, document: str) -> ConfigError:
    mark = getattr(error, "problem_mark", None)
    where = f" (linha {mark.line + 1}, coluna {mark.column + 1})" if mark is not None else ""
    return ConfigError(
        f"O {document} não é um YAML válido{where}.",
        hint="Corrija a sintaxe nesse ponto; use um editor com validação de YAML.",
    )


def parse_profile_yaml(text: str) -> dict[str, object]:
    """Interpreta o texto do `target.yml` como mapa (veja `parse_yaml_document`)."""
    return parse_yaml_document(text, "target.yml")


def parse_yaml_document(text: str, document: str) -> dict[str, object]:
    """Interpreta o texto de um arquivo do produto como mapa, recusando YAML perigoso.

    Vale para `target.yml`, `data-rules.yml` e `flows.yml`.

    Args:
        text: Conteúdo do arquivo, já decodificado.
        document: Nome do arquivo, só para as mensagens de erro.

    Returns:
        O mapa da raiz do documento.

    Raises:
        ConfigError: YAML inválido, vazio, mais de um documento, raiz que não é mapa, ou
            construção proibida (âncora, alias, mesclagem, tag, chave repetida ou não
            textual, aninhamento excessivo). A mensagem traz linha e coluna, não o conteúdo.
    """
    try:
        loaded = yaml.load(text, Loader=_StrictLoader)  # noqa: S506 - Loader derivado de SafeLoader
    except _Rejected as rejected:
        raise ConfigError(
            f"O {document} usa uma construção proibida: {rejected.reason} "
            f"(linha {rejected.line}, coluna {rejected.column}).",
            hint=_HINT,
        ) from None
    except (yaml.YAMLError, RecursionError) as error:
        raise _syntax_error(error, document) from None
    if loaded is None:
        raise ConfigError(
            f"O {document} está vazio.",
            hint=f"Preencha-o a partir de products/_template/{document}.",
        )
    if not isinstance(loaded, dict):
        raise ConfigError(
            f"A raiz do {document} deve ser um mapa de campos (chave: valor).",
            hint=f"Veja products/_template/{document}.",
        )
    return loaded

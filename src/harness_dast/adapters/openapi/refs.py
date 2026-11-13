"""Resolução de `$ref` LOCAIS (`#/...`) e conferência de forma do documento.

O documento é não confiável: aqui nunca se abre URL nem arquivo. Toda referência que não
comece com `#/` é recusada com `ConfigError`. A busca anda por mapas e listas já carregados
na memória, com limite de saltos (uma referência pode apontar para outra referência).
"""

from collections.abc import Mapping
from urllib.parse import unquote

from harness_dast.domain.api_model import safe_identifier
from harness_dast.domain.errors import ConfigError

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_NODES = 500_000
MAX_DOCUMENT_DEPTH = 128
MAX_REF_HOPS = 16
_HINT_REF = "Use só referências locais ('#/components/...'); junte o documento em um arquivo."

type Raw = object


def escape_pointer(part: str) -> str:
    """Escapa um trecho para uso em ponteiro JSON (`~` e `/`)."""
    return part.replace("~", "~0").replace("/", "~1")


def check_document_shape(document: Raw) -> None:
    """Confere, sem recursão, que o documento não passa dos limites de tamanho e profundidade.

    Cada ocorrência conta, inclusive de estruturas compartilhadas por âncora/alias do YAML,
    o que barra a "bomba de aliases" (um documento pequeno que expande para bilhões de nós) e
    estruturas que apontam para si mesmas.

    Raises:
        ConfigError: Mais de 500 mil nós ou aninhamento acima de 128 níveis.
    """
    stack: list[tuple[Raw, int]] = [(document, 1)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_DOCUMENT_NODES:
            raise ConfigError(
                f"O OpenAPI tem mais de {MAX_DOCUMENT_NODES} nós (ou usa aliases YAML que se "
                "expandem demais).",
                hint="Reduza o documento ou remova aliases YAML repetidos.",
            )
        if depth > MAX_DOCUMENT_DEPTH:
            raise ConfigError(
                f"O OpenAPI tem aninhamento acima de {MAX_DOCUMENT_DEPTH} níveis.",
                hint="Simplifique a estrutura do documento.",
            )
        if isinstance(node, Mapping):
            stack.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, list):
            stack.extend((child, depth + 1) for child in node)


class RefResolver:
    """Resolve referências locais dentro de um documento já carregado."""

    def __init__(self, document: Mapping[str, Raw]) -> None:
        """Guarda o documento; ele nunca é modificado."""
        self._document = document

    def resolve(self, ref: Raw, where: str) -> tuple[str, Raw]:
        """Segue `ref` (e referências encadeadas) até um objeto que não seja `$ref`.

        Args:
            ref: Valor do campo `$ref`.
            where: Localização (ponteiro) do campo, para as mensagens.

        Returns:
            Par (referência final canônica, objeto apontado).

        Raises:
            ConfigError: Referência remota, de arquivo externo, mal formada, inexistente
                ou encadeada em excesso. A mensagem nunca repete o texto da referência.
        """
        current = ref
        for _ in range(MAX_REF_HOPS):
            target = self._follow(current, where)
            if isinstance(target, Mapping) and "$ref" in target:
                current = target["$ref"]
                continue
            return str(current), target
        raise ConfigError(
            f"{where}: cadeia de referências longa demais (mais de {MAX_REF_HOPS} saltos).",
            hint=_HINT_REF,
        )

    def _follow(self, ref: Raw, where: str) -> Raw:
        if not isinstance(ref, str):
            raise ConfigError(f"{where}: '$ref' deve ser um texto.", hint=_HINT_REF)
        if not ref.startswith("#/"):
            kind = "remota (URL)" if "://" in ref or ref.startswith("//") else "de arquivo externo"
            raise ConfigError(
                f"{where}: referência {kind} não é suportada; o harness não abre URLs nem "
                "outros arquivos por causa de um documento não confiável.",
                hint=_HINT_REF,
            )
        node: Raw = self._document
        for raw_part in ref[2:].split("/"):
            part = unquote(raw_part).replace("~1", "/").replace("~0", "~")
            node = self._step(node, part, where)
        return node

    @staticmethod
    def _step(node: Raw, part: str, where: str) -> Raw:
        if isinstance(node, Mapping):
            if part in node:
                return node[part]
            # Chaves como `200` ou `true` chegam do YAML como número ou booleano.
            for key, value in node.items():
                if not isinstance(key, str) and str(key).lower() == part:
                    return value
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            return node[int(part)]
        raise ConfigError(
            f"{where}: referência local inexistente (trecho {safe_identifier(part)}).",
            hint="Confira se o item existe em 'components' do documento.",
        )

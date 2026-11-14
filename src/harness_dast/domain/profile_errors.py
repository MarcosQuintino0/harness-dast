"""Tradução de erros de validação do pydantic para `ConfigError` em português.

Por que existe: o texto padrão do pydantic repete o valor recebido (`input_value=...`), o que
vazaria um segredo digitado no lugar errado. Aqui só entram o caminho do campo e textos
nossos. Este módulo é puro.
"""

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from harness_dast.domain.errors import ConfigError

_TYPE_MESSAGES = {
    "missing": "campo obrigatório ausente",
    "extra_forbidden": "campo desconhecido (confira a grafia)",
    "union_tag_invalid": "valor de 'type' desconhecido; use login_password ou api_key",
    "union_tag_not_found": "campo 'type' ausente",
    "model_type": "esperado um objeto (mapa) com campos",
    "dict_type": "esperado um objeto (mapa) com campos",
    "too_short": "lista vazia ou curta demais",
    "too_long": "lista ou texto longo demais",
    "literal_error": "valor não permitido neste campo",
    "date_from_datetime_inexact": "use apenas a data (AAAA-MM-DD)",
    "date_type": "esperada uma data (AAAA-MM-DD)",
    "date_parsing": "esperada uma data (AAAA-MM-DD)",
    "bool_type": "esperado verdadeiro ou falso (true/false)",
    "int_type": "esperado um número inteiro",
    "float_type": "esperado um número",
    "string_type": "esperado um texto",
    "list_type": "esperada uma lista",
}


def _describe(error: ErrorDetails) -> str:
    kind = error["type"]
    if kind == "value_error":
        # Só o texto das nossas validações, escritas para não repetir o valor recebido.
        return str(error.get("ctx", {}).get("error", "valor inválido"))
    if kind in {"greater_than", "greater_than_equal", "less_than_equal", "less_than"}:
        return "valor fora do intervalo permitido"
    return _TYPE_MESSAGES.get(kind, "valor inválido")


# Etiquetas do campo `type` da união de autenticação: o pydantic as insere no caminho do
# erro, mas não são campos do perfil.
_UNION_TAGS = frozenset({"login_password", "api_key"})


def _format_location(location: tuple[int | str, ...]) -> str:
    text = ""
    for index, part in enumerate(location):
        if index == 1 and location[0] == "auth" and part in _UNION_TAGS:
            continue
        text += f"[{part}]" if isinstance(part, int) else f".{part}"
    return text.lstrip(".") or "(perfil)"


def _drop_derived_errors(errors: list[ErrorDetails]) -> list[ErrorDetails]:
    # Quando um item de uma lista falha, o pydantic ainda acusa "lista curta demais" porque
    # contou zero itens válidos; é consequência do erro do item, não um problema à parte.
    def has_child(error: ErrorDetails) -> bool:
        size = len(error["loc"])
        return any(
            len(other["loc"]) > size and other["loc"][:size] == error["loc"] for other in errors
        )

    return [e for e in errors if not (e["type"] == "too_short" and has_child(e))]


_ALLOW_LOCAL_HINT = (
    "Host de laboratório (nome de contêiner como vampi, localhost ou IP): na regra de "
    "scope.allow, escreva allow_local: true (e scheme: http se o alvo não tem TLS). "
    "Ambiente real de teste: use o nome DNS completo, com ponto."
)


def _hint_for(details: list[ErrorDetails], hint: str) -> str:
    # O erro de allow_local é o que mais confunde quem começa: a dica diz a correção exata.
    if any("allow_local: true nesta regra" in _describe(e) for e in details):
        return f"{hint} {_ALLOW_LOCAL_HINT}"
    return hint


def describe_problems(error: ValidationError) -> tuple[tuple[tuple[int | str, ...], str], ...]:
    """Lista os problemas do `ValidationError` como pares (caminho, explicação), ordenados.

    A explicação nunca contém o valor recebido, só textos fixos ou das nossas validações.

    Args:
        error: Erro de validação do pydantic.

    Returns:
        Pares únicos de (caminho do campo, explicação em português).
    """
    details = _drop_derived_errors(error.errors())
    pairs = {(e["loc"], _describe(e)) for e in details}
    return tuple(sorted(pairs, key=lambda pair: (_format_location(pair[0]), pair[1])))


def to_config_error(
    error: ValidationError, *, hint: str, subject: str = "Perfil", feminine: bool = False
) -> ConfigError:
    """Converte o `ValidationError` do pydantic em `ConfigError` em português.

    Cada problema vira uma linha `- caminho.do.campo: explicação`. Garantia de segurança: a
    mensagem nunca contém os valores recebidos, só o caminho dos campos e textos fixos (ou
    as mensagens das nossas validações, escritas sem eco do valor).

    Args:
        error: Erro de validação do pydantic.
        hint: Orientação do que fazer, repetida na dica do erro.
        subject: Documento que falhou ("Perfil", "Carta"), no início da mensagem.
        feminine: Se o documento é feminino em português ("Carta inválida", não "inválido").

    Returns:
        O erro de configuração a ser levantado pelo chamador.
    """
    # Nunca usa `input`, `str(error)` nem `msg` do pydantic: eles podem trazer o valor
    # recebido. Só o caminho do campo e um texto nosso entram na mensagem.
    details = _drop_derived_errors(error.errors())
    problems = sorted({f"{_format_location(e['loc'])}: {_describe(e)}" for e in details})
    lines = "\n".join(f"- {problem}" for problem in problems)
    adjective = "inválida" if feminine else "inválido"
    return ConfigError(
        f"{subject} {adjective} ({len(problems)} problema(s)):\n{lines}",
        hint=_hint_for(details, hint),
    )


def format_location(location: tuple[int | str, ...]) -> str:
    """Caminho do campo em texto (`scope.allow[0].host`), como nas mensagens de erro."""
    return _format_location(location)

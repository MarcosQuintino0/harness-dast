"""Conferência da carta estruturada e geração dos blocos do `target.yml` (ADR 0036).

`review_letter` é determinística e sem relógio: a mesma carta dá o mesmo texto, qualquer que
seja a ordem das chaves no arquivo. Falha fechada em duas etapas: (1) os portões (ambiente de
teste, dados sintéticos, autorização vigente, dono do produto): um "não" ou "desconhecido"
recusa tudo e nenhum outro campo é lido; (2) cada campo obrigatório, com origem e valor. Só
sem nenhuma pendência o perfil é montado, e ele ainda passa por `ProductProfile.from_data`:
o que o perfil recusa, a carta recusa. Este módulo é puro.
"""

from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.letter import Gates, Letter
from harness_dast.domain.letter_collect import (
    GATE_DENIED,
    INVALID_VALUE,
    PRODUCT_MISMATCH,
    PROFILE_REJECTED,
    Collector,
    LetterIssue,
)
from harness_dast.domain.letter_sections import (
    Block,
    read_auth,
    read_authorization,
    read_environment,
    read_example_data,
    read_limits,
    read_scope,
    read_strength,
)
from harness_dast.domain.letter_yaml import render_yaml
from harness_dast.domain.profile import ProductProfile

GENERATED_BLOCKS: Final = ("environment", "openapi", "scope", "limits", "auth", "scan.strength")
"""Blocos do `target.yml` que a CLI escreve a partir da carta (`scan.strength` só se informada)."""

_GATE_DENIED_TEXT = (
    "Respondido 'não'. Sem esta condição o teste não pode ser feito: nada foi gerado. "
    "Fale com o dono do produto; o agente não muda a resposta."
)
_HEADER = (
    "# Gerado por: hdast init <produto> --from-letter <carta.yml> (ADR 0036).\n"
    "# Blocos gerados da carta (o agente não os escreve nem os altera): "
    "environment, openapi, scope, limits, auth, scan.strength.\n"
    "# Para mudar algum deles, a pessoa muda a carta e o perfil é gerado de novo.\n"
)


class LetterReview(BaseModel):
    """Resultado da conferência da carta.

    Attributes:
        issues: Pendências, campo a campo; vazio quando a carta está pronta.
        profile_text: O `target.yml` gerado, só quando não há pendência.
        blocks: Blocos do perfil que o texto gerado contém, na ordem em que aparecem.
        example_data: Dados de exemplo da carta, como informação para o agente.
    """

    model_config = ConfigDict(frozen=True)

    issues: tuple[LetterIssue, ...]
    profile_text: str | None = None
    blocks: tuple[str, ...] = ()
    example_data: tuple[dict[str, JsonValue], ...] = ()

    @property
    def ready(self) -> bool:
        """Se a carta está pronta para gerar o perfil."""
        return not self.issues and self.profile_text is not None


def _check_gates(c: Collector, gates: Gates) -> None:
    answers = (
        ("test_environment", gates.test_environment),
        ("synthetic_data", gates.synthetic_data),
        ("authorization_in_force", gates.authorization_in_force),
    )
    for name, answer in answers:
        field = f"gates.{name}"
        value = c.take(field, answer)
        if value is False:
            c.add(field, GATE_DENIED, _GATE_DENIED_TEXT)
        elif value is not None and value is not True:
            c.add(field, INVALID_VALUE, "Responda true (sim) ou false (não).")
    c.take_text("gates.product_owner", gates.product_owner)


def _profile_data(
    letter: Letter, c: Collector
) -> tuple[dict[str, object], tuple[dict[str, JsonValue], ...]] | None:
    environment = read_environment(c, letter.environment)
    scope = read_scope(c, letter.scope)
    authorization = read_authorization(c, letter.authorization)
    limits = read_limits(c, letter.limits)
    auth = read_auth(c, letter.auth)
    strength = read_strength(c, letter.attack.strength)
    examples = read_example_data(c, letter.example_data)
    if (
        c.issues
        or environment is None
        or scope is None
        or authorization is None
        or limits is None
        or auth is None
    ):
        return None
    scope_block: Block = {
        "allow": scope["allow"],
        "deny_paths": scope["deny_paths"],
        "authorization": authorization[0],
        "path_mode": scope["path_mode"],
        "windows": authorization[1],
    }
    data: dict[str, object] = {
        "schema_version": 1,
        "product": letter.product,
        "environment": environment[0],
        "openapi": environment[1],
        "scope": scope_block,
        "limits": limits,
        "auth": auth,
    }
    if strength is not None:
        data["scan"] = {"strength": strength}
    return data, examples


def review_letter(letter: Letter, expected_product: str) -> LetterReview:
    """Confere a carta e, se estiver completa, gera o texto do `target.yml`.

    Args:
        letter: Carta já lida e com a forma validada (`Letter.from_data`).
        expected_product: Produto pedido em `hdast init`; a carta precisa ser dele.

    Returns:
        A conferência: pendências campo a campo ou o texto gerado.
    """
    c = Collector()
    if letter.product != expected_product:
        c.add(
            "product",
            PRODUCT_MISMATCH,
            "A carta é de outro produto; use a carta deste produto ou corrija o nome.",
        )
    _check_gates(c, letter.gates)
    if c.issues:
        return LetterReview(issues=tuple(c.issues))
    built = _profile_data(letter, c)
    if built is None:
        return LetterReview(issues=tuple(c.issues))
    data, examples = built
    try:
        ProductProfile.from_data(data)
    except ConfigError as error:
        c.add("(perfil gerado)", PROFILE_REJECTED, f"{error.message} {error.hint or ''}".strip())
        return LetterReview(issues=tuple(c.issues))
    blocks = tuple(name for name in GENERATED_BLOCKS if name.split(".")[0] in data)
    return LetterReview(
        issues=(),
        profile_text=_HEADER + render_yaml(data),
        blocks=blocks,
        example_data=examples,
    )

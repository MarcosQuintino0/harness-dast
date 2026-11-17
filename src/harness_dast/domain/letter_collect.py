"""Coletor de respostas da carta: lê cada `Answer`, confere e acumula pendências (ADR 0036).

Garantia de falha fechada: uma resposta só vira valor se tem origem `carta` ou `pessoa`, tem
valor, e o valor não é de modelo. Todo o resto vira uma pendência com o campo e o que fazer;
nada é preenchido por padrão. As mensagens nunca repetem o valor recebido. Este módulo é puro.
"""

from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict, ValidationError

from harness_dast.domain.letter import Answer
from harness_dast.domain.placeholders import is_placeholder_text
from harness_dast.domain.profile_errors import describe_problems, format_location

MISSING: Final = "MISSING"
UNKNOWN: Final = "UNKNOWN"
INVALID_VALUE: Final = "INVALID_VALUE"
PLACEHOLDER: Final = "PLACEHOLDER"
GATE_DENIED: Final = "GATE_DENIED"
WIDE_NEEDS_LETTER: Final = "WIDE_NEEDS_LETTER"
SHARED_ROLES_NEEDS_LETTER: Final = "SHARED_ROLES_NEEDS_LETTER"
AUTHZ_WRITES_NEEDS_LETTER: Final = "AUTHZ_WRITES_NEEDS_LETTER"
NEGATIVE_WRITES_NEEDS_LETTER: Final = "NEGATIVE_WRITES_NEEDS_LETTER"
UPLOAD_SCAN_NEEDS_LETTER: Final = "UPLOAD_SCAN_NEEDS_LETTER"
ATTACK_FLAG_NEEDS_LETTER: Final = "ATTACK_FLAG_NEEDS_LETTER"
PRODUCT_MISMATCH: Final = "PRODUCT_MISMATCH"
PROFILE_REJECTED: Final = "PROFILE_REJECTED"

_WHO = "A resposta vem da pessoa (carta ou entrevista), não do agente."
_MISSING_TEXT = f"Sem resposta. {_WHO} Pergunte e preencha {{value, source}}."
_UNKNOWN_TEXT = (
    "Respondido como desconhecido, mas o campo é obrigatório. A pessoa precisa obter a "
    "informação com o dono do produto; o agente não preenche por conta própria."
)
_PLACEHOLDER_TEXT = "Valor de modelo (exemplo) não vale como resposta; informe o valor real."


class LetterIssue(BaseModel):
    """Pendência da carta, campo a campo.

    Attributes:
        field: Caminho do campo no carta.yml (`scope.allow[0].host`).
        code: Identificador estável (`MISSING`, `UNKNOWN`, `INVALID_VALUE`, `PLACEHOLDER`,
            `GATE_DENIED`, `WIDE_NEEDS_LETTER`, `AUTHZ_WRITES_NEEDS_LETTER`,
            `NEGATIVE_WRITES_NEEDS_LETTER`, `UPLOAD_SCAN_NEEDS_LETTER`,
            `ATTACK_FLAG_NEEDS_LETTER`, `PRODUCT_MISMATCH`,
            `PROFILE_REJECTED`,
            `AUTHORIZATION_EXPIRED`; nos avisos: `ALLOW_ROOT_WILDCARD`, `DELETE_AUTHORIZED`,
            `DENY_PATHS_EMPTY`, `VALIDITY_OVER_ONE_YEAR`, `AUTHZ_WRITES_AUTHORIZED`,
            `NEGATIVE_WRITES_AUTHORIZED`, `UPLOAD_SCAN_AUTHORIZED`, `ATTACK_FLAG_AUTHORIZED`).
        message: O que está pendente e o que fazer.
    """

    model_config = ConfigDict(frozen=True)

    field: str
    code: str
    message: str


def has_placeholder(value: object) -> bool:
    """Diz se algum texto dentro de `value` (listas e mapas incluídos) é valor-modelo."""
    if isinstance(value, str):
        return is_placeholder_text(value)
    if isinstance(value, list | tuple):
        return any(has_placeholder(item) for item in value)
    if isinstance(value, Mapping):
        return any(has_placeholder(item) for item in value.values())
    return False


def join_path(prefix: str, location: tuple[int | str, ...]) -> str:
    """Junta o prefixo do campo ao caminho interno de um erro de validação."""
    if not location:
        return prefix
    inner = format_location(location)
    return prefix + (inner if inner.startswith("[") else "." + inner)


class Collector:
    """Acumula as pendências enquanto os campos são lidos."""

    def __init__(self) -> None:
        """Cria um coletor sem pendências."""
        self.issues: list[LetterIssue] = []

    def add(self, field: str, code: str, message: str) -> None:
        """Registra uma pendência."""
        self.issues.append(LetterIssue(field=field, code=code, message=message))

    def take(
        self,
        field: str,
        answer: Answer | None,
        *,
        required: bool = True,
        scan_placeholders: bool = True,
    ) -> object | None:
        """Devolve o valor de uma resposta, ou `None` (com pendência se obrigatória).

        Args:
            field: Caminho do campo, para a pendência.
            answer: Resposta lida da carta, ou `None` se ausente.
            required: Se `False`, ausente ou desconhecido não gera pendência (vale o padrão).
            scan_placeholders: Se `True`, recusa valor-modelo (`SEC-0000`, `exemplo.com.br`...).
        """
        if answer is None:
            self._absent(field, required, MISSING, _MISSING_TEXT)
            return None
        if answer.source == "desconhecido":
            self._absent(field, required, UNKNOWN, _UNKNOWN_TEXT)
            return None
        if answer.value is None:
            self._absent(field, required, MISSING, _MISSING_TEXT)
            return None
        if scan_placeholders and has_placeholder(answer.value):
            self.add(field, PLACEHOLDER, _PLACEHOLDER_TEXT)
            return None
        return answer.value

    def _absent(self, field: str, required: bool, code: str, text: str) -> None:
        if required:
            self.add(field, code, text)

    def take_text(self, field: str, answer: Answer | None, *, required: bool = True) -> str | None:
        """Como `take`, mas exige texto não vazio."""
        value = self.take(field, answer, required=required)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            self.add(field, INVALID_VALUE, "Esperado um texto não vazio.")
            return None
        return value.strip()

    def take_list(
        self,
        field: str,
        answer: Answer | None,
        *,
        allow_empty: bool = False,
        scan_placeholders: bool = True,
    ) -> list[object] | None:
        """Como `take`, mas exige uma lista (vazia só se `allow_empty`)."""
        value = self.take(field, answer, scan_placeholders=scan_placeholders)
        if value is None:
            return None
        if not isinstance(value, list) or (not value and not allow_empty):
            self.add(field, INVALID_VALUE, "Esperada uma lista com ao menos um item.")
            return None
        return value

    def check_model[ModelT: BaseModel](
        self,
        prefix: str,
        model: type[ModelT],
        present: Mapping[str, object],
        filler: Mapping[str, object],
    ) -> ModelT | None:
        """Valida `present` com `model`, reportando só os campos que a pessoa respondeu.

        Campos de `filler` que a pessoa não respondeu são preenchidos só para o modelo aceitar
        a construção; a ausência deles já foi reportada por `take`. Os demais erros
        (inclusive campo faltando, quando `filler` está vazio) são reportados. Devolve `None`
        se algo falhou.
        """
        try:
            return model.model_validate({**filler, **present})
        except ValidationError as error:
            reported = False
            for location, text in describe_problems(error):
                if location and location[0] in filler and location[0] not in present:
                    continue
                self.add(join_path(prefix, location), INVALID_VALUE, text)
                reported = True
            if not reported:
                self.add(prefix, INVALID_VALUE, "Valor inválido.")
            return None

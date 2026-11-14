"""Caso de uso: gerar a pasta do produto a partir da carta estruturada (ADR 0036).

A carta (`carta.yml`) leva as respostas da pessoa; este caso de uso só as confere e, se
estiverem completas, cria o produto com o `target.yml` gerado. Falha fechada: com qualquer
pendência nada é criado. O agente não escreve os blocos de proteção do perfil.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, JsonValue

from harness_dast.application.ports import LetterReader, ProductScaffolder, ScaffoldedProduct
from harness_dast.domain.errors import LetterRejected
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_collect import LetterIssue
from harness_dast.domain.letter_review import LetterReview, review_letter

_WHO_HINT = (
    "Cada pendência é uma pergunta para a pessoa (o dono do produto ou a carta assinada); o "
    "agente não preenche resposta por conta própria. Complete o carta.yml com as respostas "
    "e rode de novo (hdast init <produto> --from-letter <carta.yml> --check confere sem criar)."
)


class LetterOutcome(BaseModel):
    """Resultado de `hdast init --from-letter`.

    Attributes:
        product: Produto pedido.
        ready: Se a carta está completa e válida.
        issues: Pendências campo a campo (vazio quando `ready`).
        generated_blocks: Blocos do `target.yml` que a CLI gerou (ou geraria, em `--check`).
        example_data: Dados de exemplo da carta, informação para o agente.
        created: A pasta criada; `None` em `--check` ou quando há pendência.
    """

    model_config = ConfigDict(frozen=True)

    product: str
    ready: bool
    issues: tuple[LetterIssue, ...]
    generated_blocks: tuple[str, ...]
    example_data: tuple[dict[str, JsonValue], ...]
    created: ScaffoldedProduct | None = None


class InitFromLetter:
    """Confere a carta e cria o produto com o perfil gerado."""

    def __init__(self, reader: LetterReader, scaffolder: ProductScaffolder) -> None:
        """Cria o caso de uso.

        Args:
            reader: Leitor da carta.
            scaffolder: Criador da pasta do produto.
        """
        self._reader = reader
        self._scaffolder = scaffolder

    def review(self, product: str, letter_path: Path) -> LetterReview:
        """Lê e confere a carta, sem criar nada.

        Raises:
            ConfigError: Arquivo ilegível, YAML inválido ou carta com forma errada (campo
                desconhecido, resposta fora do formato `{value, source}`).
        """
        letter = Letter.from_data(self._reader.read(letter_path))
        return review_letter(letter, product)

    def check(self, product: str, letter_path: Path) -> LetterOutcome:
        """Só confere a carta (`--check`): não cria pasta nem arquivo."""
        return _outcome(product, self.review(product, letter_path), None)

    def execute(
        self, product: str, letter_path: Path, *, with_cleanup: bool = False
    ) -> LetterOutcome:
        """Confere a carta e, sem pendências, cria o produto com o `target.yml` gerado.

        Com pendências, nada é criado e o resultado (`ready=False`) as lista campo a campo.

        Raises:
            ConfigError: Como em `review`, ou o produto já existe (nada é sobrescrito).
        """
        review = self.review(product, letter_path)
        if not review.ready:
            return _outcome(product, review, None)
        created = self._scaffolder.scaffold(
            product, with_cleanup=with_cleanup, target_text=review.profile_text
        )
        return _outcome(product, review, created)


def _outcome(
    product: str, review: LetterReview, created: ScaffoldedProduct | None
) -> LetterOutcome:
    return LetterOutcome(
        product=product,
        ready=review.ready,
        issues=review.issues,
        generated_blocks=review.blocks,
        example_data=review.example_data,
        created=created,
    )


def rejection(outcome: LetterOutcome) -> LetterRejected:
    """Monta o erro de uma carta com pendências, listando cada campo."""
    lines = "\n".join(f"- {i.field} [{i.code}]: {i.message}" for i in outcome.issues)
    return LetterRejected(
        f"A carta tem {len(outcome.issues)} pendência(s); nada foi gerado:\n{lines}",
        hint=_WHO_HINT,
    )

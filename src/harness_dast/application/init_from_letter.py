"""Caso de uso: gerar a pasta do produto a partir da carta estruturada (ADR 0036).

A carta (`carta.yml`) leva as respostas da pessoa; este caso de uso só as confere e, se
estiverem completas, cria o produto com o `target.yml` gerado. Falha fechada: com qualquer
pendência nada é criado. O agente não escreve os blocos de proteção do perfil.
"""

from datetime import UTC
from pathlib import Path

from pydantic import BaseModel, ConfigDict, JsonValue

from harness_dast.application.common_ports import Clock
from harness_dast.application.init_ports import (
    LetterReader,
    ProductScaffolder,
    ScaffoldedProduct,
    SpecPathReader,
)
from harness_dast.domain.errors import ConfigError, LetterRejected
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_collect import LetterIssue
from harness_dast.domain.letter_review import LetterReview, review_letter
from harness_dast.domain.request_defaults import DEFAULT_TIMEZONE
from harness_dast.domain.request_letter import RequestInputs, letter_kind, requested_openapi

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
        warnings: Avisos que não recusam a carta (permissão em `/**`, `DELETE`, nenhum caminho
            proibido, validade acima de um ano); o agente os mostra à pessoa na entrevista.
        generated_blocks: Blocos do `target.yml` que a CLI gerou (ou geraria, em `--check`).
        example_data: Dados de exemplo da carta, informação para o agente.
        created: A pasta criada; `None` em `--check` ou quando há pendência.
    """

    model_config = ConfigDict(frozen=True)

    product: str
    ready: bool
    issues: tuple[LetterIssue, ...]
    warnings: tuple[LetterIssue, ...]
    generated_blocks: tuple[str, ...]
    example_data: tuple[dict[str, JsonValue], ...]
    created: ScaffoldedProduct | None = None


class InitFromLetter:
    """Confere a carta e cria o produto com o perfil gerado."""

    def __init__(
        self,
        reader: LetterReader,
        scaffolder: ProductScaffolder,
        clock: Clock,
        spec_paths: SpecPathReader | None = None,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> None:
        """Cria o caso de uso.

        Args:
            reader: Leitor da carta.
            scaffolder: Criador da pasta do produto.
            clock: Relógio injetado (a validade da autorização é conferida contra hoje).
            spec_paths: Leitor dos caminhos do OpenAPI, só para a carta `kind: request`
                (ADR 0120); sem ele, o pedido mínimo fica pendente.
            timezone: Nome IANA do fuso da janela padrão do pedido mínimo, informado pela CLI.
        """
        self._reader = reader
        self._scaffolder = scaffolder
        self._clock = clock
        self._spec_paths = spec_paths
        self._timezone = timezone

    def review(self, product: str, letter_path: Path) -> LetterReview:
        """Lê e confere a carta, sem criar nada.

        Raises:
            ConfigError: Arquivo ilegível, YAML inválido ou carta com forma errada (campo
                desconhecido, resposta fora do formato `{value, source}`).
        """
        letter = Letter.from_data(self._reader.read(letter_path))
        request = (
            self._request_inputs(letter, letter_path) if letter_kind(letter) == "request" else None
        )
        return review_letter(letter, product, self._clock.now().astimezone(UTC).date(), request)

    def _request_inputs(self, letter: Letter, letter_path: Path) -> RequestInputs:
        """Lê os caminhos do OpenAPI que o pedido mínimo usa; falha vira pendência da carta."""
        relative = requested_openapi(letter)
        if relative is None or self._spec_paths is None:
            return RequestInputs(
                timezone=self._timezone,
                api_error="Informe environment.openapi: o OpenAPI, ao lado da carta, de onde a "
                "CLI tira o escopo do pedido mínimo.",
            )
        try:
            paths = self._spec_paths.read_paths(letter_path.parent, relative)
        except ConfigError as error:
            return RequestInputs(
                timezone=self._timezone, api_error=f"{error.message} {error.hint or ''}".strip()
            )
        return RequestInputs(api_paths=paths, timezone=self._timezone)

    def check(self, product: str, letter_path: Path) -> LetterOutcome:
        """Só confere a carta (`--check`): não cria pasta nem arquivo."""
        return _outcome(product, self.review(product, letter_path), None)

    def execute(
        self, product: str, letter_path: Path, *, with_cleanup: bool = False
    ) -> LetterOutcome:
        """Confere a carta e, sem pendências, cria o produto com o `target.yml` gerado.

        Com pendências, nada é criado e o resultado (`ready=False`) as lista campo a campo.

        Raises:
            ConfigError: Como em `review`, ou a pasta do produto já tem arquivo do perfil
            (nada é sobrescrito; uma pasta só com arquivos do agente é aceita).
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
        warnings=review.warnings,
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

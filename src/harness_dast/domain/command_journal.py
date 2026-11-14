"""Diário de comandos: o registro de cada invocação do `hdast` (ADR 0033).

O diário alimenta a aba "Terminal" do painel da execução. Cada linha é uma `JournalEntry`:
quando o comando começou e terminou, qual foi (subcomando e flags), de que produto e execução,
o código de saída, o estado numa palavra da lista fechada e um resumo curto da resposta.

Regras de segurança (todas aqui, testadas, nunca no agente):

- só os NOMES das flags e valores não sensíveis; texto livre passa pela redação do projeto
  (`redact_text`) e é cortado; flag de nome sensível guarda só `***`;
- `secret set` e `secret delete` guardam só o subcomando e o NOME do segredo;
- o resumo tem só contagens, booleanos e identificadores curtos tirados do envelope da CLI:
  nunca mensagem nem corpo do alvo.

O diário é por produto. `slice_for_run` recorta o trecho que pertence a um teste: do fim do
teste anterior até o fim deste. Este módulo é puro: horas e máscara entram por argumento.
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Final, Literal, Self

from pydantic import ValidationError, field_validator, model_validator

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.redaction import (
    MASK,
    Masker,
    is_sensitive_name,
    redact_text,
    strip_control,
)
from harness_dast.domain.run import SLUG_PATTERN, RunId

JOURNAL_SCHEMA_VERSION: Final = 1
NO_PRODUCT_STEM: Final = "_sem-produto"
"""Nome (sem extensão) do arquivo que guarda os comandos que não têm produto."""

CommandState = Literal["ok", "parcial", "erro"]
"""Lista fechada do estado de um comando (`docs/design/execution-panel/system/formats.html`)."""

VALUE_CAP: Final = 120
SUMMARY_MAX_ITEMS: Final = 16
_SUMMARY_KEY: Final = re.compile(r"[A-Za-z0-9_.]{1,48}")
_SUMMARY_TEXT: Final = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
_SLUG: Final = re.compile(SLUG_PATTERN)
_SECRET_COMMANDS: Final = frozenset({"secret set", "secret delete"})
_OK_EXIT_CODES: Final = frozenset({0, 1})
"""0 é sucesso; 1 é "varredura terminou e há achados", que também é terminar como esperado."""

type SummaryValue = int | float | bool | str


class JournalFlag(ApiModel):
    """Uma flag usada no comando.

    Attributes:
        name: Nome da flag, como `--seed`.
        value: Valor não sensível (redigido e cortado), ou `None` para flag sem valor.
    """

    name: str
    value: str | None = None


class JournalEntry(ApiModel):
    """Um comando do `hdast`, como registrado no diário.

    Attributes:
        schema_version: Versão do formato da linha (1).
        started_at: Início, com fuso.
        finished_at: Fim, com fuso.
        command: Subcomando por extenso (`probe`, `stack up`, `secret set`).
        product: Slug do produto, ou `None` quando o comando não tem produto.
        run_id: Execução a que a resposta se refere, ou `None`.
        flags: Flags usadas, na ordem em que o comando as declara.
        args: Argumentos posicionais além do produto (redigidos e cortados).
        exit_code: Código de saída do processo.
        state: `ok`, `parcial` ou `erro`.
        error_code: Código estável do erro (`CONFIG_ERROR`...), ou `None`.
        summary: Resumo curto da resposta: contagens, booleanos e identificadores.
    """

    schema_version: Literal[1] = JOURNAL_SCHEMA_VERSION
    started_at: datetime
    finished_at: datetime
    command: str
    product: str | None = None
    run_id: str | None = None
    flags: tuple[JournalFlag, ...] = ()
    args: tuple[str, ...] = ()
    exit_code: int
    state: CommandState
    error_code: str | None = None
    summary: Mapping[str, SummaryValue] = {}

    @field_validator("started_at", "finished_at")
    @classmethod
    def validate_aware(cls, value: datetime) -> datetime:
        """Exige data e hora com fuso."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("data e hora sem fuso")
        return value

    @field_validator("product")
    @classmethod
    def validate_product(cls, value: str | None) -> str | None:
        """O produto vira nome de arquivo: só slug."""
        if value is not None and not _SLUG.fullmatch(value):
            raise ValueError("produto fora do formato de slug")
        return value

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str | None) -> str | None:
        """Exige o formato de `RunId`."""
        if value is not None:
            RunId(value=value)
        return value

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """O fim não pode ser anterior ao início."""
        if self.finished_at < self.started_at:
            raise ValueError("finished_at anterior a started_at")
        return self


class JournalLoad(ApiModel):
    """Resultado da leitura tolerante de um arquivo de diário.

    Attributes:
        entries: Linhas válidas, na ordem do arquivo.
        skipped_lines: Quantas linhas não vazias foram puladas por estarem corrompidas ou numa
            versão de formato desconhecida.
    """

    entries: tuple[JournalEntry, ...]
    skipped_lines: int


def journal_file_stem(product: str | None) -> str:
    """Nome (sem extensão) do arquivo do diário de um produto.

    Args:
        product: Slug do produto, ou `None`.

    Returns:
        O slug, ou `_sem-produto` quando `None` ou fora do formato (nunca vira caminho).
    """
    if product is not None and _SLUG.fullmatch(product):
        return product
    return NO_PRODUCT_STEM


def _clean(value: str, mask: Masker) -> str:
    text = redact_text(strip_control(value, keep_newlines=False), mask)
    return text if len(text) <= VALUE_CAP else text[: VALUE_CAP - 1] + "…"


def build_flags(raw: Sequence[tuple[str, str | None]], mask: Masker) -> tuple[JournalFlag, ...]:
    """Monta as flags do diário a partir de pares (nome, valor).

    Flag de nome sensível guarda `***` no lugar do valor; os demais valores são redigidos e
    cortados.
    """
    flags: list[JournalFlag] = []
    for name, value in raw:
        if value is None:
            flags.append(JournalFlag(name=name))
        elif is_sensitive_name(name):
            flags.append(JournalFlag(name=name, value=MASK))
        else:
            flags.append(JournalFlag(name=name, value=_clean(value, mask)))
    return tuple(flags)


def classify_state(*, exit_code: int, has_data: bool) -> CommandState:
    """Estado do comando numa palavra.

    Args:
        exit_code: Código de saída do processo.
        has_data: Se a resposta trouxe `data` junto de um erro (resultado parcial).

    Returns:
        `ok` quando terminou como esperado (saída 0, ou 1 com achados); `parcial` quando
        terminou com erro mas devolveu resultado; `erro` quando não terminou.
    """
    if exit_code in _OK_EXIT_CODES:
        return "ok"
    return "parcial" if has_data else "erro"


def _summary_scalar(value: object, mask: Masker) -> SummaryValue | None:
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str) and _SUMMARY_TEXT.fullmatch(value) and mask(value) == value:
        return value
    return None


def _summary_items(
    prefix: str, data: Mapping[str, object], depth: int
) -> Iterable[tuple[str, object]]:
    for key, value in data.items():
        name = f"{prefix}{key}"
        if not _SUMMARY_KEY.fullmatch(name) or is_sensitive_name(name):
            continue
        if isinstance(value, Mapping) and depth == 0:
            yield from _summary_items(f"{name}.", value, depth + 1)
        elif isinstance(value, list | tuple):
            yield f"{name}_count", len(value)
        else:
            yield name, value


def summarize_data(data: Mapping[str, object] | None, mask: Masker) -> dict[str, SummaryValue]:
    """Resumo curto de `data` do envelope: contagens, booleanos e identificadores.

    Números e booleanos passam; lista vira o seu tamanho (`<chave>_count`); texto só passa se
    tiver forma de identificador curto (letras, dígitos e `_.:-`, até 64 caracteres) e não
    contiver segredo registrado; um nível de objeto é achatado (`summary.successes`). Qualquer
    outra coisa, e toda chave de nome sensível, é descartada: o resumo nunca leva mensagem
    nem corpo do alvo. No máximo `SUMMARY_MAX_ITEMS` itens.
    """
    if not data:
        return {}
    summary: dict[str, SummaryValue] = {}
    for name, raw in _summary_items("", data, 0):
        value = _summary_scalar(raw, mask)
        if value is not None and len(summary) < SUMMARY_MAX_ITEMS:
            summary[name] = value
    return summary


def build_journal_entry(
    *,
    started_at: datetime,
    finished_at: datetime,
    command: str,
    product: str | None,
    run_id: str | None,
    flags: Sequence[tuple[str, str | None]],
    args: Sequence[str],
    exit_code: int,
    error_code: str | None,
    data: Mapping[str, object] | None,
    mask: Masker,
) -> JournalEntry:
    """Monta a linha do diário aplicando as regras de segurança do módulo.

    `secret set` e `secret delete` guardam só o subcomando e o NOME (primeiro argumento): sem
    flags, sem resumo. Um `run_id` fora do formato é descartado em vez de derrubar o registro.
    """
    is_secret = command in _SECRET_COMMANDS
    safe_run_id: str | None = None
    if run_id is not None:
        try:
            safe_run_id = RunId(value=run_id).value
        except ValidationError:
            safe_run_id = None
    return JournalEntry(
        started_at=started_at,
        finished_at=max(finished_at, started_at),
        command=command,
        product=product if product is not None and _SLUG.fullmatch(product) else None,
        run_id=safe_run_id,
        flags=() if is_secret else build_flags(flags, mask),
        args=tuple(_clean(item, mask) for item in (args[:1] if is_secret else args)),
        exit_code=exit_code,
        state=classify_state(exit_code=exit_code, has_data=data is not None),
        error_code=error_code,
        summary={} if is_secret else summarize_data(data, mask),
    )


def parse_journal_lines(lines: Iterable[str]) -> JournalLoad:
    """Leitura tolerante: linha corrompida ou de versão desconhecida é pulada e contada.

    Linhas em branco são ignoradas sem contar.
    """
    entries: list[JournalEntry] = []
    skipped = 0
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            entries.append(JournalEntry.model_validate(json.loads(text)))
        except (ValueError, ValidationError):  # JSON inválido, campo errado ou versão nova
            skipped += 1
    return JournalLoad(entries=tuple(entries), skipped_lines=skipped)


def slice_for_run(entries: Sequence[JournalEntry], run_id: str) -> tuple[JournalEntry, ...]:
    """Recorta o trecho do diário que pertence ao teste `run_id`.

    O trecho vai do fim do teste anterior até o fim deste. O "fim" de um teste é o último
    comando com o `run_id` dele que aparece antes do primeiro comando de uma execução mais nova
    (assim, um `report` refeito depois, sobre um teste antigo, não engole o teste seguinte).
    Comandos sem `run_id` (`init`, `profile validate`, `doctor`, `stack up`) que ficam nesse
    intervalo pertencem a este teste; comando de outra execução dentro do intervalo fica de fora.

    Args:
        entries: Linhas do diário do produto, em qualquer ordem (são ordenadas pelo início).
        run_id: Execução que a aba mostra.

    Returns:
        O trecho, em ordem cronológica; vazio se o diário não tem comando dessa execução.
    """
    ordered = sorted(entries, key=lambda item: item.started_at)
    own = [i for i, item in enumerate(ordered) if item.run_id == run_id]
    if not own:
        return ()
    first = own[0]
    newer = [
        i for i, item in enumerate(ordered) if item.run_id is not None and item.run_id > run_id
    ]
    limit = min((i for i in newer if i > first), default=len(ordered))
    upper = max((i for i in own if i < limit), default=own[-1])
    older = [
        i
        for i, item in enumerate(ordered)
        if i < first and item.run_id is not None and item.run_id < run_id
    ]
    lower = max(older, default=-1)
    return tuple(item for item in ordered[lower + 1 : upper + 1] if item.run_id in (None, run_id))

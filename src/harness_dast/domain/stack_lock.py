"""Trava exclusiva por pilha (ADR 0035): quem a ocupa, se está órfã e o que dizer à pessoa.

Duas execuções na mesma pilha (ZAP e proxy) se corrompem: a sessão do ZAP, a regra de token e o
histórico são globais. A trava é um arquivo com o dono (`LockHolder`). Este módulo é puro: o
instante e o "processo vivo?" entram por argumento; ele só decide e descreve.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

LOCK_SCHEMA_VERSION = 1
_MINUTE = 60
_HOUR = 3600


class LockHolder(BaseModel):
    """O dono da trava, como gravado no arquivo.

    Attributes:
        schema_version: Versão do formato do arquivo.
        lock_id: Identificador único desta tomada (aparece na mensagem de quem foi recusado).
        command: Comando que a tomou (`probe`, `scan`, `authz`, `run`, `stack up`...).
        product: Produto da execução.
        pid: Número do processo dono.
        started_at: Instante da tomada (ISO 8601 com fuso).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(default=LOCK_SCHEMA_VERSION, ge=LOCK_SCHEMA_VERSION)
    lock_id: str = Field(pattern=r"^[0-9a-f]{8,64}$")
    command: str = Field(min_length=1, max_length=40)
    product: str = Field(min_length=1, max_length=80)
    pid: int = Field(gt=0)
    started_at: AwareDatetime


class LockVerdict(StrEnum):
    """O que fazer diante de uma trava que já existe."""

    HELD = "held"
    """O dono está vivo: a pilha está ocupada e a trava não pode ser tocada."""

    ORPHAN = "orphan"
    """O dono morreu sem soltar: a trava pode ser retomada."""

    UNREADABLE = "unreadable"
    """O conteúdo não é uma trava válida: não se sabe de quem é, então falha fechada."""


def render_lock(holder: LockHolder) -> str:
    """Texto do arquivo de trava para o dono dado (JSON, com fim de linha)."""
    return holder.model_dump_json(indent=2) + "\n"


def parse_lock(text: str) -> LockHolder | None:
    """Lê o texto de um arquivo de trava; `None` se estiver vazio, corrompido ou malformado.

    Nunca levanta: um arquivo ilegível vira `UNREADABLE` em `judge_lock`.
    """
    try:
        holder = LockHolder.model_validate_json(text)
    except ValidationError:
        return None
    return holder


def judge_lock(holder: LockHolder | None, *, process_alive: bool) -> LockVerdict:
    """Decide o destino de uma trava existente.

    Args:
        holder: Dono lido do arquivo; `None` quando o conteúdo é ilegível.
        process_alive: Se o processo `holder.pid` está vivo (ignorado quando `holder` é `None`).

    Returns:
        `UNREADABLE` sem dono legível; `HELD` com processo vivo; `ORPHAN` com processo morto.
        Só a trava órfã pode ser retomada: a de processo vivo nunca é apagada.
    """
    if holder is None:
        return LockVerdict.UNREADABLE
    return LockVerdict.HELD if process_alive else LockVerdict.ORPHAN


def describe_age(holder: LockHolder, now: datetime) -> str:
    """Há quanto tempo a trava foi tomada, em frase curta (`há 5 min`, `há 2 h 10 min`)."""
    seconds = max(int((now - holder.started_at).total_seconds()), 0)
    if seconds < _MINUTE:
        return "há menos de 1 min"
    if seconds < _HOUR:
        return f"há {seconds // _MINUTE} min"
    return f"há {seconds // _HOUR} h {(seconds % _HOUR) // _MINUTE} min"


def describe_holder(holder: LockHolder, now: datetime) -> str:
    """Quem ocupa a pilha: comando, produto, id, processo e quando começou."""
    return (
        f"`{holder.command}` do produto {holder.product} (id {holder.lock_id}, "
        f"processo {holder.pid}, desde {holder.started_at.isoformat()}, "
        f"{describe_age(holder, now)})"
    )


def busy_message(holder: LockHolder, now: datetime) -> tuple[str, str]:
    """Mensagem e orientação para quem foi recusado porque a pilha está ocupada."""
    return (
        f"A pilha está ocupada por {describe_holder(holder, now)}.",
        "Espere essa execução terminar e tente de novo. Para pará-la agora, rode hdast stop. "
        "Duas execuções na mesma pilha se corrompem, por isso a segunda é recusada.",
    )


def unreadable_message(location: str) -> tuple[str, str]:
    """Mensagem e orientação para uma trava que não dá para ler."""
    return (
        f"O arquivo de trava da pilha ({location}) está vazio, corrompido ou malformado, "
        "então não sei se há uma execução em andamento.",
        "Confira com hdast stack status se há execução rodando. Se nenhuma estiver, apague "
        "esse arquivo e tente de novo.",
    )

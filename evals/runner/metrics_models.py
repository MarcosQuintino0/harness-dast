"""Modelos da medicao do agente (`agent-metrics.json`) e da entrada (eventos do transcript).

Tudo que vem do transcript entra por modelo pydantic. Evento ou bloco que nao cabe no modelo e
descartado e contado em `quality`, nunca engolido em silencio.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION: Literal[1] = 1
STAGES = ("leitura", "cadastro", "alcance", "varredura", "triagem", "outro")


class Loose(BaseModel):
    """Entrada externa: campos desconhecidos sao ignorados."""

    model_config = ConfigDict(extra="ignore")


class UsageIn(Loose):
    """`message.usage` do Claude Code. Campo ausente fica `None`."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


class BlockIn(Loose):
    """Bloco de conteudo: `tool_use` (chamada) ou `tool_result` (resultado)."""

    type: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    tool_use_id: str | None = None
    content: Any = None
    is_error: bool | None = None


class MessageIn(Loose):
    """Mensagem de um evento. `content` pode ser texto puro ou lista de blocos."""

    id: str | None = None
    model: str | None = None
    content: str | list[dict[str, Any]] | None = None
    usage: dict[str, Any] | None = None


class EventIn(Loose):
    """Evento de conversa (`assistant` ou `user`)."""

    type: Literal["assistant", "user"]
    uuid: str | None = None
    timestamp: str | None = None
    message: MessageIn


class Frozen(BaseModel):
    """Saida: congelada e sem campo desconhecido."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class TokenCounts(Frozen):
    """Tokens somados. Cada mensagem do agente conta uma vez."""

    input: int = 0
    output: int = 0
    cache_creation: int = 0
    cache_read: int = 0


class StageMetrics(Frozen):
    """Uma etapa: tempo, tokens, chamadas e subcomandos `hdast`. `None` quando o dado nao existe."""

    seconds: float | None
    thinking_seconds: float | None
    waiting_seconds: float | None
    tokens: TokenCounts | None
    tool_calls: int
    hdast_commands: dict[str, int]


class Totals(Frozen):
    """Totais da rodada."""

    duration_seconds: float | None
    thinking_seconds: float | None
    waiting_seconds: float | None
    tokens: TokenCounts | None
    turns: int
    tool_calls: int
    tool_calls_by_tool: dict[str, int]
    hdast_commands: dict[str, int]


class Counted(Frozen):
    """Um nome (subcomando com flags, ou caminho de arquivo) e quantas vezes entrou no sinal."""

    name: str
    count: int


class Loops(Frozen):
    """Sinais de volta desnecessaria: so nomes e contagens, nunca conteudo."""

    repeated_hdast_commands: list[Counted]
    failed_then_retried: list[Counted]
    files_read_more_than_once: list[Counted]
    failed_calls: int


class Quality(Frozen):
    """O que o transcript nao deixou medir."""

    events: int
    events_malformed: int
    events_without_timestamp: int
    messages_without_usage: int


class RunMetricsSummary(Frozen):
    """Resumo de um `metrics.json` de execucao: so campos escalares do topo (sem esquema fixo)."""

    run_id: str
    summary: dict[str, str | int | float | bool]


class AgentMetrics(Frozen):
    """Conteudo de `agent-metrics.json`."""

    schema_version: Literal[1]
    label: str | None
    model: str | None
    totals: Totals
    stages: dict[str, StageMetrics]
    loops: Loops
    quality: Quality
    run_metrics: list[RunMetricsSummary]

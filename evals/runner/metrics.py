"""Medicao do agente por etapa: tempo, tokens, chamadas e voltas (`agent-metrics.json`).

Le so a conversa do transcript (`evals.runner.transcript`) e nao chama modelo. As etapas vem de
`metrics_stages` (regra deterministica). O que entra na saida: contagens, segundos, nomes de
subcomando e de flag, nomes de ferramenta e caminhos de arquivo lidos. Nunca entra conteudo de
arquivo, saida de comando, texto de raciocinio nem valor de argumento.

Tempo: o intervalo antes de um resultado de ferramenta, com chamada em aberto, e `esperando`
(inclui espera de permissao); todo outro intervalo e `pensando`. O intervalo vai para a etapa da
chamada a que se refere: o de espera, a chamada que roda; o de pensar, a da mensagem que vem depois.
Tokens: cada mensagem do agente conta uma vez (eventos de uma mesma mensagem repetem o `usage`).
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evals.runner.cases import EvalError
from evals.runner.metrics_models import (
    SCHEMA_VERSION,
    STAGES,
    AgentMetrics,
    BlockIn,
    Counted,
    EventIn,
    Loops,
    Quality,
    RunMetricsSummary,
    StageMetrics,
    TokenCounts,
    Totals,
    UsageIn,
)
from evals.runner.metrics_stages import Invocation, StageTracker, parse_hdast, shell_read_paths
from evals.runner.transcript import SHELL_TOOLS, ToolCall, load_conversation_events

MAX_LISTED = 20


@dataclass
class _Call:
    tool: ToolCall
    stage: str
    invocations: list[Invocation]
    failed: bool | None = None


@dataclass
class _Message:
    phase: str
    stage: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class _Gap:
    seconds: float
    waiting: bool
    owner: str  # id da chamada (espera) ou da mensagem (pensar)


def parse_timestamp(value: str | None) -> datetime | None:
    """ISO 8601 com ou sem `Z`; sem fuso vale UTC. Ausente ou invalido: `None`."""
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _blocks(event: EventIn) -> list[BlockIn]:
    content = event.message.content
    if not isinstance(content, list):
        return []
    blocks: list[BlockIn] = []
    for raw in content:
        try:
            blocks.append(BlockIn.model_validate(raw))
        except ValidationError:
            continue
    return blocks


def _is_failure(block: BlockIn) -> bool:
    if block.is_error:
        return True
    content = block.content
    if isinstance(content, list):
        content = " ".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return isinstance(content, str) and content.startswith("Exit code")


def _usage(raw: dict[str, Any] | None) -> dict[str, int] | None:
    if raw is None:
        return None
    try:
        parsed = UsageIn.model_validate(raw)
    except ValidationError:
        return None
    values = parsed.model_dump()
    return {key: value for key, value in values.items() if value is not None}


def _normalize_path(path: str) -> str:
    text = path.strip("\"'").replace("\\", "/")
    if "/workspace/" in text:
        text = text.split("/workspace/", 1)[1]
    elif text[1:3] == ":/" and "/Users/" in text:
        text = "~/" + text.split("/Users/", 1)[1].split("/", 1)[-1]
    return text[:120]


def _top(counter: Counter[str]) -> list[Counted]:
    rows = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [Counted(name=name, count=count) for name, count in rows[:MAX_LISTED]]


class _Walker:
    """Percorre os eventos uma vez e guarda o que as agregacoes precisam."""

    def __init__(self) -> None:
        self.tracker = StageTracker()
        self.calls: dict[str, _Call] = {}
        self.order: list[_Call] = []
        self.messages: dict[str, _Message] = {}
        self.gaps: list[_Gap] = []
        self.pending: set[str] = set()
        self.stamps: list[datetime] = []
        self.model: str | None = None
        self.last_ts: datetime | None = None
        self.malformed = 0
        self.unstamped = 0

    def feed(self, document: dict[str, Any]) -> None:
        try:
            event = EventIn.model_validate(document)
        except ValidationError:
            self.malformed += 1
            return
        moment = parse_timestamp(event.timestamp)
        blocks = _blocks(event)
        results = [b for b in blocks if b.type == "tool_result"]
        message_id = self._message(event) if event.type == "assistant" else None
        if moment is None:
            self.unstamped += 1
        else:
            self._gap(moment, event, results, message_id)
        for block in results:
            self._result(block)
        if message_id is not None:
            self._calls(event, blocks, message_id)

    def _message(self, event: EventIn) -> str:
        key = event.message.id or f"uuid:{event.uuid}"
        message = self.messages.setdefault(key, _Message(phase=self.tracker.phase))
        self.model = self.model or event.message.model
        usage = _usage(event.message.usage)
        for name, value in (usage or {}).items():
            message.usage[name] = max(message.usage.get(name, 0), value)
        return key

    def _gap(
        self, moment: datetime, event: EventIn, results: list[BlockIn], message_id: str | None
    ) -> None:
        previous, self.last_ts = self.last_ts, moment
        self.stamps.append(moment)
        if previous is None:
            return
        seconds = max(0.0, (moment - previous).total_seconds())
        known = [b.tool_use_id for b in results if b.tool_use_id in self.pending]
        if known and known[0] is not None:
            self.gaps.append(_Gap(seconds, True, known[0]))
        else:
            self.gaps.append(_Gap(seconds, False, message_id or f"phase:{self.tracker.phase}"))

    def _result(self, block: BlockIn) -> None:
        call = self.calls.get(block.tool_use_id or "")
        self.pending.discard(block.tool_use_id or "")
        if call is None:
            return
        call.failed = _is_failure(block)
        if not call.failed and any(i.label == "profile validate" for i in call.invocations):
            self.tracker.validated()

    def _calls(self, event: EventIn, blocks: list[BlockIn], message_id: str) -> None:
        message = self.messages[message_id]
        for block in blocks:
            if block.type != "tool_use" or block.input is None:
                continue
            tool = ToolCall(block.name or "", dict(block.input))
            found = parse_hdast(tool.command) if tool.name in SHELL_TOOLS else []
            call = _Call(tool, self.tracker.classify(tool, found), found)
            if message.stage is None:
                message.stage = call.stage
            key = block.id or f"anon:{len(self.order)}"
            self.calls[key] = call
            self.order.append(call)
            self.pending.add(key)


def _stage_of_message(walker: _Walker, key: str) -> str:
    if key.startswith("phase:"):
        return key.split(":", 1)[1]
    message = walker.messages[key]
    return message.stage or message.phase


def _tokens(usages: list[dict[str, int]]) -> TokenCounts | None:
    if not usages:
        return None
    return TokenCounts(
        input=sum(u.get("input_tokens", 0) for u in usages),
        output=sum(u.get("output_tokens", 0) for u in usages),
        cache_creation=sum(u.get("cache_creation_input_tokens", 0) for u in usages),
        cache_read=sum(u.get("cache_read_input_tokens", 0) for u in usages),
    )


def _stage_metrics(walker: _Walker, stage: str, timed: bool) -> StageMetrics:
    thinking = waiting = 0.0
    for gap in walker.gaps:
        if gap.waiting:
            if walker.calls[gap.owner].stage == stage:
                waiting += gap.seconds
        elif _stage_of_message(walker, gap.owner) == stage:
            thinking += gap.seconds
    usages = [
        m.usage
        for k, m in walker.messages.items()
        if m.usage and _stage_of_message(walker, k) == stage
    ]
    calls = [c for c in walker.order if c.stage == stage]
    commands = Counter(i.label for c in walker.order for i in c.invocations if i.stage == stage)
    return StageMetrics(
        seconds=round(thinking + waiting, 3) if timed else None,
        thinking_seconds=round(thinking, 3) if timed else None,
        waiting_seconds=round(waiting, 3) if timed else None,
        tokens=_tokens(usages),
        tool_calls=len(calls),
        hdast_commands=dict(sorted(commands.items())),
    )


def _loops(walker: _Walker) -> Loops:
    identities = Counter((i.signature, i.identity) for c in walker.order for i in c.invocations)
    repeated: Counter[str] = Counter()
    for (signature, _), times in identities.items():
        if times > 1:
            repeated[signature] += times - 1
    retried: Counter[str] = Counter()
    for index, call in enumerate(walker.order):
        if not call.failed:
            continue
        later = {i.label for c in walker.order[index + 1 :] for i in c.invocations}
        retried.update({i.label for i in call.invocations if i.label in later})
    reads: Counter[str] = Counter()
    for call in walker.order:
        if call.tool.name == "Read" and call.tool.target:
            reads[_normalize_path(call.tool.target)] += 1
        elif call.tool.name in SHELL_TOOLS:
            reads.update(_normalize_path(p) for p in shell_read_paths(call.tool.command))
    return Loops(
        repeated_hdast_commands=_top(repeated),
        failed_then_retried=_top(retried),
        files_read_more_than_once=_top(Counter({n: c for n, c in reads.items() if c > 1})),
        failed_calls=sum(1 for c in walker.order if c.failed),
    )


def summarize_run_metrics(out: Path) -> list[RunMetricsSummary]:
    """Campos escalares do topo de cada `trace/runs/*/metrics.json` valido. Sem esquema fixo."""
    rows: list[RunMetricsSummary] = []
    for path in sorted((out / "trace" / "runs").glob("*/metrics.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        summary = {
            str(key): value
            for key, value in data.items()
            if isinstance(value, bool | int | float)
            or (isinstance(value, str) and len(value) <= 80)
        }
        rows.append(RunMetricsSummary(run_id=path.parent.name, summary=summary))
    return rows


def measure_agent(out: Path, label: str | None = None) -> AgentMetrics:
    """Mede a rodada em `out` a partir de `<out>/transcript.*`.

    Raises:
        EvalError: Transcript ausente, vazio, que nao e JSON/JSONL ou sem evento de conversa.
    """
    events = load_conversation_events(out)
    if events is None:
        raise EvalError(
            f"Sem transcript legivel em {out}: coloque o JSONL da conversa em transcript.jsonl."
        )
    if not events:
        raise EvalError(
            f"O transcript de {out} nao tem nenhum evento de conversa (assistant/user)."
        )
    walker = _Walker()
    for document in events:
        walker.feed(document)
    timed = len(walker.stamps) >= 2
    duration = (max(walker.stamps) - min(walker.stamps)).total_seconds() if timed else None
    stages = {name: _stage_metrics(walker, name, timed) for name in STAGES}
    usages = [m.usage for m in walker.messages.values() if m.usage]
    by_tool = Counter(c.tool.name for c in walker.order)
    commands = Counter(i.label for c in walker.order for i in c.invocations)
    return AgentMetrics(
        schema_version=SCHEMA_VERSION,
        label=label,
        model=walker.model,
        totals=Totals(
            duration_seconds=round(duration, 3) if duration is not None else None,
            thinking_seconds=_sum(stages, "thinking_seconds"),
            waiting_seconds=_sum(stages, "waiting_seconds"),
            tokens=_tokens(usages),
            turns=len(walker.messages),
            tool_calls=len(walker.order),
            tool_calls_by_tool=dict(sorted(by_tool.items())),
            hdast_commands=dict(sorted(commands.items())),
        ),
        stages=stages,
        loops=_loops(walker),
        quality=Quality(
            events=len(events),
            events_malformed=walker.malformed,
            events_without_timestamp=walker.unstamped,
            messages_without_usage=len(walker.messages) - len(usages),
        ),
        run_metrics=summarize_run_metrics(out),
    )


def _sum(stages: dict[str, StageMetrics], field_name: str) -> float | None:
    values: list[float | None] = [getattr(s, field_name) for s in stages.values()]
    if any(v is None for v in values):
        return None
    return round(sum(v for v in values if v is not None), 3)

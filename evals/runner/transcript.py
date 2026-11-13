"""Leitura do transcript do agente.

Formatos aceitos: saida `stream-json` do Claude Code, arquivo `.output` de um subagente (JSONL do
Claude Code, com eventos de telemetria misturados) e texto livre. Nos dois primeiros, so os eventos
de conversa (`assistant` e `user`) contam; telemetria como `api-request` repete o contexto inteiro e
contaria cada chamada varias vezes.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SHELL_TOOLS = frozenset({"Bash", "PowerShell"})
READ_TOOLS = frozenset({"Read", "Grep", "Glob"})
WEB_TOOLS = frozenset({"WebFetch", "WebSearch"})
CONVERSATION_TYPES = frozenset({"assistant", "user"})


@dataclass(frozen=True)
class ToolCall:
    """Uma chamada de ferramenta do agente."""

    name: str
    arguments: dict[str, Any]

    @property
    def command(self) -> str:
        """Texto do comando, para ferramentas de shell."""
        return str(self.arguments.get("command", ""))

    @property
    def target(self) -> str:
        """Arquivo ou padrao alvo, para ferramentas de leitura."""
        for key in ("file_path", "path", "pattern"):
            if key in self.arguments:
                return str(self.arguments[key])
        return ""


@dataclass
class Transcript:
    """Chamadas estruturadas (quando o formato permite) e o texto bruto."""

    calls: list[ToolCall] = field(default_factory=list)
    raw: str = ""
    structured: bool = False

    def shell_commands(self) -> list[str]:
        """Comandos de shell, ou, em texto livre, o texto inteiro como uma unica entrada."""
        if not self.structured:
            return [self.raw]
        return [call.command for call in self.calls if call.name in SHELL_TOOLS]

    def read_targets(self) -> list[str]:
        """Alvos das ferramentas de leitura de arquivo."""
        return [call.target for call in self.calls if call.name in READ_TOOLS]

    def web_calls(self) -> list[ToolCall]:
        """Chamadas das ferramentas de web."""
        return [call for call in self.calls if call.name in WEB_TOOLS]


def _collect(node: Any, found: list[ToolCall]) -> None:
    if isinstance(node, dict):
        if node.get("type") == "tool_use" and isinstance(node.get("input"), dict):
            found.append(ToolCall(str(node.get("name", "")), dict(node["input"])))
        for value in node.values():
            _collect(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect(item, found)


def _parse_json_documents(raw: str) -> list[Any] | None:
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return [json.loads(stripped)]
    except json.JSONDecodeError:
        pass
    documents: list[Any] = []
    for line in stripped.splitlines():
        if not line.strip():
            continue
        try:
            documents.append(json.loads(line))
        except json.JSONDecodeError:
            return None
    return documents


def _is_conversation_event(document: Any) -> bool:
    return (
        isinstance(document, dict)
        and document.get("type") in CONVERSATION_TYPES
        and isinstance(document.get("message"), dict)
    )


def _conversation_only(documents: list[Any]) -> list[Any]:
    """Se houver eventos de conversa, descarta o resto e os repetidos (mesmo `uuid`)."""
    if not any(_is_conversation_event(document) for document in documents):
        return documents
    seen: set[str] = set()
    kept: list[Any] = []
    for document in documents:
        if not _is_conversation_event(document):
            continue
        uuid = document.get("uuid")
        if isinstance(uuid, str):
            if uuid in seen:
                continue
            seen.add(uuid)
        kept.append(document)
    return kept


def parse_transcript(raw: str) -> Transcript:
    """Interpreta o transcript. JSON ou JSONL com `tool_use` vira chamadas estruturadas."""
    documents = _parse_json_documents(raw)
    calls: list[ToolCall] = []
    if documents is not None:
        kept = _conversation_only(documents)
        _collect(kept, calls)
        if kept is not documents:
            raw = "\n".join(json.dumps(document, ensure_ascii=False) for document in kept)
    return Transcript(calls=calls, raw=raw, structured=bool(calls))


def load_transcript(out: Path) -> Transcript | None:
    """Le `<out>/transcript.*` (o primeiro, em ordem alfabetica), ou `None` se nao existe."""
    found = sorted(out.glob("transcript.*"))
    if not found:
        return None
    return parse_transcript(found[0].read_text(encoding="utf-8", errors="replace"))

"""Catálogo fixo de sinais de erro interno que a cerca reconhece em respostas (ADR 0049).

O que garante: a lista de categorias é fechada (`SignalCategory`); cada categoria tem severidade,
confiança e CWE decididos aqui, nunca pelo agente; `detect_signals` só devolve NOMES de
categoria, nunca trecho do texto; todo padrão usa quantificadores limitados e não aninha
repetições, então a busca é linear no tamanho do texto (limitado a `SCAN_LIMIT_BYTES`).
O que não faz: não decide escopo, não nega nada e não conserva texto. É heurística: há falso
positivo (documentação com exemplo de erro) e falso negativo (mensagem traduzida ou cortada).
Este módulo é puro.
"""

import re
from dataclasses import dataclass
from typing import Final, Literal

SignalCategory = Literal[
    "sql_error",
    "stack_trace_java",
    "stack_trace_python",
    "stack_trace_dotnet",
    "stack_trace_node",
    "stack_trace_php",
    "debug_page",
]
SignalSkip = Literal["type", "encoding", "empty", "error"]
"""Por que uma resposta liberada não foi lida: tipo sem texto de erro, codificação que a cerca
não abre, corpo vazio ou falha inesperada da leitura (que nunca nega a resposta)."""

SCAN_LIMIT_BYTES: Final = 65_536
COMPRESSED_INPUT_LIMIT: Final = 262_144

SignalSeverity = Literal["high", "medium", "low"]
SignalConfidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class SignalRule:
    """Regra de uma categoria.

    Attributes:
        category: Categoria que ela reconhece.
        label: Nome para o relatório.
        pattern: Expressão compilada (quantificadores limitados, sem repetição aninhada).
        severity: Severidade proposta pelo código.
        confidence: Confiança proposta pelo código.
        cwe: CWE da categoria.
    """

    category: SignalCategory
    label: str
    pattern: re.Pattern[str]
    severity: SignalSeverity
    confidence: SignalConfidence
    cwe: int


# "at" de uma linha de rastreamento: no começo de palavra ou logo depois de uma quebra de linha
# ou tabulação ESCAPADA dentro de JSON (`\n\tat ...`, onde o "t" do `\t` cola no "at").
_AT = r"(?:\b|(?<=\\[nrt]))at\s"
_GAP = r"(?:\s|\\[nrt]){1,12}"
_JAVA_FRAME = _AT + r"[\w$.<>]{1,200}\([\w$.]{1,100}\.(?:java|kt|scala):\d{1,7}\)"

_SQL = (
    r"(?-i:\bORA-\d{5}\b)"
    r"|\bSQLSTATE\s{0,3}[\[(:=]?\s{0,3}[0-9A-Z]{5}\b"
    r"|\bsyntax error at or near\b"
    r"|\byou have an error in your sql syntax\b"
    r"|\bunclosed quotation mark after the character string\b"
    r"|\bSQLite3::"
    r"|\bPSQLException\b"
    r"|\bjava\.sql\.SQL\w{0,40}Exception\b"
)
_JAVA = (
    _JAVA_FRAME
    + _GAP
    + _JAVA_FRAME
    + r"|\bCaused by:\s{1,5}(?:[a-z_][\w$]{0,60}\.){1,10}[\w$]{1,80}(?:Exception|Error)\b"
    + r"|\b(?:[a-z_][\w$]{0,60}\.){2,10}[\w$]{1,80}Exception:"
)
_PYTHON = (
    r"\bTraceback \(most recent call last\)"
    r"|\bFile \\?\"[^\"\n]{1,200}?\.py\\?\", line \d{1,7}\b"
)
_DOTNET = _AT + r"[\w.<>`$+]{1,200}\([^()\n]{0,200}\) in [^\n]{1,200}?\.cs:line \d{1,7}\b"
_NODE = (
    _AT
    + r"[^\n()]{1,200}\([^\n()]{0,200}(?:node_modules[/\\]|node:internal/)"
    + r"[^\n()]{0,200}:\d{1,7}:\d{1,7}\)"
)
_PHP = r"\bStack trace:" + _GAP + r"#0\b" + r"|\bPHP Fatal error:[^\n]{1,300}? on line \d{1,7}\b"
_DEBUG = (
    r"\bWerkzeug Debugger\b"
    r"|seeing this error because you have[^\n]{0,30}?DEBUG\s{0,3}=\s{0,3}True\b"
)


def _rule(
    category: SignalCategory,
    label: str,
    pattern: str,
    severity: SignalSeverity,
    confidence: SignalConfidence,
    cwe: int,
) -> SignalRule:
    return SignalRule(
        category, label, re.compile(pattern, re.IGNORECASE), severity, confidence, cwe
    )


SIGNAL_RULES: Final[tuple[SignalRule, ...]] = (
    _rule("sql_error", "Possível erro de banco de dados", _SQL, "medium", "medium", 209),
    _rule("stack_trace_java", "Possível rastreamento de exceção Java", _JAVA, "low", "medium", 209),
    _rule(
        "stack_trace_python",
        "Possível rastreamento de exceção Python",
        _PYTHON,
        "low",
        "medium",
        209,
    ),
    _rule(
        "stack_trace_dotnet", "Possível rastreamento de exceção .NET", _DOTNET, "low", "medium", 209
    ),
    _rule(
        "stack_trace_node", "Possível rastreamento de exceção Node.js", _NODE, "low", "medium", 209
    ),
    _rule("stack_trace_php", "Possível rastreamento de exceção PHP", _PHP, "low", "medium", 209),
    _rule("debug_page", "Página de depuração de framework exposta", _DEBUG, "medium", "high", 489),
)
"""Tabela fixa do ADR 0049. Ampliar a lista de categorias exige ADR novo."""

RULE_BY_CATEGORY: Final[dict[str, SignalRule]] = {rule.category: rule for rule in SIGNAL_RULES}

_TEXT_TYPES: Final = frozenset(
    {"application/json", "application/xml", "text/xml", "text/plain", "text/html"}
)
_NO_BODY_STATUS: Final = frozenset({204, 304})


def detect_signals(text: str | None) -> tuple[SignalCategory, ...]:
    """Categorias de sinal presentes em `text`, na ordem fixa do catálogo e sem repetição.

    Só olha os primeiros `SCAN_LIMIT_BYTES` caracteres. Texto vazio ou `None` não tem sinal.
    Nunca devolve trecho do texto.
    """
    if not text:
        return ()
    head = text[:SCAN_LIMIT_BYTES]
    return tuple(rule.category for rule in SIGNAL_RULES if rule.pattern.search(head))


def is_scannable(status: int, method: str, content_type: str | None) -> bool:
    """Diz se uma resposta liberada vale a leitura.

    Só olha resposta com corpo (fora 1xx, 204, 304 e `HEAD`) de tipo texto: JSON, XML (inclui
    `+json` e `+xml`), `text/plain` e `text/html`, ou sem tipo. JavaScript, CSS, imagem e
    binário ficam de fora (pacotes de interface trazem `Exception:` sem ser vazamento). Tipo
    malformado nunca levanta: sem tipo útil (vazio, `;;`) vale como ausente; sem barra, não lê.
    """
    if method.upper() == "HEAD" or status < 200 or status in _NO_BODY_STATUS:
        return False
    media = (content_type or "").split(";", 1)[0].strip().lower()
    if not media:
        return True
    if "/" not in media:
        return False
    return media in _TEXT_TYPES or media.endswith(("+json", "+xml"))

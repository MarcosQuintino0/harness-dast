"""Catálogo de sinais de erro interno da cerca (ADR 0049)."""

import time
from typing import get_args

import pytest

from harness_dast.domain.error_signal_catalog import (
    RULE_BY_CATEGORY,
    SCAN_LIMIT_BYTES,
    SIGNAL_RULES,
    SignalCategory,
    detect_signals,
    is_scannable,
)
from harness_dast.domain.internal_error_signals import classify_internal_error_signals
from harness_dast.domain.redaction import EvidenceMessage

JAVA_TRACE = (
    "java.lang.IllegalStateException: x\n\tat com.acme.A.run(A.java:10)"
    "\n\tat com.acme.B.go(B.java:20)"
)
JAVA_TRACE_JSON = (
    '{"trace":"x\\n\\tat com.acme.A.run(A.java:10)\\n\\tat com.acme.B.go(B.java:20)\\n"}'
)

POSITIVES: dict[SignalCategory, list[str]] = {
    "sql_error": [
        "ORA-00933: SQL command not properly ended",
        "SQLSTATE[42S02]: Base table or view not found",
        "SQLSTATE 23505",
        'ERROR: syntax error at or near "FROM"',
        "You have an error in your SQL syntax; check the manual",
        "Unclosed quotation mark after the character string 'x'.",
        "SQLite3::SQLException: no such table",
        "org.postgresql.util.PSQLException: bad",
        "java.sql.SQLSyntaxErrorException: bad",
    ],
    "stack_trace_java": [
        JAVA_TRACE,
        JAVA_TRACE_JSON,
        "Caused by: java.net.ConnectException: refused",
        "java.lang.NullPointerException: boom",
    ],
    "stack_trace_python": [
        "Traceback (most recent call last):\n  File ...",
        'File "/app/views.py", line 12, in handler',
        '{"e":"File \\"/app/views.py\\", line 12"}',
    ],
    "stack_trace_dotnet": [
        "at Acme.Service.Run(Int32 id) in C:\\src\\Service.cs:line 42",
    ],
    "stack_trace_node": [
        "at Object.<anonymous> (/app/node_modules/express/lib/router.js:10:5)",
        "at Module._compile (node:internal/modules/cjs/loader:1256:14)",
    ],
    "stack_trace_php": [
        "Fatal error: x\nStack trace:\n#0 /var/www/a.php(10): f()",
        "PHP Fatal error:  Uncaught Exception in /var/www/a.php on line 4",
    ],
    "debug_page": [
        "<title>Werkzeug Debugger</title>",
        "You're seeing this error because you have <code>DEBUG = True</code> in your settings",
    ],
}

NEGATIVES = [
    "",
    "   \n\t ",
    "{}",
    '{"id": 1, "nome": "Maria"}',
    "CORA-12345 e MORA-12345 não são códigos de erro",
    "ORA-12 curto demais",
    "Para ativar o modo de depuração, defina DEBUG = True no arquivo de configuração.",
    "A mensagem fala de Exception: mas sem pacote",
    "format com.acme.A.run(A.java:10) só uma linha de pilha: at com.acme.A.run(A.java:10)",
    "at foo (/app/src/index.js:10:5) fora de node_modules",
    "Traceback sem a frase inteira",
    "Stack trace: sem o frame zero",
    "syntax is fine; at or near the end",
]


def test_toda_categoria_do_catalogo_tem_positivos_testados() -> None:
    assert set(POSITIVES) == set(get_args(SignalCategory))
    assert [rule.category for rule in SIGNAL_RULES] == list(get_args(SignalCategory))


@pytest.mark.parametrize(
    ("category", "text"),
    [(category, text) for category, texts in POSITIVES.items() for text in texts],
)
def test_detect_signals_reconhece_a_categoria_quando_o_texto_traz_o_sinal(
    category: SignalCategory, text: str
) -> None:
    assert category in detect_signals(text)


@pytest.mark.parametrize("text", NEGATIVES)
def test_detect_signals_devolve_vazio_quando_o_texto_nao_e_um_sinal(text: str) -> None:
    assert detect_signals(text) == ()


def test_detect_signals_ignora_ora_no_meio_de_palavra_e_exige_cinco_digitos() -> None:
    assert detect_signals("CORA-00933 MORA-00933 ORA-1234 ORA-123456x") == ()


def test_detect_signals_so_reconhece_ora_em_maiusculas() -> None:
    assert detect_signals("ora-00933") == ()
    assert detect_signals("ORA-00933") == ("sql_error",)


def test_detect_signals_aceita_texto_vazio_none_e_so_espacos() -> None:
    assert detect_signals(None) == ()
    assert detect_signals("") == ()
    assert detect_signals("   \n  ") == ()


def test_detect_signals_traceback_cortado_ao_meio_nao_conta() -> None:
    assert detect_signals("Traceback (most recent call") == ()
    assert detect_signals('File "/app/x.py') == ()


def test_detect_signals_uma_linha_de_pilha_java_sozinha_nao_basta() -> None:
    assert detect_signals("at com.acme.A.run(A.java:10)") == ()


def test_detect_signals_devolve_na_ordem_fixa_do_catalogo_e_sem_repeticao() -> None:
    text = (
        "Werkzeug Debugger\nORA-00933\nORA-00934\n"
        + JAVA_TRACE
        + "\nTraceback (most recent call last)"
    )

    result = detect_signals(text)

    assert result == ("sql_error", "stack_trace_java", "stack_trace_python", "debug_page")
    assert len(set(result)) == len(result)


def test_detect_signals_nunca_devolve_trecho_do_texto() -> None:
    secret = "tok3n-SECRETO-9999"  # noqa: S105 - valor falso de teste
    result = detect_signals(f"ORA-00933 {secret} Traceback (most recent call last) {secret}")

    assert all(name in RULE_BY_CATEGORY for name in result)
    assert secret not in repr(result)


def test_detect_signals_aceita_unicode_controle_e_bidi_sem_quebrar() -> None:
    noise = "\u202e\x00\x1b[31m \U0001f600"
    text = f"{noise} ORA-00933 {noise} ação ✓ 日本語"

    assert detect_signals(text) == ("sql_error",)


def test_detect_signals_so_olha_o_prefixo_do_limite() -> None:
    late = "a" * SCAN_LIMIT_BYTES + "ORA-00933"

    assert detect_signals(late) == ()


@pytest.mark.parametrize(
    "text",
    [
        "at a(" * 20_000,
        "at " + "a." * 30_000,
        "ORA-" * 16_000,
        'File "' + "a" * 60_000,
        "Caused by: " + "a." * 20_000,
        ("at a.b(" + "x" * 150 + "node_modules/") * 400,
        "at com.a.B.c(B.java:1)" + "\\n" * 30_000,
        "SQLSTATE " * 8_000,
        "\\n\tat " * 10_000,
        "Stack trace:" + "\\n" * 30_000,
        "a." * 30_000 + "Exception:",
        'File "' + 'a.py" ' * 9_000,
    ],
)
def test_detect_signals_termina_rapido_com_texto_patologico_de_64_kib(text: str) -> None:
    started = time.perf_counter()
    detect_signals(text[:SCAN_LIMIT_BYTES])

    assert time.perf_counter() - started < 2.0


def test_o_que_os_padroes_do_adr_0045_reconhecem_algum_padrao_novo_tambem_reconhece() -> None:
    samples = [
        "Traceback (most recent call last):",
        "java.lang.NullPointerException: boom",
        JAVA_TRACE,
        "ORA-12345 senha",
        "SQLSTATE[23505]",
        'syntax error at or near "x"',
        "Unclosed quotation mark after the character string 'x'",
    ]
    for sample in samples:
        old = classify_internal_error_signals(
            {1: EvidenceMessage(message_id=1, response_body=sample)}
        )
        if old.counts["stack_trace"] or old.counts["sql_error"]:
            assert detect_signals(sample), sample


def test_cada_regra_tem_severidade_confianca_e_cwe_do_adr() -> None:
    table = {rule.category: (rule.severity, rule.confidence, rule.cwe) for rule in SIGNAL_RULES}

    assert table["sql_error"] == ("medium", "medium", 209)
    assert table["debug_page"] == ("medium", "high", 489)
    for category in get_args(SignalCategory):
        if category.startswith("stack_trace"):
            assert table[category] == ("low", "medium", 209)


@pytest.mark.parametrize(
    ("status", "method", "content_type", "expected"),
    [
        (200, "GET", "application/json", True),
        (200, "GET", "application/json; charset=utf-8", True),
        (200, "GET", "application/problem+json", True),
        (200, "GET", "application/xml", True),
        (200, "GET", "text/xml", True),
        (200, "GET", "application/atom+xml", True),
        (500, "GET", "text/plain", True),
        (500, "POST", "text/html; charset=UTF-8", True),
        (200, "GET", None, True),
        (200, "GET", "", True),
        (200, "HEAD", "application/json", False),
        (200, "head", "application/json", False),
        (204, "GET", "application/json", False),
        (304, "GET", "application/json", False),
        (101, "GET", "application/json", False),
        (100, "GET", None, False),
        (200, "GET", "image/png", False),
        (200, "GET", "application/javascript", False),
        (200, "GET", "text/css", False),
        (200, "GET", "application/octet-stream", False),
        (200, "GET", ";;", True),
        (200, "GET", "; charset=utf-8", True),
        (200, "GET", "charset=utf-8", False),
        (200, "GET", "   ", True),
    ],
)
def test_is_scannable_so_aceita_resposta_com_corpo_de_texto(
    status: int, method: str, content_type: str | None, expected: bool
) -> None:
    assert is_scannable(status, method, content_type) is expected

"""QA independente (V1.5c) da leitura de sinais da cerca (ADR 0049): bomba, malformação e ReDoS."""

import gzip
import io
import time
import zlib
from collections.abc import Mapping

import pytest

from harness_dast.adapters.scope_proxy.signals import (
    SignalReading,
    inspect_response,
    read_response_signals,
)
from harness_dast.domain.error_signal_catalog import (
    COMPRESSED_INPUT_LIMIT,
    SCAN_LIMIT_BYTES,
    detect_signals,
    is_scannable,
)

JSON: Mapping[str, str] = {"Content-Type": "application/json"}
TRACE = "Traceback (most recent call last)"
LIMIT_SECONDS = 3.0


def _gzip(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as handle:
        handle.write(data)
    return buffer.getvalue()


def test_a_gzip_bomb_is_read_with_bounded_output_and_never_raises() -> None:
    bomb = _gzip(b"\0" * (200 * 1024 * 1024))
    headers = {**JSON, "Content-Encoding": "gzip"}

    start = time.monotonic()
    reading = read_response_signals("GET", 200, headers, bomb)

    assert time.monotonic() - start < LIMIT_SECONDS
    assert reading.skipped in {None, "empty", "encoding"}


def test_a_deflate_bomb_in_both_framings_is_bounded() -> None:
    raw = b"A" * (100 * 1024 * 1024)
    for window in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
        compressor = zlib.compressobj(9, zlib.DEFLATED, window)
        bomb = compressor.compress(raw) + compressor.flush()
        start = time.monotonic()
        reading = read_response_signals("GET", 200, {**JSON, "Content-Encoding": "deflate"}, bomb)
        assert time.monotonic() - start < LIMIT_SECONDS
        assert reading.categories == ()


def test_a_trace_after_the_decompressed_limit_is_not_read() -> None:
    payload = b"x" * SCAN_LIMIT_BYTES + TRACE.encode()

    reading = inspect_response("GET", 200, {**JSON, "Content-Encoding": "gzip"}, _gzip(payload))

    assert reading.categories == ()


def test_a_trace_inside_the_decompressed_limit_is_read() -> None:
    reading = inspect_response(
        "GET", 200, {**JSON, "Content-Encoding": "GZIP "}, _gzip(TRACE.encode())
    )

    assert reading.categories == ("stack_trace_python",)


@pytest.mark.parametrize(
    "encoding", ["br", "zstd", "compress", "gzip, deflate", "deflate, gzip", "gzip;q=1", "\x00"]
)
def test_unknown_or_stacked_encodings_are_skipped_not_raised(encoding: str) -> None:
    reading = read_response_signals(
        "GET", 200, {**JSON, "Content-Encoding": encoding}, TRACE.encode()
    )

    assert reading == SignalReading(skipped="encoding")


@pytest.mark.parametrize("encoding", ["gzip", "x-gzip", "deflate"])
@pytest.mark.parametrize(
    "garbage",
    [b"not compressed at all", b"\x1f\x8b\x08\x00truncated", b"\x78\x9c\xff\xff", b"\x00" * 50],
)
def test_malformed_compressed_bodies_never_raise(encoding: str, garbage: bytes) -> None:
    reading = read_response_signals("GET", 200, {**JSON, "Content-Encoding": encoding}, garbage)

    assert reading.categories == ()
    assert reading.skipped in {None, "encoding", "empty"}


def test_the_compressed_input_over_the_cap_is_cut_and_still_safe() -> None:
    body = _gzip(TRACE.encode() + b" " * 10) + b"\x00" * (COMPRESSED_INPUT_LIMIT * 2)

    reading = read_response_signals("GET", 200, {**JSON, "Content-Encoding": "gzip"}, body)

    assert reading.categories == ("stack_trace_python",)


def test_a_body_of_invalid_utf8_is_decoded_with_replacement() -> None:
    body = b"\xff\xfe\x80" * 50 + TRACE.encode() + b"\xc3\x28"

    reading = inspect_response("GET", 500, JSON, body)

    assert reading.categories == ("stack_trace_python",)


def test_a_failure_inside_the_reader_becomes_skipped_error_and_never_denies() -> None:
    def boom(*_args: object) -> SignalReading:
        raise MemoryError

    # `MemoryError` descende de `Exception`: o leitor falha aberto e a cerca segue.
    reading = read_response_signals("GET", 200, JSON, b"x", inspect=boom)

    assert reading == SignalReading(skipped="error")


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        (None, True),
        ("", True),
        (";;", True),
        ("application/json; charset=utf-8", True),
        ("APPLICATION/JSON", True),
        ("application/problem+json", True),
        ("application/javascript", False),
        ("image/png", False),
        ("garbage", False),
        ("application/json\x00", False),
        ("text/html" + " " * 5000, True),
    ],
)
def test_content_type_edge_cases_never_raise(content_type: str | None, expected: bool) -> None:
    assert is_scannable(200, "GET", content_type) is expected


@pytest.mark.parametrize("status", [100, 101, 199, 204, 304])
def test_statuses_without_body_are_never_scanned(status: int) -> None:
    assert is_scannable(status, "GET", "application/json") is False


def test_head_is_never_scanned_in_any_case() -> None:
    assert is_scannable(200, "head", "application/json") is False
    assert is_scannable(200, "HEAD", None) is False


ADVERSARIAL = {
    "at-spam": "at " * 21_000,
    "at-paren-spam": "at a(" * 13_000,
    "dots": "a." * 32_000,
    "dots-long-segment": ("a" * 60 + ".") * 1_000,
    "exception-dots": ("abc." * 15) * 1_000,
    "at-long-name": "at " + "a" * 60_000,
    "at-java-almost": "at a.b.C(" + "x" * 60_000,
    "java-frames-gap": ("at a.b.C(D.java:1)" + " " * 11) * 3_000,
    "file-quote": 'File "' + "a" * 60_000,
    "file-quote-lines": ('File "' + "a" * 150 + "\n") * 400,
    "node-almost": ("at x(" + "node_modules/" + "y" * 190) * 300,
    "node-no-close": "at " + "(".join(["node_modules/a"] * 3000),
    "php": "Stack trace:" + " " * 60_000,
    "php-fatal": "PHP Fatal error:" + "a" * 60_000,
    "dotnet": "at a(" + ")" * 60_000 + " in ",
    "dotnet-in": ("at a() in " + "b" * 190 + "\n") * 300,
    "sqlstate": "SQLSTATE" + " " * 60_000,
    "escapes": "\\n\\t" * 21_000 + "at ",
    "unicode": "é" * 60_000,
    "caused-by": "Caused by: " + "a." * 30_000,
    "werkzeug-debug": "seeing this error because you have" + " " * 60_000,
}


@pytest.mark.parametrize("name", sorted(ADVERSARIAL))
def test_pathological_texts_are_read_in_bounded_time(name: str) -> None:
    text = ADVERSARIAL[name]

    start = time.monotonic()
    detect_signals(text)

    assert time.monotonic() - start < LIMIT_SECONDS


def test_the_reading_never_returns_a_piece_of_the_text() -> None:
    secret = "tok-ultra-secreto-9999"  # noqa: S105 - sentinela de teste
    text = f'{TRACE}\nFile "/app/x.py", line 3\nSQLSTATE[42S02] {secret}'

    categories = detect_signals(text)

    assert categories
    assert all(secret not in category for category in categories)
    assert all(category.isidentifier() for category in categories)

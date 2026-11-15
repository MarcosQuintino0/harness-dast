"""Leitura de sinais numa resposta liberada (ADR 0049): só categorias, memória limitada."""

import gzip
import tracemalloc
import zlib

from harness_dast.adapters.scope_proxy.signals import (
    SignalReading,
    inspect_response,
    read_response_signals,
)
from harness_dast.domain.error_signal_catalog import COMPRESSED_INPUT_LIMIT, SCAN_LIMIT_BYTES

JSON = {"Content-Type": "application/json"}
SQL = b'{"erro":"ORA-00933: SQL command not properly ended"}'


def headers(**extra: str) -> dict[str, str]:
    return {**JSON, **extra}


def test_corpo_comum_com_sinal_devolve_so_a_categoria() -> None:
    reading = inspect_response("GET", 500, JSON, SQL)

    assert reading == SignalReading(categories=("sql_error",), skipped=None)
    assert "ORA-00933" not in repr(reading)


def test_corpo_comum_sem_sinal_devolve_lido_e_vazio() -> None:
    assert inspect_response("GET", 200, JSON, b'{"id":1}') == SignalReading()


def test_nome_do_cabecalho_nao_diferencia_maiuscula() -> None:
    reading = inspect_response(
        "GET",
        500,
        {"content-type": "application/json", "CONTENT-ENCODING": "gzip"},
        gzip.compress(SQL),
    )

    assert reading.categories == ("sql_error",)


def test_gzip_valido_e_lido() -> None:
    reading = inspect_response(
        "GET", 500, headers(**{"Content-Encoding": "gzip"}), gzip.compress(SQL)
    )

    assert reading.categories == ("sql_error",)


def test_deflate_com_envelope_zlib_e_deflate_cru_sao_lidos() -> None:
    wrapped = zlib.compress(SQL)
    raw = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    bare = raw.compress(SQL) + raw.flush()

    for body in (wrapped, bare):
        reading = inspect_response("GET", 500, headers(**{"Content-Encoding": "deflate"}), body)
        assert reading.categories == ("sql_error",)


def test_gzip_truncado_le_o_que_deu_sem_levantar() -> None:
    body = gzip.compress(SQL * 50)[:-8]

    reading = inspect_response("GET", 500, headers(**{"Content-Encoding": "gzip"}), body)

    assert reading.skipped in (None, "encoding")


def test_gzip_corrompido_vira_encoding() -> None:
    reading = inspect_response(
        "GET", 500, headers(**{"Content-Encoding": "gzip"}), b"\x1f\x8b\x08\x00lixo-de-verdade"
    )

    assert reading == SignalReading(skipped="encoding")


def test_dado_que_nao_e_gzip_com_cabecalho_gzip_vira_encoding() -> None:
    reading = inspect_response("GET", 500, headers(**{"Content-Encoding": "gzip"}), SQL)

    assert reading.skipped == "encoding"


def test_bomba_de_descompressao_tem_saida_e_memoria_limitadas() -> None:
    bomb = gzip.compress(b"A" * 60_000_000, compresslevel=9)
    assert len(bomb) < COMPRESSED_INPUT_LIMIT
    tracemalloc.start()
    try:
        reading = inspect_response("GET", 200, headers(**{"Content-Encoding": "gzip"}), bomb)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert reading == SignalReading()
    assert peak < 5 * SCAN_LIMIT_BYTES * 8


def test_entrada_comprimida_acima_do_limite_so_le_o_prefixo() -> None:
    payload = SQL + b" " * 10_000_000
    body = gzip.compress(payload)

    reading = inspect_response("GET", 500, headers(**{"Content-Encoding": "gzip"}), body)

    assert reading.categories == ("sql_error",)


def test_br_e_zstd_viram_encoding() -> None:
    for name in ("br", "zstd", "compress", "gzip, br", "gzip, gzip"):
        reading = inspect_response("GET", 500, headers(**{"Content-Encoding": name}), b"qualquer")

        assert reading == SignalReading(skipped="encoding"), name


def test_identity_e_ausente_leem_o_corpo_cru() -> None:
    assert inspect_response("GET", 500, headers(**{"Content-Encoding": "identity"}), SQL).categories


def test_corpo_acima_do_limite_le_so_o_prefixo() -> None:
    late = b"a" * SCAN_LIMIT_BYTES + SQL
    early = SQL + b"a" * (SCAN_LIMIT_BYTES * 2)

    assert inspect_response("GET", 500, JSON, late).categories == ()
    assert inspect_response("GET", 500, JSON, early).categories == ("sql_error",)


def test_corpo_none_e_vazio_viram_empty() -> None:
    assert inspect_response("GET", 200, JSON, None) == SignalReading(skipped="empty")
    assert inspect_response("GET", 200, JSON, b"") == SignalReading(skipped="empty")


def test_corpo_que_descomprime_para_vazio_vira_empty() -> None:
    reading = inspect_response(
        "GET", 200, headers(**{"Content-Encoding": "gzip"}), gzip.compress(b"")
    )

    assert reading == SignalReading(skipped="empty")


def test_tipo_fora_do_catalogo_e_head_viram_type() -> None:
    assert inspect_response("GET", 200, {"Content-Type": "image/png"}, SQL).skipped == "type"
    assert inspect_response("HEAD", 200, JSON, SQL).skipped == "type"
    assert inspect_response("GET", 204, JSON, SQL).skipped == "type"


def test_byte_invalido_em_utf8_nao_derruba_a_leitura() -> None:
    reading = inspect_response("GET", 500, JSON, b"\xff\xfe\x80 ORA-00933 \xc3\x28")

    assert reading.categories == ("sql_error",)


def test_cabecalhos_vazios_valem_como_tipo_ausente() -> None:
    assert inspect_response("GET", 500, {}, SQL).categories == ("sql_error",)


def test_read_response_signals_devolve_o_mesmo_quando_nao_falha() -> None:
    assert read_response_signals("GET", 500, JSON, SQL) == inspect_response("GET", 500, JSON, SQL)


def test_falha_inesperada_da_leitura_vira_error_e_nao_levanta() -> None:
    def broken(*_: object) -> SignalReading:
        raise RuntimeError("defeito simulado")

    reading = read_response_signals("GET", 500, JSON, SQL, inspect=broken)

    assert reading == SignalReading(skipped="error")

"""Leitura do JSONL do Nuclei: projeção, linha malformada contada e nada de conteúdo em log."""

import json
from pathlib import Path

import pytest
import structlog

from harness_dast.adapters.nuclei.jsonl_reader import MAX_LINE_BYTES, NucleiJsonlReader
from harness_dast.domain.errors import ExternalToolError
from tests.fakes.nuclei import result_line

SEGREDOS = ("CURL-SEGREDO", "REQ-SEGREDO", "RESP-SEGREDO", "EXTRAIDO-SEGREDO")


def _read(tmp_path: Path, content: bytes):  # type: ignore[no-untyped-def]
    raw = tmp_path / "raw.jsonl"
    raw.write_bytes(content)
    return NucleiJsonlReader().read(raw)


def test_projeta_cada_linha_e_descarta_curl_request_response_e_extraidos(tmp_path: Path) -> None:
    parsed = _read(tmp_path, (result_line() + "\n").encode())

    record = parsed.records[0]
    dumped = record.model_dump_json()
    assert parsed.malformed == 0
    assert record.template_id == "springboot-env"
    assert record.extracted_count == 1
    assert record.extracted_bytes == len("EXTRAIDO-SEGREDO")
    for forbidden in ("curl-command", "request", "response", "extracted-results", *SEGREDOS):
        assert forbidden not in dumped


def test_linhas_malformadas_sao_contadas_e_a_leitura_continua(tmp_path: Path) -> None:
    content = "\n".join(
        [
            "{quebrado",
            result_line("a"),
            "[1, 2]",
            json.dumps({"template-id": "sem-resto"}),
            "",
            result_line("b"),
        ]
    )

    parsed = _read(tmp_path, content.encode())

    assert [r.template_id for r in parsed.records] == ["a", "b"]
    assert parsed.malformed == 3


def test_linha_que_nao_e_utf8_conta_como_malformada(tmp_path: Path) -> None:
    parsed = _read(tmp_path, b"\xff\xfe\n" + result_line().encode() + b"\n")

    assert parsed.malformed == 1
    assert len(parsed.records) == 1


def test_linha_grande_demais_conta_como_malformada_sem_ler_a_proxima_como_resto(
    tmp_path: Path,
) -> None:
    huge = b"{" + b"x" * (MAX_LINE_BYTES + 10) + b"}\n"

    parsed = _read(tmp_path, huge + result_line().encode() + b"\n")

    assert parsed.malformed == 1
    assert len(parsed.records) == 1


def test_arquivo_vazio_nao_tem_registros_nem_erros(tmp_path: Path) -> None:
    parsed = _read(tmp_path, b"")

    assert parsed.records == ()
    assert parsed.malformed == 0


def test_arquivo_ausente_levanta_erro_claro_da_ferramenta(tmp_path: Path) -> None:
    with pytest.raises(ExternalToolError, match="saída do Nuclei"):
        NucleiJsonlReader().read(tmp_path / "nao-existe.jsonl")


def test_nunca_registra_o_conteudo_de_uma_linha_em_log(tmp_path: Path) -> None:
    content = "\n".join(["{CONTEUDO-DA-LINHA-RUIM", result_line()])

    with structlog.testing.capture_logs() as logs:
        _read(tmp_path, content.encode())

    text = repr(logs)
    assert "CONTEUDO-DA-LINHA-RUIM" not in text
    for secret in SEGREDOS:
        assert secret not in text
    assert logs == [
        {"records": 1, "malformed": 1, "event": "nuclei.jsonl.read", "log_level": "info"}
    ]

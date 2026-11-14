import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from harness_dast.domain.command_journal import (
    NO_PRODUCT_STEM,
    JournalEntry,
    build_flags,
    build_journal_entry,
    classify_state,
    journal_file_stem,
    parse_journal_lines,
    slice_for_run,
    summarize_data,
)
from harness_dast.domain.redaction import MASK

BASE = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
RUN_1 = "2026-11-14T10-00-00Z-clinica-aaaa"
RUN_2 = "2026-11-14T12-00-00Z-clinica-bbbb"
RUN_3 = "2026-11-14T14-00-00Z-clinica-cccc"


def _identity(text: str) -> str:
    return text


def _entry(minute: int, command: str, run_id: str | None = None) -> JournalEntry:
    start = BASE + timedelta(minutes=minute)
    return JournalEntry(
        started_at=start,
        finished_at=start + timedelta(seconds=5),
        command=command,
        product="clinica",
        run_id=run_id,
        exit_code=0,
        state="ok",
    )


def _build(
    *,
    command: str = "probe",
    product: str | None = "clinica",
    run_id: str | None = RUN_1,
    flags: list[tuple[str, str | None]] | None = None,
    args: list[str] | None = None,
    exit_code: int = 0,
    error_code: str | None = None,
    data: dict[str, object] | None = None,
    mask: Callable[[str], str] = _identity,
) -> JournalEntry:
    return build_journal_entry(
        started_at=BASE,
        finished_at=BASE + timedelta(seconds=3),
        command=command,
        product=product,
        run_id=run_id,
        flags=flags or [],
        args=args or [],
        exit_code=exit_code,
        error_code=error_code,
        data=data,
        mask=mask,
    )


# ---- estado


@pytest.mark.parametrize(
    ("exit_code", "has_data", "expected"),
    [
        (0, False, "ok"),
        (1, True, "ok"),
        (4, True, "parcial"),
        (130, True, "parcial"),
        (2, False, "erro"),
        (10, False, "erro"),
    ],
)
def test_classify_state_usa_so_a_lista_fechada_quando_o_codigo_varia(
    exit_code: int, has_data: bool, expected: str
) -> None:
    assert classify_state(exit_code=exit_code, has_data=has_data) == expected


# ---- construção e mascaramento


def test_build_journal_entry_guarda_so_nomes_de_flags_sensiveis_com_valor_mascarado() -> None:
    entry = _build(flags=[("--api-token", "abc123"), ("--seed", "7"), ("--dry-run", None)])

    assert [(f.name, f.value) for f in entry.flags] == [
        ("--api-token", MASK),
        ("--seed", "7"),
        ("--dry-run", None),
    ]


def test_build_journal_entry_mascara_segredo_registrado_em_valor_livre() -> None:
    def mask(text: str) -> str:
        return text.replace("hunter2", MASK)

    entry = _build(flags=[("--only", "op-hunter2")], args=["hunter2"], mask=mask)

    assert entry.flags[0].value == f"op-{MASK}"
    assert entry.args == (MASK,)


def test_build_journal_entry_mascara_cpf_e_email_em_argumento_livre() -> None:
    entry = _build(args=["123.456.789-09", "ana@exemplo.com"])

    assert entry.args == (MASK, MASK)


def test_build_journal_entry_corta_valor_muito_longo() -> None:
    entry = _build(flags=[("--only", "x" * 500)])

    assert len(entry.flags[0].value or "") <= 120


@pytest.mark.parametrize("command", ["secret set", "secret delete"])
def test_build_journal_entry_de_secret_guarda_so_subcomando_e_nome(command: str) -> None:
    entry = _build(
        command=command,
        product=None,
        run_id=None,
        flags=[("--products-dir", "/x")],
        args=["MEU_SEGREDO", "valor-extra"],
        data={"stored": True, "nome": "MEU_SEGREDO"},
    )

    assert entry.flags == ()
    assert entry.args == ("MEU_SEGREDO",)
    assert entry.summary == {}


def test_build_journal_entry_descarta_run_id_fora_do_formato_sem_derrubar_o_registro() -> None:
    assert _build(run_id="../../etc").run_id is None


def test_build_journal_entry_descarta_produto_que_nao_e_slug() -> None:
    assert _build(product="../fora").product is None


def test_build_journal_entry_marca_parcial_quando_ha_erro_com_dados() -> None:
    entry = _build(exit_code=4, error_code="PREFLIGHT_FAILED", data={"ready": False})

    assert (entry.state, entry.error_code) == ("parcial", "PREFLIGHT_FAILED")


def test_journal_entry_recusa_fim_antes_do_inicio() -> None:
    with pytest.raises(ValidationError):
        JournalEntry(
            started_at=BASE,
            finished_at=BASE - timedelta(seconds=1),
            command="probe",
            exit_code=0,
            state="ok",
        )


def test_journal_entry_recusa_data_sem_fuso() -> None:
    with pytest.raises(ValidationError):
        JournalEntry(
            started_at=datetime(2026, 11, 14, 10, 0),
            finished_at=BASE,
            command="probe",
            exit_code=0,
            state="ok",
        )


def test_build_flags_aceita_lista_vazia() -> None:
    assert build_flags([], _identity) == ()


# ---- resumo


def test_summarize_data_mantem_contagens_booleanos_e_identificadores() -> None:
    data = {
        "status": "completed",
        "operations_sent": 30,
        "dry_run": False,
        "summary": {"successes": 24, "reachability": 0.8},
        "failures": [{"operation_id": "x", "body": "corpo do alvo"}] * 3,
    }

    assert summarize_data(data, _identity) == {
        "status": "completed",
        "operations_sent": 30,
        "dry_run": False,
        "summary.successes": 24,
        "summary.reachability": 0.8,
        "failures_count": 3,
    }


def test_summarize_data_descarta_texto_livre_e_chave_sensivel() -> None:
    data = {
        "message": "O servidor respondeu: <html>erro com espaços</html>",
        "token": "abc",
        "zap_api_key": "zzz",
        "nome": "ok-id",
    }

    assert summarize_data(data, _identity) == {"nome": "ok-id"}


def test_summarize_data_descarta_identificador_que_e_segredo_registrado() -> None:
    def mask(text: str) -> str:
        return text.replace("segredo123", MASK)

    assert summarize_data({"valor": "segredo123"}, mask) == {}


def test_summarize_data_limita_a_quantidade_de_itens() -> None:
    data = {f"k{i}": i for i in range(100)}

    assert len(summarize_data(data, _identity)) == 16


def test_summarize_data_sem_dados_devolve_vazio() -> None:
    assert summarize_data(None, _identity) == {}


def test_summarize_data_nao_leva_valor_de_objeto_aninhado_mais_fundo() -> None:
    assert summarize_data({"a": {"b": {"c": 1}}}, _identity) == {}


# ---- arquivo


def test_journal_file_stem_nunca_vira_caminho() -> None:
    assert journal_file_stem("clinica-piloto") == "clinica-piloto"
    assert journal_file_stem("../fora") == NO_PRODUCT_STEM
    assert journal_file_stem(None) == NO_PRODUCT_STEM


def test_parse_journal_lines_pula_e_conta_linhas_corrompidas() -> None:
    good = _entry(0, "doctor").model_dump_json()
    newer = json.dumps({**json.loads(good), "schema_version": 2})
    extra = json.dumps({**json.loads(good), "campo_novo": 1})
    lines = [good, "", "{quebrado", "[]", newer, extra, "   ", good]

    loaded = parse_journal_lines(lines)

    assert len(loaded.entries) == 2
    assert loaded.skipped_lines == 4


def test_journal_entry_ida_e_volta_pelo_json() -> None:
    original = _build(flags=[("--seed", "7")], data={"status": "completed", "n": 3})

    loaded = parse_journal_lines([original.model_dump_json()])

    assert loaded.entries == (original,)


# ---- recorte por teste


def _journal() -> list[JournalEntry]:
    return [
        _entry(0, "init"),
        _entry(1, "doctor"),
        _entry(2, "probe", RUN_1),
        _entry(3, "scan", RUN_1),
        _entry(4, "report", RUN_1),
        _entry(60, "doctor"),
        _entry(61, "profile validate"),
        _entry(62, "probe", RUN_2),
        _entry(63, "run", RUN_2),
        _entry(120, "stack up"),
    ]


def test_slice_for_run_do_primeiro_teste_vai_do_inicio_ao_fim_dele() -> None:
    got = slice_for_run(_journal(), RUN_1)

    assert [e.command for e in got] == ["init", "doctor", "probe", "scan", "report"]


def test_slice_for_run_do_segundo_vai_do_fim_do_anterior_ao_fim_dele() -> None:
    got = slice_for_run(_journal(), RUN_2)

    assert [e.command for e in got] == ["doctor", "profile validate", "probe", "run"]


def test_slice_for_run_nao_leva_comando_do_teste_seguinte() -> None:
    got = slice_for_run(_journal(), RUN_2)

    assert "stack up" not in [e.command for e in got]


def test_slice_for_run_nao_deixa_relatorio_refeito_de_teste_antigo_engolir_o_seguinte() -> None:
    journal = [*_journal(), _entry(130, "report", RUN_1), _entry(131, "doctor")]

    first = slice_for_run(journal, RUN_1)
    second = slice_for_run(journal, RUN_2)

    assert [e.command for e in second] == ["doctor", "profile validate", "probe", "run"]
    assert [e.command for e in first] == ["init", "doctor", "probe", "scan", "report"]


def test_slice_for_run_nao_inclui_comando_de_outra_execucao_no_intervalo() -> None:
    journal = [
        _entry(0, "doctor"),
        _entry(1, "probe", RUN_2),
        _entry(2, "report", RUN_1),
        _entry(3, "scan", RUN_2),
    ]

    assert [e.command for e in slice_for_run(journal, RUN_2)] == ["doctor", "probe", "scan"]


def test_slice_for_run_aceita_ordem_embaralhada() -> None:
    journal = list(reversed(_journal()))

    assert [e.command for e in slice_for_run(journal, RUN_2)] == [
        "doctor",
        "profile validate",
        "probe",
        "run",
    ]


def test_slice_for_run_sem_comando_da_execucao_devolve_vazio() -> None:
    assert slice_for_run(_journal(), RUN_3) == ()


def test_slice_for_run_com_diario_vazio_devolve_vazio() -> None:
    assert slice_for_run([], RUN_1) == ()


def test_slice_for_run_inclui_o_stack_up_mesmo_com_o_run_id_da_pilha() -> None:
    """O `stack up` grava o run_id da pilha (de antes do teste): não é "outro teste"."""
    stack = "2026-11-14T09-55-00Z-clinica-eeee"
    journal = [
        _entry(-5, "stack up", stack),
        _entry(1, "doctor"),
        _entry(2, "run", RUN_1),
        _entry(60, "stack down", stack),
        _entry(61, "stack up", "2026-11-14T10-59-00Z-clinica-ffff"),
        _entry(62, "run", RUN_2),
    ]

    first = slice_for_run(journal, RUN_1)
    second = slice_for_run(journal, RUN_2)

    assert [e.command for e in first] == ["stack up", "doctor", "run"]
    assert [e.command for e in second] == ["stack down", "stack up", "run"]

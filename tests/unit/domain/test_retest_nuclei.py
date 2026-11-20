"""Seleção e classificação do reteste dos achados do Nuclei (ADR 0122)."""

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.retest_nuclei import nuclei_retest_entries, select_retest_targets
from tests.fakes.nuclei import nuclei_finding, nuclei_result


def test_sem_escolha_pega_todos_os_abertos_do_mais_grave_para_o_menos() -> None:
    low, high, mid = (
        nuclei_finding("l", severity="low"),
        nuclei_finding("h", severity="high"),
        nuclei_finding("m", severity="medium"),
    )

    selected, opened = select_retest_targets((), (low, high, mid), (), 10)

    assert selected == ()
    assert opened == (high, mid, low)


def test_o_teto_limita_os_achados_do_nuclei_na_escolha_padrao() -> None:
    items = tuple(nuclei_finding(name, severity="high") for name in ("a", "b", "c"))

    _, opened = select_retest_targets((), items, (), 2)

    assert len(opened) == 2


def test_fingerprint_desconhecido_continua_sendo_erro() -> None:
    with pytest.raises(ConfigError, match="não existem"):
        select_retest_targets((), (nuclei_finding(),), ("f" * 64,), 10)


def test_teto_fora_do_intervalo_e_recusado_mesmo_so_com_nuclei() -> None:
    with pytest.raises(ConfigError, match="--max"):
        select_retest_targets((), (nuclei_finding(),), ("f" * 64,), 0)


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (None, "not_tested"),
        ("found", "reproduced"),
        ("empty", "not_reproduced"),
        ("stopped", "not_tested"),
        ("stopped_found", "reproduced"),
    ],
)
def test_classifica_pela_impressao_digital_e_pelo_fim_do_estagio(
    current: str | None, expected: str
) -> None:
    item = nuclei_finding("a")
    results = {
        None: None,
        "found": nuclei_result(findings=(item,)),
        "empty": nuclei_result(),
        "stopped": nuclei_result("stopped_kill", message="KILL"),
        "stopped_found": nuclei_result("stopped_kill", findings=(item,), message="KILL"),
    }

    (entry,) = nuclei_retest_entries((item,), results[current])

    assert entry.result == expected
    assert entry.origin == "nuclei"

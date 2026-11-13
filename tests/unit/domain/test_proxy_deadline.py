from datetime import UTC, datetime, timedelta

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.proxy_deadline import (
    STACK_MARGIN_MINUTES,
    compute_policy_deadline,
    stack_validity_minutes,
)
from harness_dast.domain.run import MAX_DURATION_MINUTES
from tests.fakes.profile_data import ALWAYS_OPEN_WINDOW, valid_profile_data

NOW = datetime(2026, 11, 10, 12, 0, 30, tzinfo=UTC)  # terça-feira


def profile_with(
    *, windows: list[str] | None = None, valid_until: str = "2999-12-31", minutes: int = 60
) -> ProductProfile:
    data = valid_profile_data()
    data["scope"]["windows"] = windows or [ALWAYS_OPEN_WINDOW]
    data["scope"]["authorization"]["valid_until"] = valid_until
    data["limits"]["max_duration_minutes"] = minutes
    return ProductProfile.from_data(data)


def test_deadline_e_a_duracao_maxima_mais_a_folga_quando_nada_encurta() -> None:
    expected = NOW + timedelta(minutes=45 + STACK_MARGIN_MINUTES)

    assert compute_policy_deadline(profile_with(minutes=45), NOW) == expected


def test_pilha_vale_mais_que_uma_execucao_para_o_ajuste_do_probe_caber() -> None:
    profile = profile_with(minutes=30)

    assert stack_validity_minutes(profile) == 30 + STACK_MARGIN_MINUTES
    assert compute_policy_deadline(profile, NOW) > NOW + timedelta(minutes=30)


def test_pilha_de_execucao_maxima_nunca_passa_do_teto_da_politica() -> None:
    profile = profile_with(minutes=480)

    assert stack_validity_minutes(profile) == MAX_DURATION_MINUTES + STACK_MARGIN_MINUTES


def test_deadline_com_folga_ainda_para_no_fechamento_da_janela() -> None:
    profile = profile_with(windows=["seg-dom 08:00-12:20 UTC"], minutes=30)

    assert compute_policy_deadline(profile, NOW) == datetime(2026, 11, 10, 12, 20, tzinfo=UTC)


def test_deadline_com_folga_ainda_nao_passa_do_fim_da_autorizacao() -> None:
    profile = profile_with(valid_until="2026-11-10", minutes=30)
    late = datetime(2026, 11, 10, 23, 30, 30, tzinfo=UTC)

    assert compute_policy_deadline(profile, late) == datetime(2026, 11, 11, tzinfo=UTC)


def test_deadline_para_no_fechamento_da_janela() -> None:
    profile = profile_with(windows=["seg-dom 08:00-12:30 UTC"])

    assert compute_policy_deadline(profile, NOW) == datetime(2026, 11, 10, 12, 30, tzinfo=UTC)


def test_deadline_nao_passa_do_fim_do_ultimo_dia_da_autorizacao() -> None:
    profile = profile_with(valid_until="2026-11-10", minutes=480)
    late = datetime(2026, 11, 10, 20, 0, 30, tzinfo=UTC)

    assert compute_policy_deadline(profile, late) == datetime(2026, 11, 11, tzinfo=UTC)


def test_deadline_segue_ate_o_fim_da_ultima_de_duas_janelas_sobrepostas() -> None:
    profile = profile_with(
        windows=["seg-dom 08:00-12:30 UTC", "seg-dom 12:00-13:10 UTC"], minutes=120
    )

    assert compute_policy_deadline(profile, NOW) == datetime(2026, 11, 10, 13, 10, tzinfo=UTC)

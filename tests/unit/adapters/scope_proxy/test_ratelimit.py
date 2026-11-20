import itertools

import pytest

from harness_dast.adapters.scope_proxy.ratelimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def make(rate: float = 10, queue: int = 5) -> tuple[RateLimiter, FakeClock]:
    clock = FakeClock()
    return RateLimiter(requests_per_second=rate, max_queued=queue, monotonic=clock), clock


def test_reserve_libera_o_primeiro_pedido_sem_espera() -> None:
    limiter, _ = make()

    assert limiter.reserve() == 0


def test_reserve_espaca_pedidos_simultaneos_pelo_intervalo() -> None:
    limiter, _ = make(rate=10, queue=5)

    delays = [limiter.reserve() for _ in range(4)]

    assert delays == pytest.approx([0.0, 0.1, 0.2, 0.3])


def test_reserve_nunca_libera_mais_que_a_taxa_em_uma_janela() -> None:
    limiter, clock = make(rate=20, queue=1000)
    releases: list[float] = []

    for _ in range(200):
        delay = limiter.reserve()
        assert delay is not None
        releases.append(clock.now + delay)
        clock.now += 0.001  # pedidos chegam bem mais rápido que a taxa

    gaps = [b - a for a, b in itertools.pairwise(releases)]
    assert min(gaps) >= 1 / 20 - 1e-9


def test_reserve_nao_acumula_credito_depois_de_ocioso() -> None:
    limiter, clock = make(rate=10, queue=5)
    limiter.reserve()
    clock.now += 60.0

    first, second = limiter.reserve(), limiter.reserve()

    assert first == 0
    assert second == pytest.approx(0.1)


def test_reserve_devolve_none_quando_a_fila_esta_cheia() -> None:
    limiter, _ = make(rate=10, queue=3)

    results = [limiter.reserve() for _ in range(5)]

    assert results[:3] != [None] * 3
    assert results[3] is None
    assert results[4] is None


def test_reserve_volta_a_aceitar_depois_que_a_fila_esvazia() -> None:
    limiter, clock = make(rate=10, queue=2)
    [limiter.reserve() for _ in range(2)]
    assert limiter.reserve() is None

    clock.now += 0.5

    assert limiter.reserve() == 0


def test_reserve_recusado_nao_consome_horario() -> None:
    limiter, clock = make(rate=10, queue=1)
    assert limiter.reserve() == 0
    assert limiter.reserve() is None
    clock.now += 0.1

    assert limiter.reserve() == 0


@pytest.mark.parametrize(("rate", "queue"), [(0, 1), (-1, 1), (10, 0)])
def test_construtor_recusa_parametros_invalidos(rate: float, queue: int) -> None:
    with pytest.raises(ValueError, match="taxa"):
        RateLimiter(requests_per_second=rate, max_queued=queue, monotonic=lambda: 0.0)


def test_concessao_real_apos_atraso_nao_cria_rajada() -> None:
    limiter, clock = make()
    limiter.grant()
    clock.now += 5
    assert limiter.delay_until_grant() == 0
    limiter.grant()
    assert limiter.delay_until_grant() == pytest.approx(0.1)


def test_recuo_global_nao_reduz_recuo_anterior() -> None:
    limiter, clock = make()
    limiter.grant()
    limiter.defer(10)
    clock.now += 1
    limiter.defer(1)
    assert limiter.delay_until_grant() == pytest.approx(9)
    clock.now += 9
    limiter.grant()
    assert limiter.delay_until_grant() == pytest.approx(0.1)

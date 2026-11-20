"""Regressões independentes da escolha do recurso lido pelo authz."""

from harness_dast.domain.authz.plan_mass import update_reader
from harness_dast.domain.probe_exchange import ExchangeRecord


def test_leitura_do_alvo_exato_precede_outro_objeto_da_mesma_conta() -> None:
    write = ExchangeRecord(
        operation_id="update",
        method="PATCH",
        path="/records/{id}",
        target="/records/2",
        account="a",
        status=200,
    )
    other_object = ExchangeRecord(
        operation_id="read",
        method="GET",
        path="/records/{id}",
        target="/records/1",
        account="a",
        status=200,
    )
    exact_object = other_object.model_copy(update={"target": "/records/2", "account": "b"})

    selected = update_reader(write, [other_object, exact_object])

    assert selected is not None
    assert (selected.target, selected.account) == ("/records/2", "a")

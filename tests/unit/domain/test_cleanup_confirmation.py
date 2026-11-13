"""Token de confirmação: emissão, validade, amarração e ausência do token em claro."""

from datetime import UTC, datetime, timedelta

import pytest

from harness_dast.domain.cleanup_confirmation import (
    CONFIRMATION_TTL,
    ConfirmationRecord,
    issue_record,
    verify_token,
)
from harness_dast.domain.errors import ConfigError

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
TOKEN = "hdc-token-secreto-de-teste"  # noqa: S105 - sentinela


def issued() -> ConfirmationRecord:
    return issue_record(
        token=TOKEN, product="agenda", run_id="run-1", script_sha256="abc", rows_ceiling=7, now=NOW
    )


def verify(
    record: ConfirmationRecord | None,
    token: str = TOKEN,
    *,
    product: str = "agenda",
    run_id: str = "run-1",
    script_sha256: str = "abc",
    now: datetime = NOW,
) -> ConfirmationRecord:
    return verify_token(
        record, token, product=product, run_id=run_id, script_sha256=script_sha256, now=now
    )


def test_record_stores_only_the_digest_and_the_binding_data() -> None:
    record = issued()

    assert TOKEN not in record.model_dump_json()
    assert len(record.token_sha256) == 64
    assert (record.product, record.run_id, record.script_sha256, record.rows_ceiling) == (
        "agenda",
        "run-1",
        "abc",
        7,
    )
    assert datetime.fromisoformat(record.expires_at) == NOW + CONFIRMATION_TTL


def test_verify_accepts_the_right_token_inside_the_ttl() -> None:
    record = issued()

    assert verify(record) == record
    assert verify(record, now=NOW + CONFIRMATION_TTL - timedelta(seconds=1)) == record


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"now": NOW + CONFIRMATION_TTL}, "venceu"),
        ({"now": NOW + timedelta(days=1)}, "venceu"),
        ({"product": "outro"}, "outro produto"),
        ({"run_id": "run-2"}, "outra execução"),
        ({"script_sha256": "mudou"}, "script de limpeza mudou"),
    ],
)
def test_verify_refuses_expired_token_or_another_product_run_or_script(
    changes: dict[str, object], fragment: str
) -> None:
    with pytest.raises(ConfigError) as caught:
        verify(issued(), **changes)  # type: ignore[arg-type]  # kwargs dinâmicos do parametrize

    assert fragment in caught.value.message


def test_verify_refuses_wrong_token_and_missing_record() -> None:
    with pytest.raises(ConfigError, match="não confere"):
        verify(issued(), "hdc-outro")
    with pytest.raises(ConfigError, match="Não há token"):
        verify(None)


def test_naive_clock_is_refused() -> None:
    with pytest.raises(ConfigError):
        verify(issued(), now=datetime(2026, 1, 1))

"""Saída humana do `stack status` com a pilha desatualizada (ADR 0081)."""

from harness_dast.application.stack_models import StackReport
from harness_dast.cli.commands.stack import _render


def _report(**changes: object) -> StackReport:
    base: dict[str, object] = {
        "managed": True,
        "running": True,
        "product": "demo",
        "run_id": "r1",
        "state_file": "stack.json",
    }
    return StackReport.model_validate({**base, **changes})


def test_render_destaca_a_pilha_desatualizada_e_o_que_fazer() -> None:
    text = _render(
        _report(binding="stale", stale_parts=("profile",), stale_message="mudou; hdast stack down")
    )

    assert "PILHA DESATUALIZADA: mudou; hdast stack down" in text


def test_render_diz_que_esta_igual_quando_fresca_e_nada_sem_a_conferencia() -> None:
    assert "iguais aos do stack up" in _render(_report(binding="fresh"))
    assert "DESATUALIZADA" not in _render(_report())

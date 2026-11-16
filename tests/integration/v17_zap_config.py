"""Leitura pontual de opções do ZAP local durante scans comprovadamente ativos."""

from datetime import UTC, datetime
from typing import Any

import httpx

from tests.integration.lab_support import ZapView


class FastZapView(ZapView):
    """Usa o estado isolado do suporte de laboratório e prazo curto na API local do ZAP."""

    def _get(self, path: str, **params: str) -> dict[str, Any]:
        response = httpx.get(
            self._base + path, params=params, headers=self._headers, timeout=2, trust_env=False
        )
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise TypeError("resposta ZAP inválida")
        return value


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 9_999_999_999 else None
    if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 10:
        return int(value)
    return None


def active_scans(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Aceita apenas ids numéricos, estados ativos e progresso explícito abaixo de 100."""
    scans = body.get("scans")
    if not isinstance(scans, list) or any(not isinstance(row, dict) for row in scans):
        raise ValueError("lista de scans inválida")
    active: dict[str, dict[str, Any]] = {}
    for row in scans:
        ident, progress, state = (
            _integer(row.get("id")),
            _integer(row.get("progress")),
            row.get("state"),
        )
        if ident is None or progress is None or not isinstance(state, str):
            raise ValueError("scan inválido")
        if state.upper() in {"RUNNING", "PAUSED"} and progress < 100:
            active[str(ident)] = {"id": str(ident), "state": state.upper(), "progress": progress}
    return active


def sample_zap(view: ZapView) -> dict[str, Any] | None:
    """Lê atraso entre duas consultas que confirmam o mesmo scan ativo; sem URLs ou chave."""
    before = active_scans(view._get("/JSON/ascan/view/scans/"))
    if not before:
        return None
    delay = _integer(view._get("/JSON/ascan/view/optionDelayInMs/").get("optionDelayInMs"))
    if delay is None:
        raise ValueError("atraso inválido")
    after = active_scans(view._get("/JSON/ascan/view/scans/"))
    common = sorted(before.keys() & after.keys())
    if not common:
        return None
    return {
        "at": datetime.now(UTC).isoformat(),
        "scans": [after[scan_id] for scan_id in common],
        "delay_ms": delay,
    }

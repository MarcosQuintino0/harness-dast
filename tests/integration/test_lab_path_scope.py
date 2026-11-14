"""A cerca (proxy de escopo) contra o laboratório real nos dois modos de caminho (V1.1, ADR 0026).

Sobe a Clínica Piloto com o proxy real e manda, pelo proxy, as formas de caminho do ADR 0026
contra a isca `/api/isca/**` (listada em `scope.deny_paths`). Nenhuma pode chegar à isca.
Confere também que o modo amplo libera `;` e `%2f` legítimos, que o estrito os recusa com o
`detail` certo e que o mitmproxy entrega o caminho byte a byte.

Exige Docker. Marcador `lab_fast`.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.widepath import interpretations
from tests.integration.lab_support import PILOT_PROFILE, LabCli, proxy_audit, require_docker
from tests.integration.path_support import (
    artifacts_dir,
    direct,
    pilot_requests,
    pilot_state,
    pilot_token,
    via_proxy,
)
from tests.integration.run_support import throwaway_pilot_env

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

# Formas do ADR 0026 (e mais algumas) tentando alcançar /api/isca/x. Rótulo -> caminho cru.
ISCA_FORMS: dict[str, str] = {
    "plain": "/api/isca/x",
    "raiz": "/api/isca",
    "; no fim": "/api/isca/x;x=1",
    "; no meio": "/api/isca;x=1/x",
    "; no inicio": "/api;x=1/isca/x",
    "%3b": "/api/isca%3bx=1/x",
    "%2f 1": "/api%2fisca/x",
    "%2f 2": "/api/isca%2fx",
    "%2F maiusculo": "/api%2Fisca/x",
    "%252f": "/api%252fisca/x",
    "%25252f": "/api%25252fisca/x",
    "%5c": "/api%5cisca/x",
    "%5C": "/api%5Cisca/x",
    "barra invertida crua": "/api\\isca/x",
    "//": "/api//isca/x",
    "// no inicio": "//api/isca/x",
    "ponto final": "/api/isca/x.",
    "ponto final no dir": "/api/isca.",
    "espaco final": "/api/isca/x%20",
    "espaco final no dir": "/api/isca%20/x",
    "MAIUSCULAS": "/API/ISCA/X",
    "Misto": "/api/Isca/x",
    "sufixo .json no dir": "/api/isca.json",
    "sufixo .json no fim": "/api/isca/x.json",
    "barra final": "/api/isca/",
    "barra final dupla": "/api/isca//",
    "..": "/api/x/../isca/x",
    "%2e%2e": "/api/x/%2e%2e/isca/x",
    "%2e%2e%2f": "/api/x/%2e%2e%2fisca/x",
    "..%2f": "/api/x/..%2fisca/x",
    ".": "/api/./isca/x",
    "%2e": "/api/%2e/isca/x",
    "letra codificada": "/%61pi/isca/x",
    "letra codificada 2": "/api/%69sca/x",
    "letra com dupla codificacao": "/api/%2569sca/x",
    "largura total": "/api/%EF%BD%89sca/x",
    "NUL": "/api/isca%00/x",
    "tab": "/api/isca%09/x",
    "espaco de largura zero": "/api/isca%E2%80%8B/x",
    "% solto": "/api/isca%/x",
    "%zz": "/api/isca%zz/x",
    "com consulta": "/api/isca/x?a=1",
    "%23": "/api/isca/x%23y",
    "%3f": "/api/isca/x%3fa",
}
# Formas que NÃO são leitura da isca (o segmento tem outro nome): o alvo as recebe sem chamá-la.
NOT_ISCA_BY_NAME = {"sufixo .json no dir"}
ADDED_FORMS: dict[str, str] = {"mais (outro nome)": "/api/isca+/x"}
CANARY = "/api/canario;m=1/x%2fy%252fz/%41%20"


@dataclass
class Stack:
    """Pilha no ar num modo de caminho."""

    mode: str
    cli: LabCli
    token: str


@pytest.fixture(scope="module", params=["strict", "wide"])
def stack(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Stack]:
    """Sobe a pilha da Clínica Piloto (modo vulnerável) com `path_mode` estrito ou amplo."""
    require_docker()
    mode = str(request.param)
    cli = LabCli(tmp_path_factory.mktemp(f"path-{mode}"), throwaway_pilot_env())
    folder = cli.install_product("clinica-piloto", PILOT_PROFILE)
    if mode == "wide":
        target = folder / "target.yml"
        text = target.read_text(encoding="utf-8")
        assert "  authorization:\n" in text
        target.write_text(
            text.replace("  authorization:\n", "  path_mode: wide\n  authorization:\n", 1),
            encoding="utf-8",
        )
    try:
        assert cli.run("stack", "up", "clinica-piloto", timeout=600).code == 0
        yield Stack(mode, cli, pilot_token(cli.env))
    finally:
        cli.stack_down()


# Recusas que o modo amplo mantém por forma (ADR 0026, parte 2, item 7).
_FORBIDDEN_FORM_DETAILS = {
    "path_dot_segment",
    "path_control_char",
    "path_invalid_utf8",
    "path_bad_percent",
    "url_forbidden_char",
    "url_not_ascii",
}


def _has_isca_reading(path: str) -> bool:
    """Diz se alguma leitura do modelo do modo amplo para este caminho cai sob /api/isca."""
    try:
        readings = interpretations(path.split("?", 1)[0])
    except ScopeViolation:
        return False
    return any(
        len(r) >= 2 and (r[0].casefold(), r[1].casefold()) == ("api", "isca") for r in readings
    )


def _detail_of(cli: LabCli, path: str) -> str | None:
    """`detail` da última linha da auditoria do proxy para este caminho (cru)."""
    for row in reversed(proxy_audit(cli)):
        if row.get("path") in {path, ascii(path)[1:-1]}:  # a auditoria escapa em ASCII
            detail = row.get("detail")
            return str(detail) if detail is not None else None
    return None


def test_isca_never_reaches_the_target_by_any_path_form(stack: Stack) -> None:
    # Preparar
    before = int(str(pilot_state()["isca_calls"]))
    table: list[dict[str, object]] = []

    # Agir
    for label, path in {**ISCA_FORMS, **ADDED_FORMS}.items():
        reply = via_proxy(path, stack.token)
        table.append(
            {
                "forma": label,
                "caminho": path,
                "status": reply.status,
                "reason": reply.reason,
                "detail": _detail_of(stack.cli, path) if reply.status == 403 else None,
            }
        )

    # Verificar
    state = pilot_state()
    assert int(str(state["isca_calls"])) == before == 0, "a isca foi chamada: " + json.dumps(table)
    reached = [r["forma"] for r in table if r["status"] != 403]
    allowed_to_reach = {"mais (outro nome)"} | (
        NOT_ISCA_BY_NAME if stack.mode == "strict" else {"% solto", "%zz"}
    )
    assert set(map(str, reached)) <= allowed_to_reach, f"formas que chegaram ao alvo: {reached}"
    if stack.mode == "wide":
        # `%` solto é liberado no modo amplo (o segmento `isca%` não é a isca); o Tomcat dá 400.
        assert {r["status"] for r in table if r["forma"] in {"% solto", "%zz"}} == {400}
    if stack.mode == "wide":
        # Toda forma cuja leitura é a isca volta com o motivo `deny_path`.
        wrong = [
            r["forma"]
            for r in table
            if r["status"] == 403
            and _has_isca_reading(str(r["caminho"]))
            and r["reason"] != "deny_path"
            and r["detail"] not in _FORBIDDEN_FORM_DETAILS
        ]
        assert not wrong, f"formas com leitura da isca que não voltaram deny_path: {wrong}"
    folder = artifacts_dir()
    if folder is not None:
        (folder / f"isca-via-proxy-{stack.mode}.json").write_text(
            json.dumps(
                {
                    "mode": stack.mode,
                    "isca_calls": state["isca_calls"],
                    "isca_mentions": state["isca_mentions"],
                    "rows": table,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def test_matrix_param_and_encoded_slash_reach_the_target_only_in_wide_mode(stack: Stack) -> None:
    # Preparar
    semicolon = "/api/saude;x=1"
    legit_slash = "/api/arquivos/..%2fbuild-info.txt"  # H9 do alvo vulnerável: só existe com %2f

    # Agir
    first = via_proxy(semicolon, stack.token)
    second = via_proxy(legit_slash, stack.token)

    # Verificar
    if stack.mode == "wide":
        assert first.status == 200
        assert second.status == 200
        assert "PILOT-BUILD-INFO" in second.body
    else:
        assert (first.status, first.reason) == (403, "malformed_request")
        assert (second.status, second.reason) == (403, "malformed_request")
        assert _detail_of(stack.cli, semicolon) == "path_matrix_param"
        assert _detail_of(stack.cli, legit_slash) == "path_encoded_slash"


def test_proxy_delivers_the_path_byte_for_byte_in_wide_mode(stack: Stack) -> None:
    if stack.mode != "wide":
        pytest.skip("o caminho do canário só é liberado no modo amplo")
    # Preparar: caminho sem rota no alvo (; %2f %252f %41 e espaço); o alvo conta pelo CRU.
    # Agir
    reply = via_proxy(CANARY, stack.token)
    seen = pilot_requests()
    sent_direct = direct(CANARY, stack.token)

    # Verificar: o alvo recebeu exatamente o mesmo texto, tanto pelo proxy quanto direto.
    assert reply.status == sent_direct.status != 403
    assert seen.get(f"GET (sem rota) {CANARY}", 0) >= 1, seen
    assert pilot_requests().get(f"GET (sem rota) {CANARY}", 0) == 2


def test_slow_endpoint_keeps_its_fixed_delay_behind_the_proxy(stack: Stack) -> None:
    reply = via_proxy("/api/relatorios/lento", stack.token)
    assert reply.status == 200
    rows = [r for r in proxy_audit(stack.cli) if r.get("path") == "/api/relatorios/lento"]
    assert rows
    assert rows[-1]["duration_ms"] >= 2000
    assert rows[-1]["duration_ms"] < 5000


def test_state_report_lists_isca_counters(stack: Stack) -> None:
    state = Path(str(stack.cli.state / "stack.json"))
    assert state.exists()
    snapshot = pilot_state()
    assert snapshot["isca_calls"] == 0
    assert "isca_mentions" in snapshot

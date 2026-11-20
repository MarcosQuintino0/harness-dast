"""Caminhos do OpenAPI no pedido mínimo: curinga `{x}`, escopo e sugestão de negados."""

from pathlib import Path

import pytest

from harness_dast.adapters.openapi.spec_paths import FileSpecPaths
from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.request_paths import allow_patterns, suggest_deny_paths, to_scope_pattern
from harness_dast.domain.scope import OutboundRequest, Scope, ScopeGuard, ScopeRule

ROOT = Path(__file__).resolve().parents[3]
HOST = "https://api.acme-teste.net.br"


def _paths(folder: str, name: str) -> tuple[str, ...]:
    return FileSpecPaths().read_paths(ROOT / folder, name)


@pytest.mark.parametrize(
    ("template", "prefix", "expected"),
    [
        ("/users/{id}", "", "/users/*"),
        ("/users/{id}/password", "", "/users/*/password"),
        ("/a/{x}/b/{y}", "", "/a/*/b/*"),
        ("/files/{name}.json", "", "/files/*"),
        ("/workshop/api/mechanic/", "", "/workshop/api/mechanic"),
        ("/users/{id}", "/api/v1", "/api/v1/users/*"),
        ("/", "", "/"),
    ],
)
def test_modelo_vira_padrao_da_cerca_quando_tem_marcador_de_caminho(
    template: str, prefix: str, expected: str
) -> None:
    assert to_scope_pattern(template, prefix) == expected


@pytest.mark.parametrize("template", ["/api/isca/**", "/a/*", "/a b", "/a%2fb", "/a;b", "/a/../b"])
def test_modelo_fica_de_fora_quando_a_cerca_nao_aceita_o_padrao(template: str) -> None:
    assert to_scope_pattern(template) is None


def test_curinga_de_marcador_e_aceito_pela_cerca_quando_o_caminho_tem_id() -> None:
    patterns, _ = allow_patterns(("/users/{id}", "/users/{id}/orders"), "")
    rule = ScopeRule(host="api.acme-teste.net.br", paths=patterns, methods=("GET",))
    guard = ScopeGuard(Scope(allow=(rule,)))

    guard.ensure_allowed(OutboundRequest(method="GET", url=f"{HOST}/users/42"))
    guard.ensure_allowed(OutboundRequest(method="GET", url=f"{HOST}/users/42/orders"))
    for outside in ("/users/42/other", "/users"):
        with pytest.raises(ScopeViolation):
            guard.ensure_allowed(OutboundRequest(method="GET", url=HOST + outside))


def test_allow_junta_repeticoes_e_conta_os_caminhos_recusados() -> None:
    patterns, skipped = allow_patterns(("/a/{x}", "/a/{y}", "/b", "/c/**"), "")

    assert patterns == ("/a/*", "/b")
    assert skipped == 1


def test_sugestao_nega_a_recuperacao_de_senha_do_crapi() -> None:
    denied = suggest_deny_paths(_paths("lab/crapi", "openapi.json"), "", frozenset())

    assert "/identity/api/auth/forget-password" in denied
    assert "/identity/api/auth/v2/check-otp" in denied
    assert "/identity/api/auth/v3/check-otp" in denied
    assert "/identity/api/v2/user/reset-password" in denied
    assert "/identity/api/v2/admin/videos/*" in denied


def test_sugestao_nega_a_troca_de_senha_do_vampi() -> None:
    denied = suggest_deny_paths(_paths("tests/fixtures/specs", "vampi.yml"), "", frozenset())

    assert "/users/v1/*/password" in denied


def test_sugestao_nao_nega_caminho_comum_quando_o_nome_e_inofensivo() -> None:
    denied = suggest_deny_paths(
        ("/users/{id}", "/books/v1", "/identity/api/auth/login", "/orders/{id}/items"),
        "",
        frozenset(),
    )

    assert denied == ()


@pytest.mark.parametrize(
    "template",
    [
        "/auth/logout",
        "/auth/sign-out",
        "/auth/signOut",
        "/account/delete_account",
        "/api/Admin/users",
        "/users/forgot",
        "/users/recover_access",
        "/users/{id}/change-password",
    ],
)
def test_sugestao_nega_o_caminho_quando_o_nome_tem_um_dos_padroes(template: str) -> None:
    assert len(suggest_deny_paths((template,), "", frozenset())) == 1


def test_sugestao_ignora_o_nome_do_marcador_quando_ele_parece_perigoso() -> None:
    assert suggest_deny_paths(("/users/{admin}",), "", frozenset()) == ()


@pytest.mark.parametrize(
    "template",
    ["/auth/verifyOtp", "/auth/verifyOTP", "/auth/OTPVerify", "/auth/check_otp", "/auth/check.otp"],
)
def test_sugestao_nega_o_caminho_quando_otp_e_uma_palavra(template: str) -> None:
    assert suggest_deny_paths((template,), "", frozenset()) == (template,)


@pytest.mark.parametrize("template", ["/footprint", "/hotpots", "/auth/{otp}"])
def test_sugestao_ignora_otp_quando_nao_e_palavra_em_segmento_literal(template: str) -> None:
    assert suggest_deny_paths((template,), "", frozenset()) == ()


def test_sugestao_preserva_o_login_quando_ele_esta_na_lista_de_preservar() -> None:
    keep = frozenset({"/auth/password-login", "/auth/otp-login"})
    denied = suggest_deny_paths(
        ("/auth/password-login", "/auth/otp-login", "/auth/reset"), "", keep
    )

    assert denied == ("/auth/reset",)


def test_sugestao_inclui_o_prefixo_do_endereco_base_quando_ele_existe() -> None:
    assert suggest_deny_paths(("/auth/reset",), "/api", frozenset()) == ("/api/auth/reset",)

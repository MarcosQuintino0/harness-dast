"""Carta `kind: request` (pedido mínimo, ADR 0120): perguntas, padrões e respostas explícitas."""

from datetime import date
from typing import Any

import pytest

from harness_dast.adapters.storage.strict_yaml import parse_profile_yaml
from harness_dast.domain.auth import PasswordLoginAuth
from harness_dast.domain.errors import ConfigError, ScopeViolation
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import LetterReview, review_letter
from harness_dast.domain.nuclei_permissions import nuclei_permissions
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.request_defaults import REQUEST_DEFAULTS
from harness_dast.domain.request_letter import RequestInputs
from harness_dast.domain.scope import OutboundRequest
from tests.fakes.letter_data import answer, request_letter_data, valid_letter_data

TODAY = date(2026, 11, 18)
HOST = "https://api.hml.acme-teste.net.br"
PATHS = (
    "/api/auth/login",
    "/api/users",
    "/api/users/{id}",
    "/api/auth/forgot-password",
    "/api/users/{id}/password",
    "/api/admin/stats",
)
STATIC_FIELDS = set(REQUEST_DEFAULTS) - {"auth.login_max_per_minute"} | {
    "scope.allow",
    "scope.deny_paths",
    "authorization.reference",
    "authorization.valid_until",
    "authorization.windows",
}
UNKNOWN = {"source": "desconhecido"}


def _data(**attack: Any) -> dict[str, Any]:
    data = request_letter_data()
    data["auth"]["token_path"] = answer("/api/auth/login", "pessoa")
    if attack:
        data["attack"] = attack
    return data


def _review(
    data: dict[str, Any],
    paths: tuple[str, ...] | None = PATHS,
    timezone: str = "America/Sao_Paulo",
    today: date = TODAY,
) -> LetterReview:
    inputs = RequestInputs(api_paths=paths, timezone=timezone)
    return review_letter(Letter.from_data(data), "demo", today, inputs)


def _profile(review: LetterReview) -> ProductProfile:
    assert review.profile_text is not None, review.issues
    return ProductProfile.from_data(parse_profile_yaml(review.profile_text))


def _fields(review: LetterReview, code: str) -> set[str]:
    return {w.field for w in review.warnings if w.code == code}


def _allowed(profile: ProductProfile, method: str, path: str) -> bool:
    try:
        profile.guard().ensure_allowed(OutboundRequest(method=method, url=HOST + path))
    except ScopeViolation:
        return False
    return True


# --- kind ---------------------------------------------------------------------------------


def test_carta_e_tratada_como_letter_quando_o_kind_esta_ausente() -> None:
    review = review_letter(Letter.from_data(valid_letter_data()), "demo", TODAY)

    assert review.ready
    assert "Modo pedido mínimo" not in (review.profile_text or "")
    assert not any(w.code == "REQUEST_DEFAULT_APPLIED" for w in review.warnings)


def test_carta_e_tratada_como_letter_quando_o_kind_e_letter() -> None:
    data = valid_letter_data()
    data["kind"] = "letter"

    review = review_letter(Letter.from_data(data), "demo", TODAY)

    assert review.ready
    assert (
        review.profile_text
        == review_letter(Letter.from_data(valid_letter_data()), "demo", TODAY).profile_text
    )


def test_carta_e_pedido_minimo_quando_o_kind_e_request() -> None:
    review = _review(_data())

    assert review.ready, review.issues
    assert "Modo pedido mínimo (ADR 0120)" in (review.profile_text or "")


@pytest.mark.parametrize("kind", ["pedido", "Request", "", "LETTER"])
def test_carta_pede_correcao_quando_o_kind_tem_valor_invalido(kind: str) -> None:
    data = _data()
    data["kind"] = kind

    review = _review(data)

    assert not review.ready
    assert [(i.field, i.code) for i in review.issues] == [("kind", "INVALID_VALUE")]


@pytest.mark.parametrize("kind", [5, True, ["request"], {"value": "request"}])
def test_carta_e_recusada_na_forma_quando_o_kind_nao_e_texto(kind: object) -> None:
    data = _data()
    data["kind"] = kind

    with pytest.raises(ConfigError):
        Letter.from_data(data)


# --- carta mínima ------------------------------------------------------------------------


def test_perfil_valida_e_traz_cada_padrao_em_aviso_e_cabecalho_quando_a_carta_e_minima() -> None:
    review = _review(_data())

    profile = _profile(review)  # ProductProfile.from_data: o perfil gerado valida
    assert _fields(review, "REQUEST_DEFAULT_APPLIED") == STATIC_FIELDS | {
        "auth.login_max_per_minute"
    }
    for field in STATIC_FIELDS | {"auth.login_max_per_minute"}:
        assert f"# Padrão do pedido mínimo: {field} = " in (review.profile_text or "")
    assert profile.scope.path_mode == "strict"
    assert (profile.limits.requests_per_second, profile.limits.max_duration_minutes) == (10, 30)
    assert profile.limits.zap_threads_per_host == 2
    assert profile.scan.strength == "LOW"
    assert profile.scan.pacing == "proxy"
    assert set(profile.scan.include_outcomes) == {
        "not_found",
        "validation_error",
        "conflict",
        "logical_failure",
        "client_error",
    }
    assert profile.scan.inject_headers
    assert profile.scan.oast
    assert profile.extra_checks.allow_rate_tests
    assert profile.extra_checks.experimental_rules
    assert profile.extra_checks.inventory
    assert profile.environment.name == "teste"


def test_pedido_minimo_liga_nuclei_e_login_e_deixa_caminhos_amplos_desligados_por_padrao() -> None:
    review = _review(_data())

    checks = _profile(review).extra_checks
    assert (checks.nuclei, checks.nuclei_login, checks.nuclei_wide_paths) == (True, True, False)
    assert {"extra_checks.nuclei", "extra_checks.nuclei_login"} <= _fields(
        review, "REQUEST_DEFAULT_APPLIED"
    )
    assert "extra_checks.nuclei_wide_paths" not in _fields(review, "REQUEST_DEFAULT_APPLIED")
    for field in ("extra_checks.nuclei", "extra_checks.nuclei_login"):
        assert f"# Padrão do pedido mínimo: {field} = true | " in (review.profile_text or "")


@pytest.mark.parametrize("name", ["nuclei", "nuclei_login"])
def test_pedido_minimo_desliga_nuclei_quando_a_pessoa_responde_falso(name: str) -> None:
    review = _review(_data(**{name: answer(False, "pessoa")}))

    assert getattr(_profile(review).extra_checks, name) is False
    assert f"extra_checks.{name}" not in _fields(review, "REQUEST_DEFAULT_APPLIED")


def test_pedido_minimo_nao_aplica_padrao_de_login_quando_a_pessoa_desliga_o_nuclei() -> None:
    review = _review(_data(nuclei=answer(False, "pessoa")))

    checks = _profile(review).extra_checks
    assert (checks.nuclei, checks.nuclei_login) == (False, False)
    assert "NUCLEI_OPTION_INACTIVE" not in {w.code for w in review.warnings}


def test_pergunta_5_liga_caminhos_amplos_quando_a_resposta_e_sim() -> None:
    review = _review(_data(nuclei_wide_paths=answer(True, "pessoa")))

    checks = _profile(review).extra_checks
    assert (checks.nuclei, checks.nuclei_wide_paths) == (True, True)
    assert _fields(review, "ATTACK_FLAG_AUTHORIZED") >= {"attack.nuclei_wide_paths"}
    assert "extra_checks.nuclei_wide_paths" not in _fields(review, "REQUEST_DEFAULT_APPLIED")


@pytest.mark.parametrize("reply", [answer(False, "pessoa"), UNKNOWN, None])
def test_pergunta_5_deixa_caminhos_amplos_desligados_quando_a_resposta_nao_e_sim(
    reply: dict[str, Any] | None,
) -> None:
    data = _data() if reply is None else _data(nuclei_wide_paths=reply)

    review = _review(data)

    assert _profile(review).extra_checks.nuclei_wide_paths is False
    assert review.issues == ()


def test_pergunta_5_com_texto_e_recusada_quando_a_resposta_nao_e_booleana() -> None:
    review = _review(_data(nuclei_wide_paths=answer("sim", "pessoa")))

    assert [(i.field, i.code) for i in review.issues] == [
        ("attack.nuclei_wide_paths", "INVALID_VALUE")
    ]


def test_pergunta_5_sim_nao_liga_a_escrita_do_nuclei_quando_a_pergunta_4_nao_e_sim() -> None:
    profile = _profile(_review(_data(nuclei_wide_paths=answer(True, "pessoa"))))

    assert nuclei_permissions(profile) == (False, False, True)


def test_escrita_do_nuclei_so_liga_com_a_pergunta_4_quando_o_pedido_e_minimo() -> None:
    sem = _profile(_review(_data()))
    com = _profile(_review(_data(allow_data_writes=answer(True, "pessoa"))))

    assert nuclei_permissions(sem).writes is False
    assert nuclei_permissions(com).writes is True
    assert nuclei_permissions(com).delete is False


def test_apagar_do_nuclei_exige_pergunta_4_e_pedido_explicito_de_delete() -> None:
    delete = {"allow_delete": answer(True, "pessoa")}
    writes = answer(True, "pessoa")
    only_writes = _profile(_review(_data(allow_data_writes=writes)))
    both = _data(allow_data_writes=writes)
    both["scope"] = delete
    only_delete = _data()
    only_delete["scope"] = delete

    assert nuclei_permissions(only_writes).delete is False
    assert nuclei_permissions(_profile(_review(both))).delete is True
    assert nuclei_permissions(_profile(_review(only_delete))).delete is False


def test_carta_assinada_nao_liga_nuclei_por_padrao() -> None:
    data = valid_letter_data()
    data["authorization"]["valid_until"] = answer("2027-06-30")
    data["scope"]["deny_paths"] = answer(["/api/admin/**"])

    review = review_letter(Letter.from_data(data), "demo", TODAY)

    assert review.profile_text is not None
    assert "nuclei" not in review.profile_text


def test_perfil_usa_o_login_e_as_contas_da_carta_quando_a_carta_e_minima() -> None:
    profile = _profile(_review(_data()))

    assert profile.auth.type == "login_password"
    assert profile.auth.login_limit is not None
    assert profile.auth.login_limit.max_per_minute == 5
    assert [a.alias for a in profile.auth.accounts] == ["user_a"]


def test_escopo_vem_so_do_endereco_da_pessoa_e_do_openapi_quando_o_pedido_e_minimo() -> None:
    profile = _profile(_review(_data()))

    (rule,) = profile.scope.allow
    assert (rule.host, rule.scheme, rule.port) == ("api.hml.acme-teste.net.br", "https", None)
    assert rule.methods == ("GET", "PATCH", "POST", "PUT")
    assert "/api/users/*" in rule.paths
    assert _allowed(profile, "GET", "/api/users/42")
    assert not _allowed(profile, "GET", "/api/unknown")
    assert not _allowed(profile, "GET", "/api/users/42/other")


def test_nenhum_padrao_liga_as_tres_escritas_quando_a_pergunta_4_nao_foi_respondida() -> None:
    profile = _profile(_review(_data()))

    assert not profile.authz.allow_writes
    assert not profile.negative.allow_writes
    assert not profile.scan.allow_upload_scan


def test_referencia_registra_o_dono_e_a_validade_conta_do_dia_informado() -> None:
    profile = _profile(_review(_data(), today=date(2026, 12, 15)))

    assert profile.scope.authorization.reference == (
        "pedido-demo-2026-12-15 (dono: Dona do Produto (dona@acme-teste.net.br))"
    )
    assert profile.scope.authorization.valid_until == date(2027, 1, 14)


@pytest.mark.parametrize("zone", ["America/Sao_Paulo", "UTC", "Asia/Tokyo"])
def test_janela_usa_o_fuso_informado_quando_a_pessoa_nao_declarou(zone: str) -> None:
    profile = _profile(_review(_data(), timezone=zone))

    (window,) = profile.scope.windows
    assert window.timezone == zone
    assert (window.start_minute, window.end_minute, len(window.days)) == (0, 1440, 7)


def test_referencia_cabe_no_limite_quando_o_dono_tem_nome_enorme() -> None:
    data = _data()
    data["gates"]["product_owner"] = answer("Dono " + "muito longo | " * 40)

    profile = _profile(_review(data))

    reference = profile.scope.authorization.reference
    assert len(reference) <= 200
    assert "|" not in reference


# --- portões -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gate", ["test_environment", "synthetic_data", "authorization_in_force", "product_owner"]
)
@pytest.mark.parametrize("reply", [answer(False), UNKNOWN])
def test_cadastro_para_quando_a_pergunta_1_e_nao_ou_desconhecida(
    gate: str, reply: dict[str, Any]
) -> None:
    data = _data()
    data["gates"][gate] = reply

    review = _review(data)

    assert not review.ready
    assert [i.field for i in review.issues] == [f"gates.{gate}"]


@pytest.mark.parametrize("reply", [UNKNOWN, answer(None, "pessoa")])
def test_cadastro_para_quando_a_pergunta_2_e_desconhecida_ou_ausente(reply: dict[str, Any]) -> None:
    data = _data()
    data["environment"]["base_url"] = reply

    review = _review(data)

    assert not review.ready
    assert [i.field for i in review.issues] == ["environment.base_url"]
    assert review.profile_text is None


def test_cadastro_para_quando_a_pergunta_2_nao_existe_na_carta() -> None:
    data = _data()
    del data["environment"]["base_url"]

    review = _review(data)

    assert [(i.field, i.code) for i in review.issues] == [("environment.base_url", "MISSING")]


@pytest.mark.parametrize(
    "url", ["ftp://api.acme-teste.net.br", "https://u:p@api.acme-teste.net.br", "api.acme", "x"]
)
def test_cadastro_para_quando_o_endereco_nao_e_aceito_pela_cerca(url: str) -> None:
    data = _data()
    data["environment"]["base_url"] = answer(url, "pessoa")

    review = _review(data)

    assert [i.field for i in review.issues] == ["environment.base_url"]


def test_endereco_nunca_vem_do_servers_do_openapi_quando_a_carta_nao_o_informa() -> None:
    data = _data()
    del data["environment"]["base_url"]
    data["environment"]["servers"] = answer("https://producao.acme.net.br")

    with pytest.raises(ConfigError):
        Letter.from_data(data)


def test_portoes_param_antes_de_ler_o_openapi_quando_a_pergunta_1_e_nao() -> None:
    data = _data()
    data["gates"]["test_environment"] = answer(False)

    review = review_letter(Letter.from_data(data), "demo", TODAY, RequestInputs(api_error="x"))

    assert [i.field for i in review.issues] == ["gates.test_environment"]


# --- OpenAPI ------------------------------------------------------------------------------


def test_carta_fica_pendente_quando_o_openapi_nao_foi_lido() -> None:
    review = review_letter(
        Letter.from_data(_data()),
        "demo",
        TODAY,
        RequestInputs(api_error="O OpenAPI não pôde ser lido."),
    )

    assert [(i.field, i.code) for i in review.issues] == [
        ("environment.openapi", "OPENAPI_UNREADABLE")
    ]
    assert review.issues[0].message == "O OpenAPI não pôde ser lido."


def test_carta_fica_pendente_quando_o_pedido_minimo_chega_sem_entradas() -> None:
    review = review_letter(Letter.from_data(_data()), "demo", TODAY)

    assert [i.code for i in review.issues] == ["OPENAPI_UNREADABLE"]


def test_carta_fica_pendente_quando_nenhum_caminho_cabe_na_cerca() -> None:
    review = _review(_data(), paths=("/a/**", "/b/*"))

    assert [i.code for i in review.issues] == ["OPENAPI_UNREADABLE"]


def test_caminho_recusado_pela_cerca_fica_de_fora_e_o_aviso_conta_quantos() -> None:
    review = _review(_data(), paths=(*PATHS, "/api/isca/**"))

    profile = _profile(review)
    assert "/api/isca/**" not in profile.scope.allow[0].paths
    allow_warning = next(w for w in review.warnings if w.field == "scope.allow")
    assert "1 caminho(s) ficaram de fora" in allow_warning.message


def test_escopo_se_divide_em_regras_quando_ha_mais_de_200_caminhos() -> None:
    paths = ("/api/auth/login", *(f"/api/r{index}" for index in range(450)))

    profile = _profile(_review(_data(), paths=paths))

    assert [len(rule.paths) for rule in profile.scope.allow] == [200, 200, 51]
    assert _allowed(profile, "GET", "/api/r449")


def test_escopo_leva_o_prefixo_e_a_porta_do_endereco_quando_o_endereco_os_tem() -> None:
    data = _data()
    data["environment"]["base_url"] = answer("https://api.hml.acme-teste.net.br:8443/v2", "pessoa")
    data["auth"]["token_path"] = answer("/api/auth/login", "pessoa")

    profile = _profile(_review(data))

    (rule,) = profile.scope.allow
    assert rule.port == 8443
    assert "/v2/api/users/*" in rule.paths


def test_regra_aceita_host_local_do_laboratorio_quando_o_endereco_e_local() -> None:
    data = _data()
    data["environment"]["base_url"] = answer("http://crapi", "pessoa")

    profile = _profile(_review(data))

    (rule,) = profile.scope.allow
    assert (rule.host, rule.scheme, rule.allow_local) == ("crapi", "http", True)


# --- pergunta 4 --------------------------------------------------------------------------


def _writes(profile: ProductProfile) -> tuple[bool, bool, bool]:
    return (
        profile.authz.allow_writes,
        profile.negative.allow_writes,
        profile.scan.allow_upload_scan,
    )


@pytest.mark.parametrize("source", ["pessoa", "carta"])
def test_tres_escritas_ligam_quando_a_pergunta_4_e_sim(source: str) -> None:
    review = _review(_data(allow_data_writes=answer(True, source)))

    assert _writes(_profile(review)) == (True, True, True)
    assert _fields(review, "AUTHZ_WRITES_AUTHORIZED") == {"attack.allow_authz_writes"}
    assert _fields(review, "NEGATIVE_WRITES_AUTHORIZED") == {"attack.allow_invalid_input_writes"}
    assert _fields(review, "UPLOAD_SCAN_AUTHORIZED") == {"attack.allow_upload_scan"}
    assert "authz.allow_writes" not in _fields(review, "REQUEST_DEFAULT_APPLIED")


@pytest.mark.parametrize("reply", [answer(False, "pessoa"), UNKNOWN, None])
def test_tres_escritas_ficam_desligadas_quando_a_pergunta_4_nao_e_sim(
    reply: dict[str, Any] | None,
) -> None:
    data = _data() if reply is None else _data(allow_data_writes=reply)

    assert _writes(_profile(_review(data))) == (False, False, False)


def test_pergunta_4_com_texto_e_recusada_quando_a_resposta_nao_e_booleana() -> None:
    review = _review(_data(allow_data_writes=answer("sim", "pessoa")))

    assert [(i.field, i.code) for i in review.issues] == [
        ("attack.allow_data_writes", "INVALID_VALUE")
    ]


def test_chave_individual_falsa_vence_a_pergunta_4_quando_as_duas_existem() -> None:
    review = _review(
        _data(allow_data_writes=answer(True, "pessoa"), allow_upload_scan=answer(False, "pessoa"))
    )

    assert _writes(_profile(review)) == (True, True, False)


def test_chave_individual_verdadeira_vence_a_pergunta_4_quando_ela_e_nao() -> None:
    review = _review(
        _data(allow_data_writes=answer(False, "pessoa"), allow_authz_writes=answer(True, "pessoa"))
    )

    assert _writes(_profile(review)) == (True, False, False)


def test_chave_individual_liga_so_ela_quando_a_pergunta_4_esta_ausente() -> None:
    review = _review(_data(allow_invalid_input_writes=answer(True, "pessoa")))

    assert _writes(_profile(review)) == (False, True, False)


@pytest.mark.parametrize(
    ("field", "reply"),
    [
        ("attack.allow_data_writes", {"allow_data_writes": answer(True, "pessoa")}),
        ("attack.allow_data_writes", {"allow_data_writes": answer(False, "carta", "texto")}),
    ],
)
def test_pergunta_4_e_recusada_quando_a_carta_e_letter(field: str, reply: dict[str, Any]) -> None:
    data = valid_letter_data()
    data["attack"] = reply

    review = review_letter(Letter.from_data(data), "demo", TODAY)

    assert [(i.field, i.code) for i in review.issues] == [(field, "REQUEST_ONLY")]


def test_escritas_continuam_exigindo_a_frase_da_carta_quando_a_carta_e_letter() -> None:
    data = valid_letter_data()
    data["attack"] = {"allow_authz_writes": answer(True, "pessoa")}

    review = review_letter(Letter.from_data(data), "demo", TODAY)

    assert [i.code for i in review.issues] == ["AUTHZ_WRITES_NEEDS_LETTER"]


# --- resposta explícita vence o padrão -----------------------------------------------------


@pytest.mark.parametrize(
    ("key", "check"),
    [
        ("inject_headers", lambda p: p.scan.inject_headers),
        ("oast", lambda p: p.scan.oast),
        ("allow_rate_tests", lambda p: p.extra_checks.allow_rate_tests),
        ("experimental_rules", lambda p: p.extra_checks.experimental_rules),
        ("inventory", lambda p: p.extra_checks.inventory),
    ],
)
def test_capacidade_desliga_quando_a_pessoa_responde_falso(key: str, check: Any) -> None:
    review = _review(_data(**{key: answer(False, "pessoa")}))

    assert check(_profile(review)) is False
    assert not any(
        w.field == f"attack.{key}" and w.code == "ATTACK_FLAG_AUTHORIZED" for w in review.warnings
    )


def test_capacidade_continua_ligada_quando_a_pessoa_confirma_sem_frase() -> None:
    review = _review(_data(oast=answer(True, "pessoa")))

    assert _profile(review).scan.oast is True
    assert "scan.oast" not in _fields(review, "REQUEST_DEFAULT_APPLIED")


def test_classes_desligam_quando_a_pessoa_declara_a_lista_vazia() -> None:
    review = _review(_data(include_outcomes=answer([], "pessoa")))

    assert _profile(review).scan.include_outcomes == ()
    assert "scan.include_outcomes" not in _fields(review, "REQUEST_DEFAULT_APPLIED")


def test_classes_seguem_a_lista_da_pessoa_quando_ela_escolhe_algumas() -> None:
    review = _review(_data(include_outcomes=answer(["not_found"], "pessoa")))

    assert _profile(review).scan.include_outcomes == ("not_found",)


def test_ritmo_volta_ao_legado_quando_a_pessoa_pede() -> None:
    assert _profile(_review(_data(pacing=answer("legacy", "pessoa")))).scan.pacing == "legacy"


@pytest.mark.parametrize("level", ["LOW", "MEDIUM", "HIGH"])
def test_forca_e_a_escolhida_quando_a_pessoa_responde_a_pergunta_3(level: str) -> None:
    review = _review(_data(strength=answer(level, "pessoa")))

    assert _profile(review).scan.strength == level
    assert "scan.strength" not in _fields(review, "REQUEST_DEFAULT_APPLIED")


@pytest.mark.parametrize("reply", [UNKNOWN, None])
def test_forca_e_low_quando_a_pergunta_3_e_desconhecida_ou_ausente(
    reply: dict[str, Any] | None,
) -> None:
    review = _review(_data() if reply is None else _data(strength=reply))

    assert _profile(review).scan.strength == "LOW"
    assert "scan.strength" in _fields(review, "REQUEST_DEFAULT_APPLIED")


def test_forca_invalida_e_recusada_quando_a_pessoa_escreve_outro_valor() -> None:
    review = _review(_data(strength=answer("EXTREME", "pessoa")))

    assert [(i.field, i.code) for i in review.issues] == [("attack.strength", "INVALID_VALUE")]


def test_limites_e_login_seguem_a_pessoa_quando_ela_os_declara() -> None:
    data = _data()
    data["limits"] = {
        "requests_per_second": answer(3, "pessoa"),
        "max_duration_minutes": answer(15, "pessoa"),
        "zap_threads_per_host": answer(1, "pessoa"),
    }
    data["auth"]["login_max_per_minute"] = answer(2, "pessoa")

    review = _review(data)

    profile = _profile(review)
    assert (profile.limits.requests_per_second, profile.limits.max_duration_minutes) == (3, 15)
    assert profile.limits.zap_threads_per_host == 1
    assert isinstance(profile.auth, PasswordLoginAuth)
    assert profile.auth.login_limit is not None
    assert profile.auth.login_limit.max_per_minute == 2
    assert not {f for f in _fields(review, "REQUEST_DEFAULT_APPLIED") if f.startswith("limits.")}


def test_limite_vira_padrao_do_pedido_quando_a_pessoa_responde_nao_sei() -> None:
    data = _data()
    data["limits"] = {"requests_per_second": UNKNOWN}

    review = _review(data)

    assert _profile(review).limits.requests_per_second == 10
    assert not any(w.code == "MINIMUM_DEFAULT_APPLIED" for w in review.warnings)


def test_chave_de_api_nao_recebe_limite_de_login_quando_o_login_nao_existe() -> None:
    data = _data()
    data["auth"] = {
        "type": answer("api_key", "pessoa"),
        "header_name": answer("X-Api-Key", "pessoa"),
        "accounts": answer(
            [{"alias": "svc", "role": "servico", "api_key": {"secret_ref": "env:ACME_SVC_KEY"}}]
        ),
    }

    review = _review(data)

    assert _profile(review).auth.type == "api_key"
    assert "auth.login_max_per_minute" not in _fields(review, "REQUEST_DEFAULT_APPLIED")


def test_autorizacao_segue_a_pessoa_quando_ela_declara_referencia_validade_e_janela() -> None:
    data = _data()
    data["authorization"] = {
        "reference": answer("CHG-1", "pessoa"),
        "valid_until": answer("2027-03-01", "pessoa"),
        "windows": answer(["seg-sex 20:00-06:00 UTC"], "pessoa"),
    }

    review = _review(data)

    profile = _profile(review)
    assert profile.scope.authorization.reference == "CHG-1"
    assert profile.scope.authorization.valid_until == date(2027, 3, 1)
    assert profile.scope.windows[0].timezone == "UTC"
    assert not {f for f in _fields(review, "REQUEST_DEFAULT_APPLIED") if "authorization" in f}


def test_autorizacao_vencida_da_pessoa_e_recusada_quando_a_validade_ja_passou() -> None:
    data = _data()
    data["authorization"] = {"valid_until": answer("2026-01-01", "pessoa")}

    review = _review(data)

    assert [i.code for i in review.issues] == ["AUTHORIZATION_EXPIRED"]


def test_nome_do_ambiente_segue_a_pessoa_quando_ela_o_informa() -> None:
    data = _data()
    data["environment"]["name"] = answer("homolog", "pessoa")

    assert _profile(_review(data)).environment.name == "homolog"


def test_escopo_explicito_vence_o_padrao_quando_a_pessoa_declara_os_caminhos() -> None:
    data = _data()
    data["scope"] = {
        "allow": answer(
            [
                {
                    "host": "api.hml.acme-teste.net.br",
                    "paths": ["/api/auth/**"],
                    "methods": ["GET", "POST"],
                }
            ],
            "pessoa",
        )
    }

    review = _review(data)

    profile = _profile(review)
    assert profile.scope.allow[0].paths == ("/api/auth/**",)
    assert "scope.allow" not in _fields(review, "REQUEST_DEFAULT_APPLIED")


# --- DELETE -------------------------------------------------------------------------------


def test_delete_fica_fora_quando_a_pessoa_nao_pede() -> None:
    review = _review(_data())

    profile = _profile(review)
    assert "DELETE" not in profile.scope.allow[0].methods
    assert not _allowed(profile, "DELETE", "/api/users/42")
    assert "DELETE_AUTHORIZED" not in {w.code for w in review.warnings}


@pytest.mark.parametrize("reply", [answer(False, "pessoa"), UNKNOWN])
def test_delete_fica_fora_quando_a_pessoa_responde_nao_ou_nao_sei(reply: dict[str, Any]) -> None:
    data = _data()
    data["scope"] = {"allow_delete": reply}

    assert "DELETE" not in _profile(_review(data)).scope.allow[0].methods


def test_delete_entra_quando_a_pessoa_pede_de_forma_explicita() -> None:
    data = _data()
    data["scope"] = {"allow_delete": answer(True, "pessoa")}

    review = _review(data)

    profile = _profile(review)
    assert _allowed(profile, "DELETE", "/api/users/42")
    assert "DELETE_AUTHORIZED" in {w.code for w in review.warnings}


def test_delete_e_recusado_quando_o_valor_nao_e_booleano() -> None:
    data = _data()
    data["scope"] = {"allow_delete": answer("sim", "pessoa")}

    assert [i.field for i in _review(data).issues] == ["scope.allow_delete"]


def test_delete_e_recusado_quando_a_pessoa_pede_junto_de_um_escopo_proprio() -> None:
    data = _data()
    data["scope"] = {
        "allow": answer(
            [{"host": "api.hml.acme-teste.net.br", "paths": ["/api/**"], "methods": ["GET"]}],
            "pessoa",
        ),
        "allow_delete": answer(True, "pessoa"),
    }

    assert [i.field for i in _review(data).issues] == ["scope.allow_delete"]


def test_delete_e_recusado_quando_a_carta_e_letter() -> None:
    data = valid_letter_data()
    data["scope"]["allow_delete"] = answer(True, "pessoa")

    review = review_letter(Letter.from_data(data), "demo", TODAY)

    assert [(i.field, i.code) for i in review.issues] == [("scope.allow_delete", "REQUEST_ONLY")]


# --- caminhos negados ---------------------------------------------------------------------


def test_sugestao_entra_no_perfil_e_no_aviso_quando_o_openapi_tem_caminho_perigoso() -> None:
    review = _review(_data())

    profile = _profile(review)
    assert profile.scope.deny_paths == (
        "/api/auth/forgot-password",
        "/api/users/*/password",
        "/api/admin/stats",
    )
    assert not _allowed(profile, "POST", "/api/auth/forgot-password")
    assert not _allowed(profile, "PUT", "/api/users/42/password")
    assert _allowed(profile, "GET", "/api/users")
    assert "scope.deny_paths" in _fields(review, "REQUEST_DEFAULT_APPLIED")


def test_caminho_comum_nao_e_negado_quando_o_nome_e_inofensivo() -> None:
    profile = _profile(_review(_data()))

    assert "/api/users" not in profile.scope.deny_paths
    assert "/api/users/*" not in profile.scope.deny_paths
    assert "/api/auth/login" not in profile.scope.deny_paths


def test_resposta_da_pessoa_soma_a_sugestao_quando_ela_nega_mais_caminhos() -> None:
    data = _data()
    data["scope"] = {"deny_paths": answer(["/api/users/*/orders", "/api/admin/stats"], "pessoa")}

    profile = _profile(_review(data))

    assert profile.scope.deny_paths == (
        "/api/auth/forgot-password",
        "/api/users/*/password",
        "/api/admin/stats",
        "/api/users/*/orders",
    )


@pytest.mark.parametrize("reply", [answer([], "pessoa"), UNKNOWN])
def test_sugestao_permanece_quando_a_pessoa_declara_lista_vazia_ou_nao_sei(
    reply: dict[str, Any],
) -> None:
    data = _data()
    data["scope"] = {"deny_paths": reply}

    profile = _profile(_review(data))

    assert "/api/auth/forgot-password" in profile.scope.deny_paths


def test_resposta_malformada_e_recusada_quando_deny_paths_nao_e_lista_de_textos() -> None:
    data = _data()
    data["scope"] = {"deny_paths": answer("/api/x", "pessoa")}

    review = _review(data)

    assert [i.field for i in review.issues] == ["scope.deny_paths"]


def test_aviso_de_lista_vazia_aparece_quando_nada_e_sugerido_nem_respondido() -> None:
    review = _review(_data(), paths=("/api/auth/login", "/api/users"))

    assert _profile(review).scope.deny_paths == ()
    assert "DENY_PATHS_EMPTY" in {w.code for w in review.warnings}
    assert "scope.deny_paths" not in _fields(review, "REQUEST_DEFAULT_APPLIED")


def test_login_nao_e_negado_quando_o_nome_dele_parece_perigoso() -> None:
    data = _data()
    data["auth"]["token_path"] = answer("/api/auth/password-login", "pessoa")

    profile = _profile(_review(data, paths=("/api/auth/password-login", "/api/users")))

    assert profile.scope.deny_paths == ()


# --- caminho amplo ------------------------------------------------------------------------


def test_caminho_e_strict_quando_a_pessoa_nao_responde() -> None:
    review = _review(_data())

    assert _profile(review).scope.path_mode == "strict"
    assert "scope.path_mode" in _fields(review, "REQUEST_DEFAULT_APPLIED")


def test_caminho_strict_explicito_nao_gera_aviso_de_padrao() -> None:
    data = _data()
    data["scope"] = {"path_mode": answer("strict", "pessoa")}

    review = _review(data)

    assert _profile(review).scope.path_mode == "strict"
    assert "scope.path_mode" not in _fields(review, "REQUEST_DEFAULT_APPLIED")


@pytest.mark.parametrize(
    "reply",
    [answer("wide", "carta", "A carta diz que o modo amplo vale."), answer("wide", "pessoa")],
)
def test_modo_amplo_e_recusado_quando_a_carta_e_pedido_minimo(reply: dict[str, Any]) -> None:
    data = _data()
    data["scope"] = {"path_mode": reply}

    review = _review(data)

    assert [(i.field, i.code) for i in review.issues] == [("scope.path_mode", "WIDE_NEEDS_LETTER")]


def test_modo_amplo_continua_valendo_na_carta_assinada_quando_traz_a_frase() -> None:
    data = valid_letter_data()
    data["scope"]["path_mode"] = answer("wide", "carta", "A carta autoriza o modo amplo.")

    review = review_letter(Letter.from_data(data), "demo", TODAY)

    assert review.ready
    assert 'path_mode: "wide"' in (review.profile_text or "")


# --- determinismo ---------------------------------------------------------------------------


def test_texto_gerado_e_identico_quando_a_mesma_carta_e_conferida_duas_vezes() -> None:
    assert _review(_data()).profile_text == _review(_data()).profile_text


def test_carta_nao_e_alterada_quando_a_conferencia_a_completa() -> None:
    data = _data()
    letter = Letter.from_data(data)
    before = letter.model_dump()

    review_letter(letter, "demo", TODAY, RequestInputs(api_paths=PATHS))

    assert letter.model_dump() == before

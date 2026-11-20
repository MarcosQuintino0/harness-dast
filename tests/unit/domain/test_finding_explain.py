import re

import pytest

from harness_dast.domain.authz.findings import TECHNIQUE_LABEL
from harness_dast.domain.finding import Classification, Finding, FindingEvidence
from harness_dast.domain.finding_explain import (
    GENERIC_KEY,
    WHO_VALUES,
    FindingExplanation,
    catalog_entries,
    explain_authz_technique,
    explain_finding,
    explain_zap_alert,
)

# Palavras que o desenho do painel proíbe (promessa ou atestado).
_FORBIDDEN = re.compile(
    r"\b(seguro|segura|seguros|aprovad[oa]s?|garant\w*|resolv\w*|100%|sem risco|corrigid[oa]s?)\b",
    re.IGNORECASE,
)
# Jargão que não pode aparecer nos quatro textos para leigos (o nome técnico pode ter).
_JARGON = re.compile(
    r"\b(SQL|XSS|CSRF|CORS|XXE|SSRF|HTTP|HTTPS|API|URL|endpoint|payload|header|token|exploit|"
    r"JWT|CWE|OWASP|BOLA|IDOR|BFLA)\b",
    re.IGNORECASE,
)

# Tipos que aparecem nos findings.json das rodadas pilot-vuln-strict e pilot-vuln-wide da V1.1
# (plugin do ZAP, CWE e título) e na pasta authz-vulneravel.
_PILOT_TYPES = [
    ("10010", 1004, "Cookie No HttpOnly Flag"),
    ("10021", 693, "X-Content-Type-Options Header Missing"),
    ("10111", None, "Authentication Request Identified"),
    ("10112", None, "Session Management Response Identified"),
    ("40018", 89, "SQL Injection"),
    ("40019", 89, "SQL Injection - MySQL (Time Based)"),
    ("40021", 89, "SQL Injection - Oracle (Time Based)"),
    ("40022", 89, "SQL Injection - PostgreSQL (Time Based)"),
    ("40027", 89, "SQL Injection - MsSQL (Time Based)"),
    ("6", 22, "Path Traversal"),
]


def _all_texts(entry: FindingExplanation) -> list[str]:
    return [
        entry.title,
        entry.what_happened,
        entry.why_it_matters,
        *(step.text for step in entry.what_to_do),
    ]


def _finding(plugin_id: str, cwe: int | None, title: str) -> Finding:
    return Finding(
        finding_id="F-00000001",
        fingerprint="a" * 64,
        title=title,
        plugin_id=plugin_id,
        alert_ref=plugin_id,
        classification=Classification(cwe=cwe),
        proposed_severity="high",
        proposed_confidence="high",
        method="GET",
        path_template="/x",
        attribution="source_message",
        occurrences=1,
        evidence=FindingEvidence(),
    )


def test_toda_entrada_tem_todos_os_campos_preenchidos() -> None:
    entries = catalog_entries()

    assert len(entries) >= 20
    for entry in entries:
        assert entry.key not in {"", GENERIC_KEY}
        assert entry.known is True
        assert all(text.strip() for text in _all_texts(entry)), entry.key
        assert entry.technical_name.strip(), entry.key
        assert entry.what_to_do, entry.key


def test_toda_entrada_tem_quem_na_lista_fechada() -> None:
    for entry in catalog_entries():
        assert entry.who in WHO_VALUES
        assert all(step.who in WHO_VALUES for step in entry.what_to_do), entry.key


def test_quem_na_lista_fechada_e_exatamente_os_tres_papeis() -> None:
    assert set(WHO_VALUES) == {"QA", "dono do produto", "time de desenvolvimento"}


def test_nenhuma_entrada_usa_termo_proibido() -> None:
    for entry in catalog_entries():
        for text in [*_all_texts(entry), entry.technical_name]:
            assert not _FORBIDDEN.search(text), (entry.key, text)


def test_textos_para_leigos_nao_usam_jargao() -> None:
    for entry in catalog_entries():
        for text in _all_texts(entry):
            assert not _JARGON.search(text), (entry.key, text)


def test_chaves_do_catalogo_sao_unicas() -> None:
    keys = [entry.key for entry in catalog_entries()]

    assert len(keys) == len(set(keys))


@pytest.mark.parametrize(("plugin_id", "cwe", "title"), _PILOT_TYPES)
def test_todo_tipo_dos_relatorios_do_piloto_tem_explicacao_conhecida(
    plugin_id: str, cwe: int | None, title: str
) -> None:
    explained = explain_zap_alert(plugin_id=plugin_id, cwe=cwe, title=title)

    assert explained.known is True


@pytest.mark.parametrize("technique", sorted(TECHNIQUE_LABEL))
def test_toda_tecnica_do_authz_tem_explicacao(technique: str) -> None:
    explained = explain_authz_technique(technique)  # type: ignore[arg-type]  # parametrização

    assert explained.known is True
    assert explained.key == technique


def test_sql_injection_de_regra_desconhecida_cai_pelo_cwe() -> None:
    explained = explain_zap_alert(plugin_id="99999", cwe=89, title="SQL Injection - Novo Banco")

    assert explained.key == "sql_injection"


def test_sql_por_tempo_nao_manda_esconder_mensagem_de_erro_do_banco() -> None:
    by_error = explain_zap_alert(plugin_id="40018", cwe=89, title="SQL Injection")
    by_time = explain_zap_alert(
        plugin_id="40022", cwe=89, title="SQL Injection - PostgreSQL (Time Based)"
    )

    assert by_time.key == "sql_injection_time"
    assert any("erro interna do banco" in step.text for step in by_error.what_to_do)
    assert not any("erro" in step.text for step in by_time.what_to_do)
    assert "demor" in by_time.what_happened


def test_comando_do_sistema_por_tempo_tem_a_propria_explicacao() -> None:
    by_time = explain_zap_alert(
        plugin_id="90020", cwe=78, title="Remote OS Command Injection (Time Based)"
    )

    assert by_time.key == "os_command_injection_time"
    assert by_time.known is True


def test_regra_conhecida_vale_mais_que_o_cwe() -> None:
    # 10021 tem CWE 693 (configuração), mas a regra tem texto próprio.
    explained = explain_zap_alert(plugin_id="10021", cwe=693, title="X")

    assert explained.key == "missing_nosniff"


def test_tipo_desconhecido_recebe_explicacao_generica_e_honesta() -> None:
    explained = explain_zap_alert(plugin_id="777777", cwe=None, title="Alerta Inventado")

    assert explained.known is False
    assert explained.key == GENERIC_KEY
    assert "Alerta Inventado" in explained.what_happened
    assert "não temos explicação simples para este tipo" in explained.what_happened
    assert explained.who == "QA"


def test_explicacao_generica_limpa_e_corta_o_nome_da_regra() -> None:
    hostile = "\x1b[31mnome\x07 " + "x" * 500

    explained = explain_zap_alert(plugin_id="1", cwe=None, title=hostile)

    assert "\x1b" not in explained.title
    assert "\x07" not in explained.title
    assert len(explained.technical_name) < 200


def test_explicacao_generica_nao_ecoa_id_de_regra_estranho() -> None:
    explained = explain_zap_alert(plugin_id="<script>alert(1)</script>", cwe=None, title="x")

    assert "<script>" not in explained.technical_name
    assert "desconhecida" in explained.technical_name


def test_explicacao_generica_tambem_respeita_as_regras_do_desenho() -> None:
    explained = explain_zap_alert(plugin_id="1", cwe=None, title="Qualquer")

    for text in [*_all_texts(explained), explained.technical_name]:
        assert not _FORBIDDEN.search(text)


def test_explain_finding_usa_regra_cwe_e_titulo_do_achado() -> None:
    explained = explain_finding(_finding("6", 22, "Path Traversal"))

    assert explained.key == "path_traversal"


def test_explicar_nao_altera_o_achado() -> None:
    finding = _finding("40018", 89, "SQL Injection")
    before = finding.model_dump()

    explain_finding(finding)

    assert finding.model_dump() == before
    assert finding.proposed_severity == "high"


def test_o_catalogo_nao_ecoa_texto_do_alvo_nas_entradas_conhecidas() -> None:
    first = explain_zap_alert(plugin_id="40018", cwe=89, title="titulo qualquer A")
    second = explain_zap_alert(plugin_id="40018", cwe=89, title="titulo qualquer B")

    assert first == second

"""Avalia provas passivas registradas, sem tráfego nem acesso a sistemas externos.

O módulo reúne as técnicas porque o contrato comum exige preservar os mesmos limites de
redação e de suficiência das provas em todas elas.
"""

import re
from types import MappingProxyType
from urllib.parse import urlsplit

from harness_dast.domain.authz.result import AuthzFinding
from harness_dast.domain.cors import classify_cors
from harness_dast.domain.finding import Finding
from harness_dast.domain.verification import VerificationEntry, VerificationLevel

_PASSIVE = frozenset({"10020", "10021", "10035", "10036", "10038", "10098"})
_NAMES = MappingProxyType(
    {
        "10020": "x-frame-options",
        "10021": "x-content-type-options",
        "10038": "content-security-policy",
    }
)


def _entry(
    fingerprint: str, level: VerificationLevel, reason: str, proof: str
) -> VerificationEntry:
    return VerificationEntry(
        fingerprint=fingerprint,
        level=level,
        reason=reason,
        recipe="recorded_observation",
        attack=proof,
        control="Observação direta da evidência guardada, sem novo pedido de controle.",
    )


def _headers(raw: str, response: bool) -> dict[str, str] | None:
    lines = raw.splitlines()
    if not lines or not re.fullmatch(
        r"HTTP/\d(?:\.\d)? [1-5]\d\d(?: .*)?" if response else r"[A-Z]+ \S+ HTTP/\d(?:\.\d)?",
        lines[0].strip(),
    ):
        return None
    result: dict[str, str] = {}
    for line in lines[1:]:
        if not line.strip():
            break
        name, sep, value = line.partition(":")
        name = name.strip().lower()
        if not sep or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9a-z-]+", name) or name in result:
            return None
        result[name] = value.strip()
    return result


def classify_recorded_finding(finding: Finding) -> VerificationEntry | None:
    """Classifica cabeçalhos registrados; tipos ativos ou alheios retornam None.

    Não envia pedidos nem inclui valores de origem, corpo ou credenciais na saída.
    """
    if finding.plugin_id not in _PASSIVE:
        return None
    evidence = finding.evidence
    headers = (
        _headers(evidence.response_header, True)
        if evidence.available and not evidence.truncated
        else None
    )
    if headers is None:
        return _entry(
            finding.fingerprint,
            "not_verifiable",
            "Cabeçalhos completos e válidos não estão disponíveis.",
            "Observação guardada insuficiente.",
        )
    if finding.plugin_id == "10098":
        return _cors(finding, headers)
    if finding.plugin_id == "10035":
        return _hsts(finding, headers)
    if finding.plugin_id not in _NAMES:
        return _entry(
            finding.fingerprint,
            "not_verifiable",
            "Regra passiva sem interpretação segura implementada.",
            "Cabeçalhos guardados; propriedade não avaliada.",
        )
    return _security_header(finding, headers)


def _hsts(finding: Finding, headers: dict[str, str]) -> VerificationEntry:
    request = finding.evidence.request_header
    parsed = _headers(request, False)
    target = request.splitlines()[0].split()[1] if parsed is not None else ""
    try:
        https = urlsplit(target).scheme == "https" and bool(urlsplit(target).hostname)
    except ValueError:
        https = False
    if not https:
        return _entry(
            finding.fingerprint,
            "not_verifiable",
            "A requisição HTTPS não está comprovada.",
            "Esquema da requisição não comprovado.",
        )
    value = headers.get("strict-transport-security")
    if value is None:
        return _entry(
            finding.fingerprint,
            "reproduced",
            "Resposta HTTPS sem cabeçalho HSTS registrado.",
            "Cabeçalhos da resposta HTTPS examinados; HSTS ausente.",
        )
    if re.search(r"(?:^|;)\s*max-age\s*=\s*[1-9][0-9]*\s*(?:;|$)", value, re.I):
        return _entry(
            finding.fingerprint,
            "likely_false_positive",
            "Resposta HTTPS contém HSTS com max-age positivo.",
            "Cabeçalho HSTS observado; demais diretivas não avaliadas.",
        )
    return _entry(
        finding.fingerprint,
        "inconclusive",
        "HSTS presente sem max-age positivo reconhecível.",
        "Valor de HSTS não demonstrou proteção válida.",
    )


def _cors(finding: Finding, headers: dict[str, str]) -> VerificationEntry:
    request = _headers(finding.evidence.request_header, False)
    origin = request.get("origin") if request else None
    acao = headers.get("access-control-allow-origin")
    acac = headers.get("access-control-allow-credentials")
    if not origin or not _valid_origin(origin) or not acao:
        return _entry(
            finding.fingerprint,
            "not_verifiable",
            "Origin ou Access-Control-Allow-Origin não foi registrado de forma válida.",
            "Observação CORS incompleta.",
        )
    if classify_cors(origin, acao, acac):
        return _entry(
            finding.fingerprint,
            "reproduced",
            "Cabeçalhos registrados mostram política CORS permissiva para a origem enviada.",
            "Origin e política CORS observados; valores omitidos.",
        )
    return _entry(
        finding.fingerprint,
        "inconclusive",
        "A política observada não basta para concluir sobre outras origens.",
        "Origin e política CORS observados; valores omitidos.",
    )


def _valid_origin(origin: str) -> bool:
    try:
        parts = urlsplit(origin)
        return bool(
            parts.scheme in {"http", "https"}
            and parts.hostname
            and parts.port != 0
            and parts.username is None
            and parts.password is None
            and not parts.path
            and not parts.query
            and not parts.fragment
            and not any(char.isspace() for char in origin)
        )
    except ValueError:
        return False


def _security_header(finding: Finding, headers: dict[str, str]) -> VerificationEntry:
    name = _NAMES[finding.plugin_id]
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "text/html":
        return _entry(
            finding.fingerprint,
            "not_verifiable",
            "A resposta registrada não comprova uma interface HTML.",
            "Tipo de conteúdo HTML não comprovado.",
        )
    if name not in headers:
        return _entry(
            finding.fingerprint,
            "reproduced",
            "Resposta HTML registrada não contém o cabeçalho apontado.",
            "Cabeçalhos da resposta HTML examinados; cabeçalho ausente.",
        )
    value = headers[name].strip().lower()
    if finding.plugin_id == "10021" and value == "nosniff":
        return _entry(
            finding.fingerprint,
            "likely_false_positive",
            "A resposta HTML registrada contém X-Content-Type-Options: nosniff.",
            "Proteção específica presente na resposta examinada.",
        )
    if finding.plugin_id == "10020" and value in {"deny", "sameorigin"}:
        return _entry(
            finding.fingerprint,
            "likely_false_positive",
            "A resposta HTML registrada contém proteção X-Frame-Options reconhecida.",
            "Proteção específica presente na resposta examinada.",
        )
    if finding.plugin_id == "10038" and value:
        return _entry(
            finding.fingerprint,
            "inconclusive",
            "CSP presente não comprova que suas diretivas sejam eficazes.",
            "Cabeçalho CSP presente; diretivas não avaliadas.",
        )
    return _entry(
        finding.fingerprint,
        "inconclusive",
        "Cabeçalho presente não demonstra proteção eficaz nem refuta o alerta.",
        "Cabeçalho presente; valor não avaliado.",
    )


def _ok(status: int | None) -> bool:
    return status is not None and 200 <= status < 300


def _authz_proof(f: AuthzFinding) -> tuple[bool, str]:
    technique = f.technique
    both = _ok(f.baseline_status) and _ok(f.observed_status)
    distinct = bool(f.actor_account and f.owner_account and f.actor_account != f.owner_account)
    if technique == "authz_cors":
        return f.method == "GET" and _ok(f.observed_status) and f.fields in (
            ("wildcard",),
            ("reflected_credentials",),
        ), "Receipt tipado de política CORS; cabeçalhos originais não foram guardados."
    if technique == "authz_horizontal":
        return (
            both
            and distinct
            and f.actor_role is not None
            and f.actor_role == f.owner_role
            and "com corpo equivalente para o mesmo pedido." in f.evidence,
            "Comparação entre contas do mesmo papel registrou corpos equivalentes.",
        )
    if technique == "authz_vertical":
        return (
            both
            and distinct
            and bool(f.actor_role and f.owner_role and f.actor_role != f.owner_role)
            and "menor) recebeu" in f.evidence,
            "Receipt registra papel menor na operação atribuída ao papel maior.",
        )
    if technique == "authz_anonymous_access":
        return (
            both and "corpo equivalente ao enviar o mesmo pedido sem credencial" in f.evidence,
            "Comparação registrou corpo equivalente sem credencial.",
        )
    if technique == "authz_tampered_token":
        return (
            both and bool(f.variants) and "equivalente ao do pedido autenticado" in f.evidence,
            "Variantes registradas produziram corpo equivalente ao controle autenticado.",
        )
    return _authz_effect(f)


def _authz_effect(f: AuthzFinding) -> tuple[bool, str]:
    if f.technique == "authz_horizontal_write":
        valid = (
            f.method in {"PUT", "PATCH"}
            and _ok(f.observed_status)
            and len(f.fields) == 1
            and bool(f.fields[0])
            and bool(f.owner_account and f.actor_account and f.actor_account != f.owner_account)
            and bool(f.actor_role and f.actor_role == f.owner_role)
            and "leu o valor de teste no campo depois." in f.evidence
        )
        return valid, "Receipt registra leitura posterior do marcador pela conta dona."
    if f.technique == "authz_mass_assignment":
        readback = (
            "a leitura seguinte do recurso mostrou o valor injetado em:" in f.evidence
            or "a leitura do recurso criado mostrou o valor injetado em:" in f.evidence
        )
        return f.method in {"POST", "PUT", "PATCH"} and _ok(f.observed_status) and bool(
            f.fields and f.fields[0] and f.candidate_source
        ) and readback, "Receipt registra leitura posterior do campo atribuído."
    if f.technique == "authz_excessive_data":
        return f.method == "GET" and _ok(f.observed_status) and bool(
            f.fields and all(f.fields)
        ), "Receipt registra nomes de campos fora do esquema; valores não foram guardados."
    if f.technique == "authz_access_matrix":
        valid = (
            f.method in {"GET", "POST", "PUT", "PATCH"}
            and _ok(f.observed_status)
            and bool(f.actor_role and f.fields == (f.actor_role,))
            and "tabela authz.access_matrix proíbe" in f.evidence
        )
        return (
            valid,
            "Receipt registra sucesso para papel proibido; efeito da escrita não foi provado.",
        )
    return False, "Técnica sem prova registrada suportada."


def classify_authz_confirmation(finding: AuthzFinding) -> VerificationEntry:
    """Classifica receipt de autorização sem repetir pedidos ou alterar o achado.

    Uma escrita só comprova alteração quando o receipt registra leitura posterior.
    """
    valid, proof = _authz_proof(finding)
    if valid:
        return _entry(
            finding.fingerprint,
            "reproduced",
            "A propriedade descrita foi observada na execução anterior; não houve nova requisição.",
            proof,
        )
    reason = "Receipt incompleto ou inconsistente para demonstrar o efeito desta técnica."
    if finding.technique in {"authz_horizontal_write", "authz_mass_assignment"}:
        reason = "Escrita sem leitura posterior ou contexto suficiente não prova efeito."
    return _entry(
        finding.fingerprint,
        "not_verifiable",
        reason,
        "Comparação guardada insuficiente; nenhum pedido foi enviado.",
    )

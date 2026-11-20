"""Modelo de achado da CLI, independente do formato do ZAP, e o fingerprint dele.

O fingerprint identifica o MESMO achado entre execuções (para comparar releases). Ele é um
SHA-256 sobre: produto, método HTTP e modelo de caminho da requisição APRENDIDA (resolvida
por `sourceMessageId`, nunca a URL atacada), vetor de entrada, parâmetro, regra do ZAP
(`pluginId` e `alertRef`) e CWE. Fora dele, de propósito: carga (`attack`), host, ids concretos,
`messageId`, severidade e confiança. Mudar qualquer ingrediente ou a normalização invalida o
histórico: suba `FINGERPRINT_VERSION` e escreva um ADR. Este módulo é puro.
"""

import hashlib
import re
from typing import Final, Literal

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.zap_alert import Confidence, Severity

FINGERPRINT_VERSION: Final = 1

Attribution = Literal["source_message", "scan", "url_match", "unresolved"]
Comparison = Literal["new", "persistent"]

_PLACEHOLDER = re.compile(r"\{[^{}/]*\}")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_HEX_ID = re.compile(r"^[0-9a-fA-F]{12,}$")
_LONG_ID = 20
_PUNCTUATED_NUMBER = re.compile(r"^(?=(?:\D*\d){6})[\d.\-_:]+$")
"""Número com pontuação (CPF, CNPJ, data, telefone): só dígitos e `.-_:`, com 6 dígitos ou mais."""


def normalize_path_template(path: str) -> str:
    """Forma canônica de um modelo de caminho do OpenAPI.

    Sem consulta nem fragmento, sem barras repetidas ou final, e com todo `{nome}` trocado por
    `{}` (renomear um parâmetro no OpenAPI não muda o achado).
    """
    cleaned = path.split("?", 1)[0].split("#", 1)[0]
    segments = [item for item in _PLACEHOLDER.sub("{}", cleaned).split("/") if item]
    return "/" + "/".join(segments)


def generic_template(path: str) -> str:
    """Modelo aproximado de um caminho concreto: segmentos com cara de id viram `{}`.

    Só é usado quando o alerta não pôde ser ligado a uma operação do `probe`.
    """
    segments = []
    for segment in (item for item in path.split("?", 1)[0].split("/") if item):
        looks_like_id = (
            segment.isdigit()
            or bool(_UUID.match(segment))
            or bool(_HEX_ID.match(segment))
            or (len(segment) >= _LONG_ID and any(c.isdigit() for c in segment))
            or "@" in segment
            or bool(_PUNCTUATED_NUMBER.match(segment))
        )
        segments.append("{}" if looks_like_id else segment)
    return normalize_path_template("/" + "/".join(segments))


_SEPARATOR = "\x1f"


def compute_fingerprint(
    *,
    product: str,
    method: str,
    path_template: str,
    input_vector: str,
    parameter: str,
    plugin_id: str,
    alert_ref: str,
    cwe: int | None,
) -> str:
    """Calcula o fingerprint (SHA-256 hexadecimal) da versão `FINGERPRINT_VERSION`."""
    parts = (
        f"hdast-finding-v{FINGERPRINT_VERSION}",
        product,
        method.upper(),
        normalize_path_template(path_template),
        input_vector.strip().lower(),
        parameter.strip(),
        plugin_id.strip(),
        alert_ref.strip(),
        "" if cwe is None else str(cwe),
    )
    if any(_SEPARATOR in part for part in parts):
        # O separador aparece no dado (vem do ZAP): ("a\x1fb", "c") e ("a", "b\x1fc") colidiriam.
        # Esta forma, com o tamanho de cada parte, é injetiva e começa com \x1e, que a forma
        # simples nunca produz; assim o fingerprint de quem não tem o separador não muda.
        payload = "\x1e" + "".join(f"{len(part)}:{part}" for part in parts)
    else:
        payload = _SEPARATOR.join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Classification(ApiModel):
    """Classe do achado.

    Attributes:
        cwe: CWE informado pelo ZAP.
        wasc: WASC informado pelo ZAP.
        owasp_api_2023: Categoria do OWASP API Top 10 2023, só quando o mapeamento é inequívoco.
    """

    cwe: int | None = None
    wasc: int | None = None
    owasp_api_2023: str | None = None


class FindingEvidence(ApiModel):
    """Evidência da melhor ocorrência, já redigida.

    Attributes:
        message_id: Mensagem do ataque no ZAP.
        attack: Carga enviada (redigida).
        zap_evidence: Trecho que o ZAP aponta como prova (redigido).
        request_header: Cabeçalho da requisição (redigido).
        request_body: Corpo da requisição (redigido, cortado).
        response_header: Cabeçalho da resposta (redigido).
        response_body: Corpo da resposta (redigido, cortado).
        truncated: Se algum campo foi cortado.
        available: `False` quando a mensagem não foi guardada pelo `scan`.
    """

    message_id: int | None = None
    attack: str = ""
    zap_evidence: str = ""
    request_header: str = ""
    request_body: str = ""
    response_header: str = ""
    response_body: str = ""
    truncated: bool = False
    available: bool = True


class TriageNote(ApiModel):
    """Anotação de triagem do agente, anexada ao achado SEM alterá-lo.

    Attributes:
        note: Observação livre (dado do agente, não confiável para o relatório).
        suspected_false_positive: Se o agente suspeita de falso positivo.
        reason: Motivo da suspeita.
    """

    note: str = ""
    suspected_false_positive: bool = False
    reason: str = ""


class Finding(ApiModel):
    """Achado normalizado.

    Attributes:
        finding_id: Identificador curto legível (`F-` e 8 hexadecimais do fingerprint).
        fingerprint: SHA-256 estável entre execuções.
        fingerprint_version: Versão do algoritmo do fingerprint.
        title: Nome do alerta.
        plugin_id: Regra do ZAP.
        alert_ref: Regra com sub-regra.
        classification: CWE, WASC e categoria OWASP.
        proposed_severity: Severidade PROPOSTA pelo ZAP (a CLI nunca a altera).
        proposed_confidence: Confiança PROPOSTA pelo ZAP.
        operation_id: Operação do `probe` de onde o ataque partiu, ou `None`.
        method: Método da requisição aprendida.
        path_template: Modelo de caminho da requisição aprendida.
        attribution: Como o alerta foi ligado à operação.
        input_vector: Onde a entrada foi injetada.
        parameter: Parâmetro atacado.
        occurrences: Alertas do ZAP reunidos neste achado.
        evidence: Evidência da melhor ocorrência.
        description: Descrição padrão do ZAP, em texto simples.
        solution: Solução padrão do ZAP, em texto simples.
        reproduce_curl: `curl` com marcadores no lugar dos segredos, ou `None`.
        technique: Técnica que produziu o achado; aqui sempre `zap_active_scan`. Os achados
            de autorização entre contas ficam em `FindingsReport.authz` (ADR 0027).
        status: Sempre `needs_triage`: a CLI não decide se é verdadeiro.
        comparison: `new` ou `persistent` com `--compare`; `None` sem comparação.
        triage: Anotação do agente, se houver.
        seed_outcome: Classe do `probe` da operação quando ela NÃO foi `success` e mesmo assim foi
            atacada (ADR 0050); `None` nas demais. Fica FORA do fingerprint: o mesmo achado vindo
            de uma semente `not_found` e de uma `success` é o mesmo achado.
        experimental: `True` quando o alerta vem de uma regra alpha ou beta que a imagem do
            harness acrescenta (`domain/experimental_rules.py`, ADR 0103): precisa de mais cuidado
            na triagem. Não muda severidade nem fingerprint.
    """

    finding_id: str
    fingerprint: str
    fingerprint_version: int = FINGERPRINT_VERSION
    title: str
    plugin_id: str
    alert_ref: str
    classification: Classification
    proposed_severity: Severity
    proposed_confidence: Confidence
    operation_id: str | None = None
    method: str
    path_template: str
    attribution: Attribution
    input_vector: str = ""
    parameter: str = ""
    occurrences: int
    evidence: FindingEvidence
    description: str = ""
    solution: str = ""
    reproduce_curl: str | None = None
    technique: Literal["zap_active_scan"] = "zap_active_scan"
    status: Literal["needs_triage"] = "needs_triage"
    comparison: Comparison | None = None
    triage: TriageNote | None = None
    seed_outcome: str | None = None
    experimental: bool = False

"""Resultado do teste negativo de validação de entrada (`negative.json`), ADR 0051.

O achado também é de origem própria.

Os achados daqui NÃO são alertas do ZAP: nascem da reação do servidor a um valor que o contrato
proíbe. A severidade vem do código (`negative_verdict`), nunca do agente. O VALOR enviado nunca
entra nestes modelos: só a classe do caso, o NOME do campo, o limite que o contrato declara e o
código HTTP. Este módulo é puro.
"""

from typing import Final, Literal

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.negative_values import CaseClass
from harness_dast.domain.probe_result import ProbeStatus
from harness_dast.domain.zap_alert import Severity

NEGATIVE_SCHEMA_VERSION: Final = 1
NEGATIVE_FINGERPRINT_VERSION: Final = 1

NegativeTechnique = Literal["input_accepted", "input_server_error"]
Location = Literal["query", "body"]

NEGATIVE_NOTICE: Final = (
    "Achados vêm da reação do servidor a um valor que o contrato (OpenAPI) proíbe, um campo por "
    "pedido (não do ZAP). Severidade proposta pela taxonomia do código; todo achado exige "
    "triagem humana. Contagem zero NÃO prova que a validação é boa: veja 'not_tested' e os "
    "limites declarados."
)

NEGATIVE_LIMITS: Final[tuple[str, ...]] = (
    "Só parâmetro de consulta e campo de primeiro nível de corpo JSON, nas operações que o "
    "probe alcançou (exchanges.json). Caminho, cabeçalho, cookie, formulário, multipart, campo "
    "aninhado, lista, pattern, formato, oneOf e anyOf não são exercitados.",
    "Um valor proibido por pedido, mínimo e conferido contra o esquema; não é fuzzing nem teste "
    "de injeção (isso é do ZAP).",
    "Aceitar pode ser coerção legítima ou parâmetro ignorado, e 5xx pode vir do estado do alvo: "
    "por isso a severidade é baixa em leitura e todo achado é para triagem.",
    "Rejeitar não prova que a validação é a do esquema: um 400 por outro motivo também conta.",
    "Escrita só com negative.allow_writes (da carta), nunca DELETE; PUT e PATCH aceitos são "
    "restaurados sem releitura (melhor esforço) e um POST aceito deixa um recurso criado "
    "(limpe com `hdast cleanup` ou o reset do ambiente).",
    "O orçamento (negative.max_cases_per_operation e negative.max_requests) corta casos: veja "
    "not_tested.",
)


class NegativeFinding(ApiModel):
    """Achado do teste negativo, de origem própria.

    Attributes:
        finding_id: Identificador curto (`N-` e 8 hexadecimais do fingerprint).
        fingerprint: SHA-256 estável entre execuções (produto, técnica, método, modelo de
            caminho, local, campo e classe; fora: status, valor e execução).
        fingerprint_version: Versão do algoritmo do fingerprint.
        origin: Sempre `negative` (distingue dos achados do ZAP e do `authz`).
        technique: `input_accepted` (2xx) ou `input_server_error` (5xx).
        title: Título curto.
        proposed_severity: Severidade decidida pelo código.
        cwe: 20 (aceitou) ou 755 (5xx).
        owasp_api_2023: Categoria proposta do OWASP API Top 10 2023.
        operation_id: Operação.
        method: Método HTTP.
        path_template: Modelo de caminho.
        account: Conta que enviou.
        location: `query` ou `body`.
        field: NOME do campo alterado (nunca o valor).
        case_class: Classe do valor enviado.
        declared: O limite que o OpenAPI declara (vem do contrato, não do alvo).
        observed_status: Código HTTP da reação.
        baseline_status: Código HTTP que o `probe` obteve com o valor válido.
        restored: `True` ou `False` (PUT e PATCH), `None` se não se aplica.
        created: Se um POST pode ter criado um recurso com valor inválido.
        evidence: Frase sem valor do alvo e sem o valor enviado.
        description: O que a falha significa.
        solution: O que fazer a respeito.
        status: Sempre `needs_triage`.
    """

    finding_id: str
    fingerprint: str
    fingerprint_version: int = NEGATIVE_FINGERPRINT_VERSION
    origin: Literal["negative"] = "negative"
    technique: NegativeTechnique
    title: str
    proposed_severity: Severity
    cwe: int
    owasp_api_2023: str
    operation_id: str
    method: str
    path_template: str
    account: str
    location: Location
    field: str
    case_class: CaseClass
    declared: str
    observed_status: int | None = None
    baseline_status: int | None = None
    restored: bool | None = None
    created: bool = False
    evidence: str
    description: str
    solution: str
    status: Literal["needs_triage"] = "needs_triage"


class NegativeNotTested(ApiModel):
    """O que não foi testado, para uma operação (ou para o estágio todo).

    Attributes:
        operation_id: Operação, ou `None` quando vale para o estágio inteiro.
        method: Método HTTP, quando há operação.
        path: Modelo de caminho, quando há operação.
        reason: Motivo estável (`writes_not_authorized`, `budget`, `unconfirmable`,
            `scope_denied`, `possible_unrestored_change`...).
        message: Explicação em português, com o que fazer.
        field: NOME do campo, quando o motivo é de um caso.
        case_class: Classe do caso, quando o motivo é de um caso.
    """

    operation_id: str | None = None
    method: str | None = None
    path: str | None = None
    reason: str
    message: str
    field: str | None = None
    case_class: CaseClass | None = None


class ClassSummary(ApiModel):
    """Totais de uma classe de caso.

    Attributes:
        case_class: Classe.
        planned: Casos planejados.
        sent: Casos enviados.
        rejected: Rejeitados pelo servidor (o esperado).
        accepted: Aceitos (achado).
        server_error: Respondidos com 5xx (achado).
        inconclusive: Sem conclusão (401, 403, 404, 409, 429, 3xx, sem resposta...).
    """

    case_class: CaseClass
    planned: int = 0
    sent: int = 0
    rejected: int = 0
    accepted: int = 0
    server_error: int = 0
    inconclusive: int = 0


class OperationSummary(ApiModel):
    """Totais de uma operação testada (a seção do relatório lê daqui).

    Attributes:
        operation_id: Operação.
        method: Método HTTP.
        path: Modelo de caminho.
        sent: Casos enviados.
        rejected: Rejeitados pelo servidor (o esperado).
        accepted: Aceitos.
        server_error: Respondidos com 5xx.
        inconclusive: Sem conclusão.
    """

    operation_id: str
    method: str
    path: str
    sent: int = 0
    rejected: int = 0
    accepted: int = 0
    server_error: int = 0
    inconclusive: int = 0


class PlannedCase(ApiModel):
    """Caso planejado, para a simulação: o que seria enviado, sem o valor.

    Attributes:
        operation_id: Operação.
        method: Método HTTP.
        path: Modelo de caminho.
        location: `query` ou `body`.
        field: NOME do campo.
        case_class: Classe.
        declared: Limite declarado no OpenAPI.
    """

    operation_id: str
    method: str
    path: str
    location: Location
    field: str
    case_class: CaseClass
    declared: str


class NegativeResult(ApiModel):
    """`negative.json`: resultado completo do teste negativo.

    Attributes:
        schema_version: Versão do formato.
        run_id: Execução do `probe` usada.
        product: Produto.
        dry_run: Se nada foi enviado (só o plano).
        status: `completed` ou o motivo da parada antecipada.
        stop_message: Explicação da parada.
        started_at: Início (ISO 8601).
        finished_at: Fim (ISO 8601).
        requests_sent: Requisições enviadas pelo estágio (casos e restaurações).
        accounts: Apelidos das contas usadas.
        created_resources: Recursos que um `POST` aceito pode ter deixado no alvo.
        restored_resources: PUT e PATCH restaurados com sucesso.
        by_class: Uma linha por classe, na ordem de prioridade.
        operations: Uma linha por operação com casos enviados.
        operations_tested: Operações com ao menos um caso enviado.
        plan: Casos planejados (só na simulação), sem valor.
        findings: Achados.
        not_tested: O que não foi testado e por quê.
        limits: Limites conhecidos do estágio (afirmações fixas).
        notice: Aviso fixo.
    """

    schema_version: int = NEGATIVE_SCHEMA_VERSION
    run_id: str
    product: str
    dry_run: bool = False
    status: ProbeStatus
    stop_message: str | None = None
    started_at: str
    finished_at: str
    requests_sent: int = 0
    accounts: tuple[str, ...] = ()
    created_resources: int = 0
    restored_resources: int = 0
    by_class: tuple[ClassSummary, ...] = ()
    operations: tuple[OperationSummary, ...] = ()
    operations_tested: int = 0
    plan: tuple[PlannedCase, ...] = ()
    findings: tuple[NegativeFinding, ...] = ()
    not_tested: tuple[NegativeNotTested, ...] = ()
    limits: tuple[str, ...] = NEGATIVE_LIMITS
    notice: str = NEGATIVE_NOTICE

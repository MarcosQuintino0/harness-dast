"""Resultado do teste de autorização entre contas (`authz.json`) e o achado de origem própria.

Os achados daqui NÃO são alertas do ZAP: nascem de uma comparação determinística entre contas e
levam a técnica que os produziu. A severidade vem do código (`authz_findings`), nunca do agente.
Nenhum valor de campo do alvo entra nestes modelos: só nomes, caminhos, códigos HTTP e apelidos
de conta. Este módulo é puro.
"""

from typing import Final, Literal

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.authz_config import AuthzCheck
from harness_dast.domain.authz_fields import CandidateSource
from harness_dast.domain.authz_matrix_report import AccessMatrixReport
from harness_dast.domain.authz_token import TamperVariant
from harness_dast.domain.probe_result import ProbeStatus
from harness_dast.domain.zap_alert import Severity

AUTHZ_SCHEMA_VERSION: Final = 1
AUTHZ_FINGERPRINT_VERSION: Final = 1

AuthzTechnique = Literal[
    "authz_cors",
    "authz_horizontal",
    "authz_vertical",
    "authz_excessive_data",
    "authz_mass_assignment",
    "authz_anonymous_access",
    "authz_tampered_token",
    "authz_horizontal_write",
    "authz_access_matrix",
]
CheckStatus = Literal["completed", "partial", "skipped", "disabled"]

AUTHZ_NOTICE: Final = (
    "Achados de autorização vêm de comparação determinística entre contas (não do ZAP). "
    "Severidade proposta pela taxonomia do código; todo achado exige triagem humana. Contagem "
    "zero NÃO prova que a API é segura: veja 'not_tested' e os limites declarados."
)

AUTHZ_LIMITS: Final[tuple[str, ...]] = (
    "CORS amostra somente GETs provados, com uma origem sob .invalid e uma tentativa por "
    "operação, até cors_max_requests; não cobre preflight, outras origens ou todas as operações.",
    "Par horizontal automático exige escrita autorizada, duas contas de papel não "
    "compartilhado, POST e GET irmão provados, HTTP 201 com sucesso lógico e identificador "
    "devolvido que não apareceu nas leituras anteriores; criação com HTTP 200 é inconclusiva. "
    "O teto de 400 escritas é compartilhado com atribuição em massa, "
    "com uma tentativa por escrita.",
    "BOLA em leituras (GET) com identificador no caminho ou na consulta; escritas só com "
    "allow_writes (PUT e PATCH, um campo por pedido, nunca DELETE); identificador no corpo não "
    "é testado.",
    "Exposição excessiva só em respostas de GET; respostas de POST, PUT e PATCH não são "
    "comparadas com o esquema.",
    "additionalProperties do OpenAPI não é modelado: objeto sem properties no esquema é tratado "
    "como livre.",
    "BFLA só em operações atribuídas por regra explícita de auth.account_map e nos métodos de "
    "authz.vertical_methods; exige authz.role_order.",
    "Atribuição em massa: os campos de authz.mass_assignment_fields mais, por operação, até "
    "authz.max_derived_candidates campos tirados do OpenAPI, um por pedido; só campos escalares "
    "de primeiro nível, e dono do recurso (ownerId, tenantId) só se declarado. Num POST, cada "
    "campo testado deixa um recurso criado no alvo (limpe com `hdast cleanup` ou o reset do "
    "ambiente); valores únicos não são gerados de novo (409 vira create_conflict).",
    "Operações que o probe não alcançou com sucesso não são repetidas.",
    "Pedido sem login e token adulterado só em GET; autenticação só por cookie de sessão não é "
    "modelada, então 'sem achado' no pedido sem login não prova segurança.",
    "Tabela quem pode o quê (authz.access_matrix): só proibições são testadas, um pedido por "
    "papel proibido e por operação, com a primeira conta do papel; só 401 e 403 provam a "
    "negação (404 e 400 são 'não testado'); papel fora da tabela não é testado nem presumido "
    "proibido; POST e PUT e PATCH só com allow_writes e DELETE nunca; um POST aceito deixa um "
    "recurso criado no alvo.",
    "Token adulterado: só JWT (remover assinatura, alg none, uma reivindicação a mais) e texto "
    "embaralhado; nunca se forja assinatura nem se troca identidade. 2xx com corpo diferente não "
    "é achado.",
)


class AuthzFinding(ApiModel):
    """Achado de autorização, de origem própria.

    Attributes:
        finding_id: Identificador curto (`A-` e 8 hexadecimais do fingerprint).
        fingerprint: SHA-256 estável entre execuções (técnica, produto, método, caminho, campos).
        fingerprint_version: Versão do algoritmo do fingerprint.
        origin: Sempre `authz` (distingue dos achados do ZAP).
        technique: Técnica que produziu o achado.
        title: Título curto.
        proposed_severity: Severidade decidida pelo código.
        cwe: CWE da técnica.
        owasp_api_2023: Categoria do OWASP API Top 10 2023 da técnica.
        operation_id: Operação repetida.
        method: Método HTTP.
        path_template: Modelo de caminho.
        actor_account: Conta que fez a repetição (ou a conta testada, em dado a mais e atribuição).
        actor_role: Papel dessa conta.
        owner_account: Conta dona da linha de base (horizontal e vertical), ou `None`.
        owner_role: Papel da conta dona, ou `None`.
        baseline_status: Código HTTP da linha de base, quando existe.
        observed_status: Código HTTP observado na repetição.
        fields: Caminhos de campo envolvidos (dado a mais; atribuição em massa; campo do
            marcador da escrita em outra conta) e `query:<nome>` do BOLA com identificador de
            consulta. Só nomes.
        candidate_source: De onde veio o campo testado (atribuição em massa), ou `None`. Fora
            do fingerprint.
        variants: Variantes de token aceitas pelo servidor (token adulterado). Só nomes: o
            valor de um token nunca é gravado. Fora do fingerprint.
        evidence: Frase que descreve o que foi observado, sem valores do alvo.
        description: O que a falha significa.
        solution: O que fazer a respeito.
        status: Sempre `needs_triage`.
    """

    finding_id: str
    fingerprint: str
    fingerprint_version: int = AUTHZ_FINGERPRINT_VERSION
    origin: Literal["authz"] = "authz"
    technique: AuthzTechnique
    title: str
    proposed_severity: Severity
    cwe: int
    owasp_api_2023: str
    operation_id: str
    method: str
    path_template: str
    actor_account: str
    actor_role: str | None = None
    owner_account: str | None = None
    owner_role: str | None = None
    baseline_status: int | None = None
    observed_status: int | None = None
    fields: tuple[str, ...] = ()
    variants: tuple[TamperVariant, ...] = ()
    candidate_source: CandidateSource | None = None
    evidence: str
    description: str
    solution: str
    status: Literal["needs_triage"] = "needs_triage"


class AuthzNotTested(ApiModel):
    """Verificação que não pôde ser feita para uma operação (ou para a execução toda).

    Attributes:
        check: Verificação.
        operation_id: Operação, ou `None` quando vale para a verificação inteira.
        method: Método HTTP, quando há operação.
        path: Modelo de caminho, quando há operação.
        reason: Motivo estável (`no_peer_account`, `public_operation`, `no_role_order`...).
        message: Explicação em português, com o que fazer.
    """

    check: AuthzCheck
    operation_id: str | None = None
    method: str | None = None
    path: str | None = None
    reason: str
    message: str


class CheckSummary(ApiModel):
    """Totais de uma verificação.

    Attributes:
        check: Verificação.
        status: `completed`, `partial` (parou no meio), `skipped` (nada pôde ser testado) ou
            `disabled` (desligada ou não pedida).
        candidates: Operações candidatas.
        tested: Operações em que houve comparação conclusiva.
        findings: Achados da verificação.
        message: Observação, quando há.
    """

    check: AuthzCheck
    status: CheckStatus
    candidates: int = 0
    tested: int = 0
    findings: int = 0
    message: str | None = None


class AuthzResult(ApiModel):
    """`authz.json`: resultado completo do teste de autorização entre contas.

    Attributes:
        schema_version: Versão do formato.
        run_id: Execução do `probe` usada.
        product: Produto.
        dry_run: Se nada foi enviado (só o plano).
        status: `completed` ou o motivo da parada antecipada.
        stop_message: Explicação da parada.
        started_at: Início (ISO 8601).
        finished_at: Fim (ISO 8601).
        requests_sent: Requisições enviadas pelo estágio.
        created_resources: Recursos que um `POST` de teste deixou no alvo (atribuição em massa;
            o `DELETE` é proibido, então quem limpa é o `cleanup` ou o reset do ambiente).
        accounts: Apelidos das contas usadas.
        access_matrix: A tabela "quem pode o quê" com o resultado de cada célula (ADR 0041), ou
            `None` quando o perfil não declara `authz.access_matrix` ou foi uma simulação.
        checks: Uma linha por verificação, na ordem fixa.
        findings: Achados de autorização.
        not_tested: O que não foi testado e por quê.
        limits: Limites conhecidos do estágio (afirmações fixas).
        notice: Aviso fixo.
    """

    schema_version: int = AUTHZ_SCHEMA_VERSION
    run_id: str
    product: str
    dry_run: bool = False
    status: ProbeStatus
    stop_message: str | None = None
    started_at: str
    finished_at: str
    requests_sent: int = 0
    created_resources: int = 0
    accounts: tuple[str, ...] = ()
    access_matrix: AccessMatrixReport | None = None
    checks: tuple[CheckSummary, ...] = ()
    findings: tuple[AuthzFinding, ...] = ()
    not_tested: tuple[AuthzNotTested, ...] = ()
    limits: tuple[str, ...] = AUTHZ_LIMITS
    notice: str = AUTHZ_NOTICE

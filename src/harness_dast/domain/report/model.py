"""Modelo do relatório de achados (`findings.json`) e as afirmações fixas de honestidade.

`findings.json` é contrato público (schema versionado, `docs/referencia/finding-schema.md`).
Toda execução leva, no próprio arquivo, o que ela NÃO testou: a ausência de achados não prova
segurança. Este módulo é puro.
"""

from typing import Final

from pydantic import Field

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.finding import FINGERPRINT_VERSION, Finding
from harness_dast.domain.finding_group import FindingGroup
from harness_dast.domain.internal_error_signals import InternalErrorSignals
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.scan_result import AppliedLimits, AppliedPolicy, RuleCoverageGap
from harness_dast.domain.signal_result import ProxySignals
from harness_dast.domain.traffic import TrafficSummary

REPORT_SCHEMA_VERSION: Final = 1

NOT_TESTED_STATEMENTS: Final[tuple[str, ...]] = (
    "Falhas de autorização (BOLA/IDOR, BFLA, troca de dados de outro usuário) exigem comparar "
    "respostas de contas diferentes; uma varredura ativa do ZAP não as detecta.",
    "Atribuição em massa (mass assignment), exposição excessiva de dados em respostas "
    "legítimas e falhas de lógica de negócio estão fora do que o ZAP detecta.",
    "Só foram varridas as operações que o probe alcançou com sucesso e que o plano permitiu "
    "(sem DELETE, sem o login, sem caminhos negados); as demais constam como não testadas.",
    "Varreduras cortadas pelo tempo ou paradas antes do fim cobrem só parte dos ataques; a "
    "lista de varreduras truncadas está neste relatório.",
    "Severidade e confiança são PROPOSTAS pelo ZAP, não confirmadas: todo achado exige "
    "triagem humana (status needs_triage).",
    "Um relatório sem achados NÃO é evidência de que a API é segura: significa apenas que "
    "estas regras não encontraram problema nestas requisições, com estes limites.",
)

NOT_TESTED_WITH_AUTHZ: Final[tuple[str, ...]] = (
    "O ZAP não detecta falhas de autorização nem de lógica de negócio. Nesta execução o "
    "estágio authz (técnica própria, determinística) comparou contas; o que ele cobriu e o que "
    "não pôde testar está na seção 'Autorização entre contas' e em 'authz'.",
    "O estágio authz cobre BOLA em leituras com identificador, BFLA nos métodos liberados, "
    "campos fora do esquema em respostas de GET e atribuição em massa com a lista de campos do "
    "perfil; falhas de lógica de negócio além disso continuam sem teste.",
    *NOT_TESTED_STATEMENTS[2:],
)
"""Afirmações quando o estágio de autorização rodou: no lugar das duas primeiras do ZAP."""

NOT_TESTED_NEGATIVE: Final[str] = (
    "O estágio negative (ADR 0051) mexeu só em parâmetro de consulta e em campo de primeiro "
    "nível de corpo JSON, um valor proibido por pedido, nas operações que o probe alcançou; "
    "caminho, cabeçalho, formulário, multipart, campo aninhado, pattern e formato não foram "
    "exercitados, e o orçamento do estágio cortou o que está em 'not_tested' de 'negative'."
)
"""Afirmação acrescentada quando o estágio `negative` rodou: onde ele mexeu e onde não."""


class NotTested(ApiModel):
    """Operação sem varredura nesta execução.

    Attributes:
        operation_id: Operação.
        method: Método HTTP.
        path: Modelo de caminho.
        reason: Motivo estável (`delete`, `login`, `mutating`, `probe_validation_error`...).
        message: Explicação em português.
        probe_outcome: Resultado do último probe, ou `None` em relatórios antigos.
    """

    operation_id: str
    method: str
    path: str
    reason: str
    message: str
    probe_outcome: str | None = None


class TruncatedScan(ApiModel):
    """Varredura que não cobriu todos os ataques.

    Attributes:
        operation_id: Operação.
        outcome: `truncated` (corte do ZAP) ou `stopped` (parada nossa).
        progress: Percentual alcançado.
    """

    operation_id: str
    outcome: str
    progress: int


class SeededScan(ApiModel):
    """Operação varrida a partir de uma resposta do `probe` que não foi sucesso (ADR 0050).

    Attributes:
        operation_id: Operação.
        method: Método HTTP.
        path: Modelo de caminho.
        seed_outcome: Classe do `probe` (`not_found`, `validation_error`...).
        probe_status: Código HTTP que o `probe` viu, ou `None`.
    """

    operation_id: str
    method: str
    path: str
    seed_outcome: str
    probe_status: int | None = None


class Coverage(ApiModel):
    """O que a execução cobriu.

    Attributes:
        operations_total: Operações do OpenAPI.
        operations_sent: Operações que o probe tentou.
        probe_successes: Operações com sucesso no probe.
        probe_reached: Operações alcançadas, incluindo recusa esperada de login; `None` em legado.
        reachability: Alcançadas sobre tentadas (ou `None`).
        reachability_all: Alcançadas sobre todas (ou `None`).
        partial: Se há lacunas elegíveis ou etapas incompletas.
        probe_status: Estado final do probe.
        scan_status: Estado final do scan.
        scan_stop_message: Explicação da parada do scan.
        scans_run: Varreduras executadas.
        rule_coverage_gaps: Lacunas por regra, ou `None` quando indisponíveis.
        oast_gap: Motivo de retorno OAST não verificável, quando houver.
        truncated_scans: Varreduras truncadas ou paradas.
        not_tested: Operações sem varredura, com o motivo.
        include_outcomes: Classes além de `success` que o `scan` aplicou (`scan.include_outcomes`,
            ADR 0050); vazio em `scan.json` anterior.
        seeded_scans: Operações varridas a partir de uma resposta que não foi sucesso (ADR 0050).
            Não mudam `reachability`, `reachability_all` nem `probe_successes`: incluir uma classe
            não faz a operação "alcançada".
        limits: Limites aplicados.
        policy: Política de varredura aplicada.
        traffic: Tráfego visto pelo proxy de escopo durante o scan.
    """

    operations_total: int
    operations_sent: int
    probe_successes: int
    probe_reached: int | None = None
    reachability: float | None
    reachability_all: float | None
    partial: bool = False
    probe_status: str
    scan_status: str
    scan_stop_message: str | None = None
    scans_run: int
    rule_coverage_gaps: tuple[RuleCoverageGap, ...] | None = None
    oast_gap: str | None = None
    truncated_scans: tuple[TruncatedScan, ...] = ()
    not_tested: tuple[NotTested, ...] = ()
    include_outcomes: tuple[str, ...] = ()
    seeded_scans: tuple[SeededScan, ...] = ()
    limits: AppliedLimits
    policy: AppliedPolicy
    traffic: TrafficSummary = Field(default_factory=TrafficSummary)


class FindingsSummary(ApiModel):
    """Totais dos achados.

    Attributes:
        total: Achados.
        by_severity: Contagem pela severidade proposta pelo ZAP.
        occurrences: Alertas do ZAP reunidos nos achados.
        alerts_unreadable: Alertas brutos ilegíveis (ignorados e contados).
        authz_by_severity: Achados do estágio de autorização entre contas por severidade
            (aditivo, ADR 0027); vazio quando o estágio não rodou. NÃO entra em `total` nem em
            `by_severity`, que seguem sendo só do ZAP.
        negative_by_severity: Achados do estágio `negative` (valores que o esquema proíbe) por
            severidade (aditivo, ADR 0051); vazio quando o estágio não rodou. Também NÃO entra
            em `total` nem em `by_severity`.
        signal_by_severity: Achados de sinal de erro interno vistos pela cerca por severidade
            (aditivo, ADR 0049); vazio quando a cerca não leu esta execução. Também NÃO entra em
            `total` nem em `by_severity`.
    """

    total: int
    by_severity: dict[str, int]
    occurrences: int
    alerts_unreadable: int = 0
    authz_by_severity: dict[str, int] = Field(default_factory=dict)
    negative_by_severity: dict[str, int] = Field(default_factory=dict)
    signal_by_severity: dict[str, int] = Field(default_factory=dict)


class GoneFinding(ApiModel):
    """Achado da execução anterior que NÃO foi observado nesta.

    "Não observado" não é "corrigido": a operação pode não ter sido varrida agora.

    Attributes:
        fingerprint: Fingerprint.
        finding_id: Identificador curto.
        title: Nome.
        proposed_severity: Severidade proposta na execução anterior.
        method: Método.
        path_template: Modelo de caminho.
        operation_scanned_now: Se a operação foi varrida nesta execução.
    """

    fingerprint: str
    finding_id: str
    title: str
    proposed_severity: str
    method: str
    path_template: str
    operation_scanned_now: bool


class ComparisonInfo(ApiModel):
    """Comparação com outra execução.

    Attributes:
        baseline_run_id: Execução usada como base.
        new: Achados novos.
        persistent: Achados presentes nas duas.
        not_observed: Achados da base não observados agora.
        notice: Aviso sobre o significado de "não observado".
    """

    baseline_run_id: str
    new: int
    persistent: int
    not_observed: int
    notice: str


class FindingsReport(ApiModel):
    """`findings.json`.

    Attributes:
        internal_error_signals: Sinais passivos nas evidências, ou `None` em relatório anterior.
        schema_version: Versão do formato (1).
        fingerprint_version: Versão do algoritmo do fingerprint.
        run_id: Execução.
        product: Produto.
        generated_at: Instante da geração (ISO 8601).
        harness_version: Versão do harness.
        coverage: Cobertura e limites.
        not_tested_statements: Afirmações fixas sobre o que não foi testado.
        summary: Totais.
        findings: Achados (todos, sem agrupar).
        groups: Visão agrupada pela causa provável; cada achado está em exatamente um grupo
            (aditivo, ADR 0029).
        not_observed: Achados da base não observados (só com `--compare`).
        comparison: Resumo da comparação, ou `None`.
        triage_orphans: Fingerprints da triagem que não existem.
        authz: Resultado do estágio de autorização entre contas (ADR 0027), com os achados de
            origem própria e a técnica de cada um; `None` quando o estágio não rodou. Não se
            mistura com `findings` (do ZAP).
        negative: Resultado do estágio de valores que o esquema proíbe (ADR 0051), com os achados
            de origem própria `negative`; `None` quando o estágio não rodou (ou em relatório
            anterior). Não se mistura com `findings` (do ZAP).
        proxy_signals: Sinais de erro interno vistos pela cerca em toda resposta liberada
            (ADR 0049), com os achados de origem própria `proxy`; `None` em relatório anterior.
            Não se soma a `internal_error_signals` (outra fonte) nem se mistura com `findings`.
    """

    internal_error_signals: InternalErrorSignals | None = None
    schema_version: int = REPORT_SCHEMA_VERSION
    fingerprint_version: int = FINGERPRINT_VERSION
    run_id: str
    product: str
    generated_at: str
    harness_version: str
    coverage: Coverage
    not_tested_statements: tuple[str, ...] = NOT_TESTED_STATEMENTS
    summary: FindingsSummary
    findings: tuple[Finding, ...] = ()
    groups: tuple[FindingGroup, ...] = ()
    not_observed: tuple[GoneFinding, ...] = ()
    comparison: ComparisonInfo | None = None
    triage_orphans: tuple[str, ...] = Field(default=())
    authz: AuthzResult | None = None
    proxy_signals: ProxySignals | None = None
    negative: NegativeResult | None = None


class FindingDigest(ApiModel):
    """Resumo de um achado para o envelope JSON (a evidência fica nos arquivos).

    Attributes:
        finding_id: Identificador curto.
        fingerprint: Fingerprint.
        title: Nome do alerta.
        proposed_severity: Severidade proposta pelo ZAP.
        proposed_confidence: Confiança proposta pelo ZAP.
        operation_id: Operação de origem, ou `None`.
        method: Método.
        path_template: Modelo de caminho.
        parameter: Parâmetro atacado.
        occurrences: Ocorrências reunidas.
        cwe: CWE, ou `None`.
        owasp_api_2023: Categoria OWASP, ou `None`.
        comparison: `new`, `persistent` ou `None`.
        suspected_false_positive: Suspeita do agente (consultiva), ou `None` sem triagem.
    """

    finding_id: str
    fingerprint: str
    title: str
    proposed_severity: str
    proposed_confidence: str
    operation_id: str | None
    method: str
    path_template: str
    parameter: str
    occurrences: int
    cwe: int | None
    owasp_api_2023: str | None
    comparison: str | None
    suspected_false_positive: bool | None


class ReportDigest(ApiModel):
    """`data` do envelope de `hdast report`.

    Attributes:
        internal_error_signals: Sinais passivos nas evidências, ou `None` em relatório anterior.
        run_id: Execução.
        product: Produto.
        files: Arquivos gerados na pasta da execução.
        threshold: Limiar de severidade aplicado (`none` = sem gate).
        exceeds_threshold: Se há achado no limiar ou acima (saída 1).
        summary: Totais.
        coverage: Cobertura, limites e o que não foi testado.
        not_tested_statements: Afirmações fixas de honestidade.
        findings: Resumo dos achados.
        groups: Grupos de achados com a mesma causa provável.
        not_observed: Achados da base não observados (com `--compare`).
        comparison: Resumo da comparação.
        triage_orphans: Fingerprints de triagem sem achado.
        authz: Resultado do estágio de autorização entre contas, ou `None` se não rodou.
        proxy_signals: Sinais de erro interno vistos pela cerca, ou `None` em relatório anterior.
        negative: Resultado do estágio de valores que o esquema proíbe, ou `None` se não rodou.
    """

    internal_error_signals: InternalErrorSignals | None = None
    run_id: str
    product: str
    files: tuple[str, ...]
    threshold: str
    exceeds_threshold: bool
    summary: FindingsSummary
    coverage: Coverage
    not_tested_statements: tuple[str, ...]
    findings: tuple[FindingDigest, ...]
    groups: tuple[FindingGroup, ...]
    not_observed: tuple[GoneFinding, ...]
    comparison: ComparisonInfo | None
    triage_orphans: tuple[str, ...]
    authz: AuthzResult | None = None
    proxy_signals: ProxySignals | None = None
    negative: NegativeResult | None = None


def build_digest(
    report: FindingsReport, files: tuple[str, ...], threshold: str, *, exceeds: bool
) -> ReportDigest:
    """Resume o relatório para o envelope JSON."""
    return ReportDigest(
        run_id=report.run_id,
        product=report.product,
        files=files,
        threshold=threshold,
        exceeds_threshold=exceeds,
        summary=report.summary,
        coverage=report.coverage,
        not_tested_statements=report.not_tested_statements,
        findings=tuple(
            FindingDigest(
                finding_id=item.finding_id,
                fingerprint=item.fingerprint,
                title=item.title,
                proposed_severity=item.proposed_severity,
                proposed_confidence=item.proposed_confidence,
                operation_id=item.operation_id,
                method=item.method,
                path_template=item.path_template,
                parameter=item.parameter,
                occurrences=item.occurrences,
                cwe=item.classification.cwe,
                owasp_api_2023=item.classification.owasp_api_2023,
                comparison=item.comparison,
                suspected_false_positive=(
                    item.triage.suspected_false_positive if item.triage else None
                ),
            )
            for item in report.findings
        ),
        groups=report.groups,
        not_observed=report.not_observed,
        comparison=report.comparison,
        triage_orphans=report.triage_orphans,
        authz=report.authz,
        internal_error_signals=report.internal_error_signals,
        proxy_signals=report.proxy_signals,
        negative=report.negative,
    )

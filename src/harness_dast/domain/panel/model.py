"""Modelo de visão do painel da execução: tudo que as sete abas precisam de UM teste. Módulo puro.

O painel (`docs/design/execution-panel/`) é um conjunto de páginas estáticas que a CLI gera para
quem não domina segurança. Este módulo só descreve os dados; `panel_build` os monta a partir dos
arquivos da execução e `panel_pages` os transforma em HTML. As regras:

- Dado ausente é `None` (ou lista vazia onde "nenhum" é uma resposta), nunca zero inventado: a
  tela mostra o traço e a explicação ("— não medido").
- Texto que vem do alvo, do OpenAPI, do ZAP, do agente ou de arquivo continua CRU aqui; quem
  escreve HTML o passa por `html_safe`. Texto nosso já vem em português simples.
- Ganchos `commands` (diário de comandos) e `explanations` (catálogo de explicação de falha)
  entram por parâmetro, já prontos: o modelo não sabe de onde vêm, e podem vir vazios.
- Nada aqui altera severidade nem apaga achado, e nada diz "seguro" ou "aprovado".
"""

from datetime import date, datetime
from typing import Final, Literal

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.finding import FindingEvidence
from harness_dast.domain.manual_repro import ManualRepro
from harness_dast.domain.panel.format import FunctionStateKind, RunStateKind
from harness_dast.domain.report_model import NotTested
from harness_dast.domain.rule_stats import RuleTotal
from harness_dast.domain.run_metrics import DisabledRuleMetric, OperationMetric
from harness_dast.domain.traffic import TrafficGaps, TrafficSummary

PANEL_DIR: Final = "panel"
"""Pasta, dentro de `runs/<run_id>/`, onde as páginas são gravadas."""

StageKey = Literal["preflight", "probe", "scan", "authz", "negative", "report"]
StageState = Literal["done", "cut", "skipped", "pending"]
CommandStatus = Literal["ok", "partial", "error"]
FindingOrigin = Literal["zap", "authz", "negative"]
Owner = Literal["qa", "owner"]


INDEX_FILE: Final = "index.html"
"""Índice de produtos, na pasta das execuções (`runs/`)."""

HISTORY_PREFIX: Final = "history-"


def history_file(product: str) -> str:
    """Nome do histórico de um produto, na pasta das execuções (`history-<slug>.html`)."""
    return f"{HISTORY_PREFIX}{product}.html"


class PanelLinks(ApiModel):
    """Para onde os dois primeiros pedaços do caminho (`hdast / Produto`) levam.

    `None` quer dizer que a página de destino não existe: o pedaço sai como texto, nunca como
    link quebrado. Os links são relativos à pasta `runs/<run_id>/panel/`.
    """

    products: str | None = None
    product: str | None = None


def panel_links(product: str) -> PanelLinks:
    """Links das páginas de um teste para os índices (`runs/index.html` e o histórico).

    Quem grava o painel também regrava os índices, então os dois arquivos existem quando a
    página é aberta (e o `hdast panel --index` os refaz a qualquer hora).
    """
    return PanelLinks(products=f"../../{INDEX_FILE}", product=f"../../{history_file(product)}")


class PanelIdentity(ApiModel):
    """Quem é este teste.

    Attributes:
        product: Slug do produto.
        product_name: Nome para mostrar (derivado do slug).
        run_id: Pasta da execução.
        started_at: Início, no fuso do computador que gerou o painel, ou `None`.
        finished_at: Fim, ou `None` se não há fim conhecido.
        duration_seconds: Do começo ao fim, ou `None`.
        fence_mode: Modo de leitura do caminho da cerca (`strict` ou `wide`), ou `None`.
        authorization_reference: Referência da carta de autorização (texto do perfil), ou `None`.
        authorization_valid_until: Último dia de validade da carta, ou `None` sem perfil.
        zap_version: Versão do ZAP que fez a varredura, ou `None`.
        harness_version: Versão do `hdast` que gravou a execução, ou `None`.
    """

    product: str
    product_name: str
    run_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    fence_mode: str | None = None
    authorization_reference: str | None = None
    authorization_valid_until: date | None = None
    zap_version: str | None = None
    harness_version: str | None = None


class PanelVerdict(ApiModel):
    """Como o teste terminou (nunca "seguro" nem "aprovado").

    Attributes:
        kind: `finished` (terminou), `partial` (parou no meio) ou `error` (não chegou a testar).
        stopped_stage: Etapa em que parou ou falhou, quando `partial` ou `error`.
        reason: Motivo, em texto da CLI (mensagem da etapa ou da parada), ou `None`.
        stop_requested: Se a trava de emergência (`hdast stop`) estava acionada.
        severe_count: Falhas graves (ZAP e autorização entre contas), ou `None` sem relatório.
        strong_count: Falhas graves com prova forte, ou `None` sem relatório.
        to_confirm_count: Falhas graves a confirmar, ou `None` sem relatório.
        functions_total: Funções do OpenAPI, ou `None` se ninguém as contou.
        functions_attempted: Funções que o alcance tentou, ou `None` sem `probe.json`.
        functions_planned: Funções que a varredura planejou atacar (as que responderam no
            alcance e a carta permite), ou `None` sem `scan.json`.
        functions_attacked: Funções que a varredura atacou, ou `None` sem `scan.json`.
    """

    kind: RunStateKind
    stopped_stage: StageKey | None = None
    reason: str | None = None
    stop_requested: bool = False
    severe_count: int | None = None
    strong_count: int | None = None
    to_confirm_count: int | None = None
    functions_total: int | None = None
    functions_attempted: int | None = None
    functions_planned: int | None = None
    functions_attacked: int | None = None


class PanelStage(ApiModel):
    """Uma das cinco etapas.

    Attributes:
        key: Etapa da CLI (`preflight`, `probe`, `scan`, `authz`, `negative`, `report`).
        label: Nome simples da etapa.
        state: `done`, `cut` (parou aqui), `skipped` (pedido pela pessoa) ou `pending` (não chegou).
        seconds: Duração, ou `None` se não foi medida.
        summary: O que aconteceu, em texto nosso com os números.
        message: Mensagem de erro ou de parada (texto da CLI), ou `None`.
        tokens: Tokens do agente nesta etapa, ou `None` (ainda não medido).
        unreached: `True` quando a etapa é `cut` só porque o teste acabou antes dela (não há
            registro de que começou): marca onde parou, sem dizer que rodou.
    """

    key: StageKey
    label: str
    state: StageState
    seconds: float | None = None
    summary: str
    message: str | None = None
    tokens: int | None = None
    unreached: bool = False


class PanelFunction(ApiModel):
    """Uma função (operação do OpenAPI) e o que aconteceu com ela.

    Attributes:
        operation_id: Identificador da operação.
        method: Método HTTP em maiúsculas.
        path: Modelo de caminho.
        name: Nome simples: o `summary` do OpenAPI, senão o `operation_id`.
        area: Parte do sistema: a primeira `tag` do OpenAPI, senão "Outras".
        state: `tested`, `severe`, `failed` (tentou e não conseguiu), `forbidden` (fora do
            combinado na carta) ou `not_tried`.
        reason: Por que não foi testada, em texto nosso, ou `None`.
        finding_ids: Achados graves ligados a esta função.
    """

    operation_id: str
    method: str
    path: str
    name: str
    area: str
    state: FunctionStateKind
    reason: str | None = None
    finding_ids: tuple[str, ...] = ()


class PanelAction(ApiModel):
    """Um passo do "o que fazer", com quem o faz.

    Attributes:
        who: Quem faz, como a tela o mostra (`Você (QA)`, `Time de dev`, `Dono do produto`).
        text: O passo, em português simples.
    """

    who: str
    text: str


class PanelExplanation(ApiModel):
    """Explicação simples de uma falha (gancho do catálogo; a chave é o `finding_id`).

    Attributes:
        title: Título que conta o que houve.
        technical_name: Nome técnico, para a etiqueta cinza.
        what_happened: O que aconteceu, em português simples.
        why_it_matters: Por que isso importa, sem exagero e sem promessa.
        what_to_do: O que fazer, em uma frase só (os passos estão em `actions`).
        who: Quem conduz o assunto (`Você (QA)`, `Dono do produto`, `Time de dev`...).
        actions: Os passos do "o que fazer", cada um com quem o faz, na ordem.
    """

    title: str
    technical_name: str | None = None
    what_happened: str = ""
    why_it_matters: str = ""
    what_to_do: str = ""
    who: str = ""
    actions: tuple[PanelAction, ...] = ()


class PanelFinding(ApiModel):
    """Uma falha grave, com a evidência que o `findings.json` já tem.

    Attributes:
        finding_id: Identificador curto (`F-...` ou `A-...`).
        origin: `zap` (varredura), `authz` (teste entre contas) ou `negative` (valores que o
            esquema proíbe).
        title: Nome do alerta ou da técnica.
        severity: Severidade PROPOSTA (nunca alterada).
        confidence: Degrau do medidor: 1 a confirmar, 2 prova forte, 3 confirmada.
        proposed_confidence: Confiança que o ZAP propôs (`low`, `medium`, `high`...), ou `None`
            em falha de autorização (que não passa pelo ZAP).
        method: Método HTTP.
        path_template: Modelo de caminho.
        operation_id: Operação de origem, ou `None`.
        function_name: Nome simples da função, ou `None`.
        parameter: Parâmetro atacado.
        input_vector: Onde a entrada foi injetada.
        occurrences: Alertas reunidos neste achado.
        cwe: CWE, ou `None`.
        owasp: Categoria OWASP API 2023, ou `None`.
        description: Descrição padrão da regra (texto do ZAP).
        solution: Solução padrão da regra (texto do ZAP).
        evidence: Prova gravada (já redigida), ou `None` em falha de autorização.
        authz_evidence: Resumo da prova do teste entre contas, ou `None`.
        negative_evidence: Resumo da prova do teste de valores proibidos, ou `None`.
        reproduce_curl: Comando `curl` com marcadores no lugar dos segredos, ou `None`.
        repro: Dados de "Como reproduzir à mão" (sem segredo, dado pessoal mascarado), ou `None`
            em falha de autorização ou sem evidência gravada.
        comparison: `new` ou `persistent` com `--compare`.
        suspected_false_positive: Suspeita do agente (consultiva), ou `None` sem triagem.
        triage_note: Observação do agente, ou `None`.
        explanation: Explicação do catálogo, quando o gancho a trouxe.
    """

    finding_id: str
    origin: FindingOrigin
    title: str
    severity: str
    confidence: int
    proposed_confidence: str | None = None
    method: str
    path_template: str
    operation_id: str | None = None
    function_name: str | None = None
    parameter: str = ""
    input_vector: str = ""
    occurrences: int = 1
    cwe: int | None = None
    owasp: str | None = None
    description: str = ""
    solution: str = ""
    evidence: FindingEvidence | None = None
    authz_evidence: str | None = None
    negative_evidence: str | None = None
    reproduce_curl: str | None = None
    repro: ManualRepro | None = None
    comparison: str | None = None
    suspected_false_positive: bool | None = None
    triage_note: str | None = None
    explanation: PanelExplanation | None = None


class PanelGroup(ApiModel):
    """Achados com a mesma causa provável (visão agrupada do `findings.json`).

    Attributes:
        group_id: `G-...`.
        title: Título do achado mais bem classificado.
        severity: Severidade proposta.
        findings_count: Achados no grupo.
        occurrences: Alertas do ZAP reunidos.
        cwe: CWE comum, ou `None`.
        locations: Onde aparece, como (método, caminho, id do achado).
        expected_note: Nota fixa quando o padrão costuma ser esperado, ou `None`.
        parameter: Campo ou parâmetro que a regra apontou (`XSRF-TOKEN`): é o que separa dois
            grupos de mesmo título.
    """

    group_id: str
    title: str
    severity: str
    findings_count: int
    occurrences: int
    cwe: int | None = None
    locations: tuple[tuple[str, str, str], ...] = ()
    expected_note: str | None = None
    parameter: str = ""


class FindingCounts(ApiModel):
    """Achados por severidade proposta (ZAP e autorização somados, só para a contagem).

    Attributes:
        high: Graves.
        medium: Médios.
        low: Baixos.
        informational: Informativos.
        unknown: Severidade que a CLI não soube classificar.
        groups: Causas distintas (grupos).
    """

    high: int = 0
    medium: int = 0
    low: int = 0
    informational: int = 0
    unknown: int = 0
    groups: int = 0

    @property
    def total(self) -> int:
        """Todos os achados."""
        return self.high + self.medium + self.low + self.informational + self.unknown


class PanelLeftOut(ApiModel):
    """Algo que o teste NÃO cobriu.

    Attributes:
        kind: `functions` (funções sem ataque), `scan` (varredura cortada), `authz` (teste entre
            contas), `fence` (cobertura parcial pela cerca), `seeded` (funções atacadas a partir de
            um resultado que não era sucesso, ADR 0050) ou `blind` (o que este tipo de teste
            nunca vê).
        text: Frase nossa.
        count: Quantidade, quando faz sentido.
    """

    kind: Literal["functions", "scan", "authz", "negative", "fence", "seeded", "blind"]
    text: str
    count: int | None = None


class PanelStep(ApiModel):
    """Um próximo passo com dono.

    Attributes:
        owner: `qa` ("Você (QA)") ou `owner` ("Dono do produto").
        text: O que fazer, em texto nosso. Nunca amplia escopo, limite, janela ou autorização.
    """

    owner: Owner
    text: str


class PanelTokens(ApiModel):
    """Tokens do agente no teste todo, separados como o arquivo os traz.

    Attributes:
        input: Entrada (sem cache).
        output: Saída.
        cache_written: Entrada gravada no cache.
        cache_read: Entrada relida do cache (não entra na soma de "tokens").
    """

    input: int = 0
    output: int = 0
    cache_written: int = 0
    cache_read: int = 0


class PanelMeasurements(ApiModel):
    """Medição do teste (`metrics.json`); tokens ainda não existem.

    Attributes:
        metrics_available: Se há `metrics.json` (teste antigo não tem).
        operations: Medição por operação varrida.
        rules: Regras do ZAP somadas, da mais lenta para a mais rápida.
        rules_measured: Varreduras com medição por regra.
        rules_unavailable: Varreduras sem a medição.
        gaps: Silêncios longos do tráfego, ou `None` sem auditoria do proxy.
        disabled_rules: Regras que a política do `scan` desligou, com o motivo.
        tokens_total: Tokens do agente no teste todo, ou `None` (sem `agent-metrics.json`).
        tokens_by_stage: Tokens por etapa da CLI (`preflight`, `probe`, `scan`, `report`) e
            `other` (o que o agente fez fora delas), ou `None` sem o arquivo.
        tokens_breakdown: Tokens do teste todo separados, ou `None`.
        agent_model: Modelo do agente que gravou a medição, ou `None`.
    """

    metrics_available: bool = False
    operations: tuple[OperationMetric, ...] = ()
    rules: tuple[RuleTotal, ...] = ()
    rules_measured: int = 0
    rules_unavailable: int = 0
    gaps: TrafficGaps | None = None
    disabled_rules: tuple[DisabledRuleMetric, ...] = ()
    tokens_total: int | None = None
    tokens_by_stage: dict[str, int] | None = None
    tokens_breakdown: PanelTokens | None = None
    agent_model: str | None = None


class PanelCommand(ApiModel):
    """Um comando do agente (gancho do diário de comandos).

    Attributes:
        at: Hora do comando, ou `None`.
        stage: Etapa a que pertence, ou `None`.
        command: Texto do comando, cru.
        translation: Frase que traduz o comando, em português simples.
        status: `ok`, `partial` ou `error`.
        seconds: Duração, ou `None`.
        output: Resposta do comando (texto do alvo ou da CLI, cru), ou vazio.
        tokens: Tokens gastos neste comando, ou `None`.
    """

    at: datetime | None = None
    stage: StageKey | None = None
    command: str
    translation: str = ""
    status: CommandStatus = "ok"
    seconds: float | None = None
    output: str = ""
    tokens: int | None = None


class PanelJournal(ApiModel):
    """Trecho do diário de comandos que pertence a um teste (devolvido pelo gancho `commands`).

    Attributes:
        commands: Comandos do teste, em ordem cronológica.
        skipped_lines: Linhas corrompidas do diário que foram puladas (a aba Terminal as conta).
    """

    commands: tuple[PanelCommand, ...]
    skipped_lines: int = 0


class PanelView(ApiModel):
    """Visão completa de UM teste: o que as sete abas leem.

    Attributes:
        identity: Quem é o teste.
        verdict: Como terminou.
        stages: As cinco etapas, na ordem.
        functions: Todas as funções conhecidas, na ordem do OpenAPI (ou do `probe`).
        coverage_partial: Se há lacunas elegíveis ou etapas incompletas.
        coverage_not_tested: Operações sem varredura e o último resultado do probe.
        traffic: Tráfego da cerca durante a varredura, ou `None` sem `scan.json`.
        traffic_measured: Se havia auditoria do proxy (sem ela, "0 pedidos barrados" seria mentira).
        counts: Achados por severidade, ou `None` sem `findings.json`.
        groups: Achados agrupados por causa.
        severe: Falhas graves com a evidência, da mais forte para a mais fraca.
        left_out: O que ficou de fora.
        next_steps: O que fazer agora.
        measurements: Medição do teste.
        commands: Diário de comandos (gancho), ou `None` quando ninguém o entregou ou o teste
            é anterior ao diário.
        commands_skipped: Linhas corrompidas do diário que foram puladas (0 sem diário).
        links: Para onde o caminho do alto leva.
    """

    identity: PanelIdentity
    verdict: PanelVerdict
    stages: tuple[PanelStage, ...]
    functions: tuple[PanelFunction, ...] = ()
    coverage_partial: bool = False
    coverage_not_tested: tuple[NotTested, ...] = ()
    authz: AuthzResult | None = None
    traffic: TrafficSummary | None = None
    traffic_measured: bool = False
    counts: FindingCounts | None = None
    groups: tuple[PanelGroup, ...] = ()
    severe: tuple[PanelFinding, ...] = ()
    left_out: tuple[PanelLeftOut, ...] = ()
    next_steps: tuple[PanelStep, ...] = ()
    measurements: PanelMeasurements = PanelMeasurements()
    commands: tuple[PanelCommand, ...] | None = None
    commands_skipped: int = 0
    links: PanelLinks = PanelLinks()

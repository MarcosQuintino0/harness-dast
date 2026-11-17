"""Modelos dos índices do painel (produtos e histórico de um produto). Módulo puro.

Um índice lê UMA linha por execução (`RunRow`), montada a partir dos mesmos arquivos do painel.
Execução ilegível ou de versão antiga não derruba o índice: vira linha "sem dados" (estado
`empty`) ou "dados incompletos" (`partial`), sempre visível. Dado ausente é `None`, nunca zero.
"""

from datetime import date, datetime
from typing import Literal

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.panel.format import RunStateKind

RowState = Literal["ok", "partial", "empty"]
RunKind = Literal["scan", "authz", "probe", "preflight", "none"]


class RowFinding(ApiModel):
    """Uma falha grave de uma execução, só o que o histórico precisa para comparar.

    Attributes:
        finding_id: Código curto da falha, que não muda entre testes (vem do fingerprint).
        title: Título (nome da função, quando existe, ou o nome do alerta).
    """

    finding_id: str
    title: str


class RunRow(ApiModel):
    """Uma execução nos índices.

    Attributes:
        run_id: Pasta da execução.
        product: Slug do produto.
        state: `ok`, `partial` (algum arquivo ilegível) ou `empty` (nada legível).
        started_at: Início (ou o carimbo da pasta), no fuso do computador.
        kind: O que rodou, em categoria (`scan` inclui o teste entre contas junto).
        what_ran: O que rodou, em texto nosso, ou `None`.
        verdict: Como terminou, ou `None` sem dados.
        functions_attacked: Funções que a varredura atacou, ou `None`.
        functions_basis: Funções tentadas pelo alcance (ou o total do Swagger), ou `None`.
        functions_total: Funções do Swagger conhecidas pela execução, ou `None`.
        severe_count: Falhas graves, ou `None` sem `findings.json`.
        severe: As falhas graves (código e título).
        duration_seconds: Duração do teste, ou `None`.
        tokens: Tokens do agente, ou `None` (ainda não medido).
        fence_mode: Modo da cerca em que o teste rodou, ou `None`.
        panel_link: Caminho do Resumo do painel, relativo a `runs/`, ou `None` se não existe.
    """

    run_id: str
    product: str
    state: RowState
    started_at: datetime | None = None
    kind: RunKind = "none"
    what_ran: str | None = None
    verdict: RunStateKind | None = None
    functions_attacked: int | None = None
    functions_basis: int | None = None
    functions_total: int | None = None
    severe_count: int | None = None
    severe: tuple[RowFinding, ...] = ()
    duration_seconds: float | None = None
    tokens: int | None = None
    fence_mode: str | None = None
    panel_link: str | None = None


class ProductInfo(ApiModel):
    """O que o perfil do produto diz (para o cartão e o topo do histórico).

    Attributes:
        profile_available: Se o perfil pôde ser lido agora.
        authorization_reference: Referência da carta, ou `None`.
        valid_until: Último dia de validade da carta, ou `None`.
        fence_mode: Modo da cerca do perfil, ou `None`.
    """

    profile_available: bool = False
    authorization_reference: str | None = None
    valid_until: date | None = None
    fence_mode: str | None = None


class ProductEntry(ApiModel):
    """Um produto nos índices.

    Attributes:
        product: Slug.
        name: Nome para mostrar.
        info: Dados do perfil.
        rows: Execuções, da mais recente para a mais antiga.
    """

    product: str
    name: str
    info: ProductInfo
    rows: tuple[RunRow, ...]

"""Modelo da página "Ao vivo" (`live.html`): o que se sabe durante `hdast run`. Módulo puro.

A página é HTML estático, sem JavaScript: a CLI a regrava e ela se recarrega sozinha
(`<meta http-equiv="refresh">`). Por isso mostra o horário da última gravação. Dado que a CLI
ainda não tem (por exemplo, pedidos sem a auditoria do proxy) fica `None` e a tela diz
"não medido", nunca zero.
"""

from datetime import datetime
from typing import Literal

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.panel.format import RunStateKind
from harness_dast.domain.panel.model import PanelLinks, StageKey

LivePhase = Literal["running", "stopping", "finished"]
LiveStageState = Literal["done", "running", "pending", "cut", "skipped"]


class LiveStage(ApiModel):
    """Uma etapa no trilho.

    Attributes:
        key: Etapa da CLI.
        label: Nome simples (o mesmo da aba Etapas).
        state: `done`, `running` (agora), `pending` (a seguir), `cut` (parou aqui) ou `skipped`.
        seconds: Duração (da etapa pronta, ou o tempo até agora da etapa em curso), ou `None`.
    """

    key: StageKey
    label: str
    state: LiveStageState
    seconds: float | None = None


class LiveView(ApiModel):
    """Tudo que a página "Ao vivo" mostra.

    Attributes:
        product: Slug do produto.
        product_name: Nome para mostrar.
        run_id: Pasta da execução.
        phase: `running`, `stopping` (a trava de emergência foi acionada) ou `finished`.
        outcome: Como terminou, quando `finished`.
        reason: Motivo do fim (mensagem da etapa que parou), ou `None`.
        started_at: Início do `run`, no fuso do computador, ou `None`.
        updated_at: Hora desta gravação, no fuso do computador.
        elapsed_seconds: Tempo desde o início do `run`, ou `None`.
        limit_minutes: Prazo do perfil (`limits.max_duration_minutes`), ou `None`.
        fence_mode: Modo da cerca (`strict` ou `wide`), ou `None`.
        stages: Etapas, na ordem.
        functions_tried: Funções que o alcance tentou, ou `None` antes do alcance.
        functions_reached: Funções alcançadas, inclusive recusa esperada de login, ou `None`.
        scan_done: Funções já varridas, ou `None` fora da varredura.
        scan_total: Funções que a varredura vai atacar, ou `None`.
        current_function: Nome simples da função em ataque, ou `None`.
        allowed: Pedidos que passaram pela cerca, ou `None` sem auditoria do proxy.
        denied: Pedidos barrados pela cerca, ou `None`.
        outside_allow: Pedidos liberados com leitura fora do combinado (modo amplo), ou `None`.
        links: Para onde o caminho do alto leva (`None` quando o índice não existe).
    """

    product: str
    product_name: str
    run_id: str
    phase: LivePhase
    outcome: RunStateKind | None = None
    reason: str | None = None
    started_at: datetime | None = None
    updated_at: datetime
    elapsed_seconds: float | None = None
    limit_minutes: int | None = None
    fence_mode: str | None = None
    stages: tuple[LiveStage, ...] = ()
    functions_tried: int | None = None
    functions_reached: int | None = None
    scan_done: int | None = None
    scan_total: int | None = None
    current_function: str | None = None
    allowed: int | None = None
    denied: int | None = None
    outside_allow: int | None = None
    links: PanelLinks = PanelLinks()

"""Resumo de uma execução encadeada (`hdast run`): estágios, estados, tempos e artefatos.

É o conteúdo de `run.json`. Só dados: nenhum segredo, URL concreta nem corpo do alvo entra
aqui; as mensagens vêm das exceções da CLI, que já são redigidas.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

STAGES: Final = ("preflight", "probe", "scan", "nuclei", "authz", "negative", "report")

StageName = Literal["preflight", "probe", "scan", "nuclei", "authz", "negative", "report"]
StageStatus = Literal["ok", "failed", "interrupted", "skipped", "not_run"]
RunStatus = Literal["completed", "findings", "failed", "interrupted"]


class StageRecord(BaseModel):
    """O que aconteceu em um estágio.

    Attributes:
        name: Estágio.
        status: `ok`, `failed`, `interrupted`, `skipped` (pedido pela pessoa, por exemplo
            `--skip-scan`) ou `not_run` (um estágio anterior falhou).
        exit_code: Código de saída do estágio (`0` se ok; o do erro se falhou).
        run_id: Pasta de execução usada ou criada pelo estágio, quando existe.
        started_at: Início (ISO 8601), ou `None` se não rodou.
        duration_seconds: Duração.
        error_code: `error.code` do envelope quando falhou.
        message: Mensagem do erro ou observação.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: StageName
    status: StageStatus
    exit_code: int = 0
    run_id: str | None = None
    started_at: str | None = None
    duration_seconds: float = 0.0
    error_code: str | None = None
    message: str | None = None


class RunOptions(BaseModel):
    """Opções do `run` (só o que reduz ou escolhe; nada que amplie).

    `nuclei` é a chave pedida (`--nuclei/--no-nuclei`); o perfil sem `extra_checks.nuclei` e o
    `--only` ainda pulam o estágio, e `stages` diz por quê. `nuclei_only` marca o reteste que
    roda só o Nuclei (sem achado elegível do ZAP).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int | None = None
    skip_scan: bool = False
    nuclei: bool = False
    nuclei_only: bool = False
    authz: bool = False
    negative: bool = False
    fail_on: str | None = None
    compare: str | None = None
    max_minutes: int | None = None
    include_outcomes: bool = True
    only: tuple[str, ...] = ()


class RunSummary(BaseModel):
    """Conteúdo de `run.json`.

    Attributes:
        schema_version: Versão do formato.
        product: Produto.
        run_id: Pasta onde este arquivo foi gravado (a do `probe`, se ele chegou a rodar).
        status: `completed`, `findings` (saída 1), `failed` ou `interrupted`.
        exit_code: Código de saída do processo.
        started_at: Início.
        finished_at: Fim.
        duration_seconds: Duração total.
        options: Opções efetivas.
        stages: Os sete estágios, sempre, na ordem (`nuclei`, `authz` e `negative` ficam
            `skipped` com `--no-nuclei`, `--no-authz`, `--no-negative`, `--skip-scan` e, no caso
            do `nuclei`, também com `--only` ou sem `extra_checks.nuclei` no perfil).
        artifacts: Nome do arquivo -> nome do arquivo, só dos que existem na pasta.
        findings_by_severity: Achados do ZAP por severidade proposta, quando o `report` rodou.
        authz_findings_by_severity: Achados do estágio `authz` (técnica própria, não misturados
            aos do ZAP) por severidade, quando o estágio rodou.
        negative_findings_by_severity: Achados do estágio `negative` (valores que o esquema
            proíbe, ADR 0051; técnica própria) por severidade, quando o estágio rodou.
        nuclei_findings_by_severity: Achados do estágio `nuclei` (segundo motor, ADR 0122; origem
            própria, não misturados aos do ZAP) por severidade, quando o estágio rodou.
        nuclei_templates_selected: Quantos modelos do Nuclei o domínio escolheu para rodar, quando
            o estágio rodou.
        nuclei_templates_excluded: Modelos do Nuclei excluídos por motivo (um modelo com mais de
            um motivo conta em cada um), quando o estágio rodou.
        stop_requested: Se a trava de emergência (`hdast stop`) foi acionada.
        cleanup_command: Comando que a pessoa deve rodar para limpar os dados desta execução.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    product: str
    run_id: str
    status: RunStatus
    exit_code: int
    started_at: str
    finished_at: str
    duration_seconds: float
    options: RunOptions
    stages: tuple[StageRecord, ...]
    artifacts: dict[str, str] = Field(default_factory=dict)
    findings_by_severity: dict[str, int] | None = None
    authz_findings_by_severity: dict[str, int] | None = None
    negative_findings_by_severity: dict[str, int] | None = None
    nuclei_findings_by_severity: dict[str, int] | None = None
    nuclei_templates_selected: int | None = None
    nuclei_templates_excluded: dict[str, int] | None = None
    stop_requested: bool = False
    cleanup_command: str | None = None

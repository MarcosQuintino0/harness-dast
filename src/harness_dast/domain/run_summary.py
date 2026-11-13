"""Resumo de uma execução encadeada (`hdast run`): estágios, estados, tempos e artefatos.

É o conteúdo de `run.json`. Só dados: nenhum segredo, URL concreta nem corpo do alvo entra
aqui; as mensagens vêm das exceções da CLI, que já são redigidas.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

STAGES: Final = ("preflight", "probe", "scan", "report")

StageName = Literal["preflight", "probe", "scan", "report"]
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
    """Opções efetivas do `run` (só o que reduz ou escolhe; nada que amplie)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int | None = None
    skip_scan: bool = False
    fail_on: str | None = None
    compare: str | None = None
    max_minutes: int | None = None


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
        stages: Os quatro estágios, sempre, na ordem.
        artifacts: Nome do arquivo -> nome do arquivo, só dos que existem na pasta.
        findings_by_severity: Achados por severidade proposta, quando o `report` rodou.
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
    stop_requested: bool = False
    cleanup_command: str | None = None

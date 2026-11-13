"""Plano de limpeza: contagens por comando, teto de linhas e quando a execução já terminou.

O plano é o que a pessoa vê antes de confirmar (hash do script, tabelas e quantas linhas cada
comando apagou DENTRO da transação ainda aberta). Este módulo é puro: o relógio entra por
parâmetro.
"""

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.errors import CleanupError


class StatementResult(BaseModel):
    """Resultado de um comando dentro da transação.

    Attributes:
        index: Posição do comando no script, a partir de 1.
        table: Tabela alvo, em maiúsculas.
        rows: Linhas afetadas (que seriam apagadas, se a transação for confirmada).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    table: str
    rows: int


class CleanupPlan(BaseModel):
    """O que foi apagado na transação aberta e aguarda a confirmação.

    Attributes:
        product: Produto.
        run_id: Execução cujo lixo está sendo limpo.
        script_sha256: SHA-256 (hex) do script lido.
        results: Linhas afetadas por comando, na ordem do script.
        max_rows: Teto de linhas do perfil (`cleanup.max_rows`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    product: str
    run_id: str
    script_sha256: str
    results: tuple[StatementResult, ...]
    max_rows: int

    @property
    def total_rows(self) -> int:
        """Soma das linhas afetadas."""
        return sum(result.rows for result in self.results)


def ensure_within_ceiling(total: int, ceiling: int, *, source: str) -> None:
    """Recusa quando a limpeza apagaria mais linhas que o teto.

    Args:
        total: Linhas que a transação apagou.
        ceiling: Teto permitido.
        source: De onde vem o teto (para a mensagem), por exemplo `cleanup.max_rows`.

    Raises:
        CleanupError: Se `total` passa de `ceiling`. A transação deve sofrer ROLLBACK.
    """
    if total > ceiling:
        raise CleanupError(
            f"A limpeza apagaria {total} linhas, acima do teto de {ceiling} ({source}).",
            hint=(
                "Nada foi gravado (ROLLBACK). Confira o script e o conteúdo do banco; só aumente "
                "o teto no perfil com a concordância da pessoa dona do produto."
            ),
        )


def run_is_finished(
    *, finished_at: str | None, started_at: datetime, max_duration_minutes: int, now: datetime
) -> bool:
    """Diz se nenhuma varredura desta execução pode mais estar em andamento.

    Terminou quando o manifesto tem `finished_at`. Uma execução interrompida (Ctrl+C, queda do
    processo) nunca grava o fim; por isso, passado o prazo máximo da própria execução
    (`limits.max_duration_minutes`), ela também conta como terminada: nenhum envio legítimo
    acontece depois do prazo.
    """
    if finished_at is not None:
        return True
    return now >= started_at + timedelta(minutes=max_duration_minutes)


CleanupStatus = Literal["dry_run", "committed", "declined", "failed"]
ConfirmationMethod = Literal["none", "interactive", "token"]


class CleanupRecord(ApiModel):
    """`cleanup.json` da execução e `data` do envelope. Nunca tem valor de ligação nem credencial.

    Attributes:
        schema_version: Versão do formato (1).
        run_id: Execução limpa.
        product: Produto.
        status: `dry_run` (tudo desfeito), `committed`, `declined` (a pessoa recusou; tudo
            desfeito) ou `failed` (erro; tudo desfeito).
        script_sha256: SHA-256 (hex) do script executado.
        statement_count: Quantos comandos o script tem.
        tables: Tabelas distintas tocadas.
        statements: Linhas afetadas por comando (vazio se a falha veio antes de executar).
        total_rows: Soma das linhas afetadas.
        max_rows: Teto do perfil.
        confirmation_method: Como a confirmação foi dada: `interactive`, `token` ou `none`
            (`--dry-run`).
        committed: Se a transação foi confirmada.
        rolled_back: Se a transação foi desfeita.
        started_at: Início (ISO 8601).
        finished_at: Fim (ISO 8601).
        duration_ms: Duração total em milissegundos.
        failed_statement: Em `failed`, o índice do comando que falhou, quando se aplica.
        failed_table: Em `failed`, a tabela desse comando.
        error_code: Em `failed`, o código do erro (`CLEANUP_FAILED`...).
        token_expires_at: No `--dry-run`, até quando o token vale (o token nunca é gravado).
    """

    schema_version: int = 1
    run_id: str
    product: str
    status: CleanupStatus
    script_sha256: str
    statement_count: int
    tables: tuple[str, ...]
    statements: tuple[StatementResult, ...]
    total_rows: int
    max_rows: int
    confirmation_method: ConfirmationMethod
    committed: bool
    rolled_back: bool
    started_at: str
    finished_at: str
    duration_ms: int
    failed_statement: int | None = None
    failed_table: str | None = None
    error_code: str | None = None
    token_expires_at: str | None = None


class CleanupAuditLine(ApiModel):
    """Linha de `cleanup-audit.jsonl` (só acréscimo): o início e o fim de cada tentativa.

    Attributes:
        event: `started` (gravada antes de abrir a conexão) ou `finished`.
        at: Instante (ISO 8601).
        product: Produto.
        run_id: Execução.
        script_sha256: Hash do script.
        mode: `dry_run` ou `execute`.
        confirmation_method: Como a confirmação foi dada.
        status: Em `finished`, o estado final.
        total_rows: Em `finished`, as linhas afetadas.
    """

    event: Literal["started", "finished"]
    at: str
    product: str
    run_id: str
    script_sha256: str
    mode: Literal["dry_run", "execute"]
    confirmation_method: ConfirmationMethod
    status: CleanupStatus | None = None
    total_rows: int | None = None

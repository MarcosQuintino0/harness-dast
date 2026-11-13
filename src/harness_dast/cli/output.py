"""Saída da CLI: envelope JSON versionado e texto humano.

Único módulo autorizado a escrever em stdout. Só o resultado do comando vai para
stdout; diagnósticos humanos de erro vão para stderr, e logs pelo logger estruturado.
O formato do envelope é contrato público (`schema_version`); mudança incompatível
exige ADR e nova versão.
"""

import sys
from dataclasses import dataclass, field

import typer
from pydantic import BaseModel, ConfigDict, JsonValue

from harness_dast.domain.errors import HarnessError
from harness_dast.observability.logging import SecretRegistry

SCHEMA_VERSION = 1


class ErrorInfo(BaseModel):
    """Erro serializado no envelope."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    hint: str | None = None


class Envelope(BaseModel):
    """Envelope JSON de toda resposta da CLI com `--json`.

    Em sucesso `data` está presente; em falha, `error`. Campos ausentes são omitidos.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    ok: bool
    run_id: str | None = None
    data: dict[str, JsonValue] | None = None
    error: ErrorInfo | None = None


@dataclass
class CliState:
    """Estado da invocação atual, criado por execução e compartilhado via contexto Typer."""

    json_mode: bool = False
    secrets: SecretRegistry = field(default_factory=SecretRegistry)
    result_emitted: bool = False
    """O comando já escreveu o envelope do próprio desfecho (inclusive 130 deliberado)."""


def get_state(ctx: typer.Context) -> CliState:
    """Obtém o estado da invocação a partir do contexto.

    Args:
        ctx: Contexto do Typer.

    Returns:
        O estado criado por `run_app`.

    Raises:
        TypeError: Se o contexto não foi iniciado por `run_app` (erro de programação).
    """
    if not isinstance(ctx.obj, CliState):
        raise TypeError("Contexto da CLI sem CliState; inicie a aplicação por run_app.")
    return ctx.obj


def build_success(data: dict[str, JsonValue], run_id: str | None = None) -> Envelope:
    """Monta o envelope de sucesso.

    Args:
        data: Resultado do comando.
        run_id: Identificador da execução, quando houver.

    Returns:
        Envelope com `ok=True`.
    """
    return Envelope(ok=True, run_id=run_id, data=data)


def build_failure(error: HarnessError) -> Envelope:
    """Monta o envelope de falha a partir de um erro do harness.

    Args:
        error: Erro esperado ou o `HarnessError` genérico para falhas internas.

    Returns:
        Envelope com `ok=False`.
    """
    info = ErrorInfo(code=error.code, message=error.message, hint=error.hint)
    return Envelope(ok=False, error=info)


def build_failure_with_data(
    error: HarnessError, data: dict[str, JsonValue], run_id: str | None = None
) -> Envelope:
    """Monta o envelope de falha que ainda carrega o resultado parcial (`data`).

    Serve a comandos que produzem dados mesmo quando terminam em falha (preflight que não
    está pronto, probe interrompido): o agente lê `data` e `error` no mesmo envelope.

    Args:
        error: Erro que define o código de saída.
        data: Resultado do comando.
        run_id: Identificador da execução, quando houver.

    Returns:
        Envelope com `ok=False`, `data` e `error`.
    """
    info = ErrorInfo(code=error.code, message=error.message, hint=error.hint)
    return Envelope(ok=False, run_id=run_id, data=data, error=info)


def _render_human_success(envelope: Envelope) -> str:
    lines = [f"{key}: {value}" for key, value in (envelope.data or {}).items()]
    return "\n".join(lines)


def _render_human_failure(envelope: Envelope) -> str:
    error = envelope.error
    if error is None:
        return ""
    text = f"Erro [{error.code}]: {error.message}"
    if error.hint:
        text += f"\nComo resolver: {error.hint}"
    return text


def emit(envelope: Envelope, *, json_mode: bool, human: str | None = None) -> None:
    """Escreve o resultado no destino correto.

    Com `json_mode`, o envelope (sucesso ou falha) vai a stdout como uma linha JSON.
    Sem ele, sucesso vai a stdout em texto e falha a stderr; uma falha que traz `data`
    (resultado parcial) escreve o resultado em stdout e o erro em stderr.

    Args:
        envelope: Resultado a emitir.
        json_mode: Se `True`, emite JSON.
        human: Texto legível do sucesso para o modo humano; sem ele, lista `campo: valor`.
    """
    if json_mode:
        sys.stdout.write(envelope.model_dump_json(exclude_none=True) + "\n")
    elif envelope.ok:
        text = human if human is not None else _render_human_success(envelope)
        sys.stdout.write(text + "\n")
    else:
        if envelope.data is not None:
            text = human if human is not None else _render_human_success(envelope)
            sys.stdout.write(text + "\n")
        sys.stderr.write(_render_human_failure(envelope) + "\n")

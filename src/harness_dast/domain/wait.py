"""Espera de uma execução: resultado e estado de observação."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WaitResult(BaseModel):
    """Estado observado; `exit_code` pertence ao run, nunca ao comando wait."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    state: Literal["finished", "running", "stopped", "unknown"]
    status: str | None = None
    exit_code: int | None = None
    phase: str | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    run_id: str | None = None
    lock_id: str | None = None

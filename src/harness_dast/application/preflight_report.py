"""Resultado do `preflight`: as verificações como dado."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CheckKind = Literal["scope", "environment"]


class PreflightCheck(BaseModel):
    """Uma verificação do preflight.

    Attributes:
        id: Identificador estável (`authorization`, `window`, `secrets:user_a`, `zap`,
            `target_health`, `login:user_a`, `csrf:user_a`).
        ok: Se passou.
        detail: O que foi verificado ou o que falhou e o que fazer. Sem segredos.
        kind: `scope` (autorização ou janela) ou `environment` (todo o resto).
        operator_detail: Complemento para a pessoa (nome da variável de ambiente); excluído
            do JSON.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    ok: bool
    detail: str
    kind: CheckKind = "environment"
    operator_detail: str | None = Field(default=None, exclude=True)


class PreflightReport(BaseModel):
    """Resultado do preflight.

    Attributes:
        product: Produto.
        ready: `true` só se todas as verificações passaram.
        checks: As verificações, na ordem executada.
        run_id: Pasta de execução com o `audit.jsonl` do preflight, quando algo foi enviado.
        zap_version: Versão do ZAP, quando ele respondeu.
    """

    model_config = ConfigDict(frozen=True)

    product: str
    ready: bool
    checks: tuple[PreflightCheck, ...]
    run_id: str | None = None
    zap_version: str | None = None

    def first_failure(self) -> PreflightCheck | None:
        """Primeira verificação que falhou, priorizando as de escopo."""
        failed = [check for check in self.checks if not check.ok]
        failed.sort(key=lambda check: check.kind != "scope")
        return failed[0] if failed else None

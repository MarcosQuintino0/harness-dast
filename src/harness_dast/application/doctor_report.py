"""Resultado do `doctor`: as conferências do ambiente como dado."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

DoctorStatus = Literal["ok", "warn", "fail"]
DoctorKind = Literal["scope", "config", "environment"]


class DoctorCheck(BaseModel):
    """Uma conferência do `doctor`.

    Attributes:
        id: Identificador estável (`python`, `uv`, `docker`, `images`, `port:8080`,
            `products_dir`, `stack`, `profile`, `authorization`, `window`, `secrets:user_a`).
        status: `ok`; `warn` (algo a saber, não impede começar); `fail` (impede).
        detail: O que foi conferido ou, se não passou, o que houve e o que fazer, em uma linha.
            Sem segredos.
        kind: `scope` (autorização ou janela), `config` (perfil, pasta de produtos, portas
            configuradas) ou `environment` (todo o resto). Define o código de saída.
        operator_detail: Complemento para a pessoa (nome da variável de ambiente); excluído do
            JSON.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    status: DoctorStatus
    detail: str
    kind: DoctorKind = "environment"
    operator_detail: str | None = Field(default=None, exclude=True)


def make_check(
    check_id: str,
    status: DoctorStatus,
    detail: str,
    kind: DoctorKind = "environment",
    operator_detail: str | None = None,
) -> DoctorCheck:
    """Monta uma conferência com a categoria de ambiente por padrão."""
    return DoctorCheck(
        id=check_id, status=status, detail=detail, kind=kind, operator_detail=operator_detail
    )


class DoctorSummary(BaseModel):
    """Contagem das conferências por resultado.

    Attributes:
        ok: Quantas passaram.
        warn: Quantas avisaram.
        fail: Quantas reprovaram.
    """

    model_config = ConfigDict(frozen=True)

    ok: int
    warn: int
    fail: int


class DoctorReport(BaseModel):
    """Resultado do `doctor`.

    Attributes:
        product: Produto conferido, ou `None` quando só o ambiente foi conferido.
        ready: `true` só se nenhuma conferência reprovou (avisos não contam).
        checks: As conferências, na ordem executada.
        summary: Contagem por resultado.
    """

    model_config = ConfigDict(frozen=True)

    product: str | None
    ready: bool
    checks: tuple[DoctorCheck, ...]
    summary: DoctorSummary

    @classmethod
    def from_checks(cls, checks: tuple[DoctorCheck, ...], *, product: str | None = None) -> Self:
        """Monta o relatório e determina a prontidão a partir das conferências."""
        summary = DoctorSummary(
            ok=sum(check.status == "ok" for check in checks),
            warn=sum(check.status == "warn" for check in checks),
            fail=sum(check.status == "fail" for check in checks),
        )
        return cls(product=product, ready=summary.fail == 0, checks=checks, summary=summary)

    def first_failure(self) -> DoctorCheck | None:
        """Primeira reprovação, priorizando escopo, depois configuração."""
        failed = [check for check in self.checks if check.status == "fail"]
        failed.sort(key=lambda check: ("scope", "config", "environment").index(check.kind))
        return failed[0] if failed else None

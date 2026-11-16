"""Impressões digitais tipadas das dependências de uma escolha de estratégia."""

import hashlib
import json

from pydantic import Field

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_fingerprint import block_digests
from harness_dast.domain.secret_ref import ProfileModel

_SHA = r"^[0-9a-f]{64}$"


class StrategyBasisContext(ProfileModel):
    """Digests atuais, inclusive motor indisponível, sem conteúdo de documentos."""

    environment: str = Field(pattern=_SHA, min_length=64, max_length=64)
    authorization: str = Field(pattern=_SHA, min_length=64, max_length=64)
    accounts: str = Field(pattern=_SHA, min_length=64, max_length=64)
    openapi: str = Field(pattern=_SHA, min_length=64, max_length=64)
    data_rules: str = Field(pattern=_SHA, min_length=64, max_length=64)
    flows: str = Field(pattern=_SHA, min_length=64, max_length=64)
    engine: str | None = Field(pattern=_SHA, min_length=64, max_length=64)


class StrategyBasis(StrategyBasisContext):
    """Vínculo completo das fontes necessárias, incluindo a versão do motor."""

    engine: str = Field(pattern=_SHA, min_length=64, max_length=64)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_strategy_document(content: bytes | None) -> str:
    """Identifica bytes exatos, distinguindo documento ausente de documento vazio."""
    return _digest(b"absent\0" if content is None else b"present\0" + content)


def make_strategy_basis(
    profile: ProductProfile,
    *,
    openapi_sha256: str,
    data_rules_sha256: str,
    flows_sha256: str,
    engine_version: str | None,
) -> StrategyBasis | None:
    """Resume fontes atuais; sem versão efetiva do motor, não há vínculo verificável.

    Os digests de documentos são obtidos independentemente dos valores da estratégia.
    O resumo da autenticação inclui o roteamento completo e nomes de referências, sem
    resolver ou devolver segredos. A autorização usa os blocos protegidos atuais.
    """
    context = describe_strategy_basis(
        profile,
        openapi_sha256=openapi_sha256,
        data_rules_sha256=data_rules_sha256,
        flows_sha256=flows_sha256,
        engine_version=engine_version,
    )
    if context.engine is None:
        return None
    return StrategyBasis.model_validate(context.model_dump())


def describe_strategy_basis(
    profile: ProductProfile,
    *,
    openapi_sha256: str,
    data_rules_sha256: str,
    flows_sha256: str,
    engine_version: str | None,
) -> StrategyBasisContext:
    """Resume as fontes atuais mesmo quando a versão do motor não está disponível."""
    blocks = block_digests(profile)
    protected = {key: value for key, value in blocks.items() if key != "environment"}
    authorization = json.dumps(protected, sort_keys=True, separators=(",", ":"))
    accounts = json.dumps(
        profile.auth.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return StrategyBasisContext(
        environment=blocks["environment"],
        authorization=_digest(authorization.encode()),
        accounts=_digest(accounts.encode()),
        openapi=openapi_sha256,
        data_rules=data_rules_sha256,
        flows=flows_sha256,
        engine=_digest(engine_version.encode())
        if engine_version and engine_version.strip()
        else None,
    )

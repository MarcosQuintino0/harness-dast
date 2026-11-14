"""Validade vencida e avisos da carta estruturada (ADR 0036).

- `expired_issue`: carta com `authorization.valid_until` no passado é recusada (pendência
  `AUTHORIZATION_EXPIRED`). A regra é a mesma de `Authorization.ensure_valid`: o último dia vale
  inteiro, contado em UTC. O dia de hoje entra por parâmetro (nada de relógio aqui).
- `letter_warnings`: avisos que NÃO recusam a carta nem mudam o perfil gerado. Servem para o
  agente mostrar à pessoa na entrevista o que merece uma segunda olhada do dono do produto.

Este módulo é puro.
"""

from datetime import date, timedelta
from typing import Final

from harness_dast.domain.letter_collect import LetterIssue
from harness_dast.domain.profile import ProductProfile

AUTHORIZATION_EXPIRED: Final = "AUTHORIZATION_EXPIRED"
ALLOW_ROOT_WILDCARD: Final = "ALLOW_ROOT_WILDCARD"
DELETE_AUTHORIZED: Final = "DELETE_AUTHORIZED"
DENY_PATHS_EMPTY: Final = "DENY_PATHS_EMPTY"
VALIDITY_OVER_ONE_YEAR: Final = "VALIDITY_OVER_ONE_YEAR"
AUTHZ_WRITES_AUTHORIZED: Final = "AUTHZ_WRITES_AUTHORIZED"

_ROOT_WILDCARD: Final = "/**"
_ONE_YEAR: Final = timedelta(days=365)


def expired_issue(valid_until: date, today: date) -> LetterIssue | None:
    """Pendência da carta cuja autorização já venceu; `None` se ainda vale.

    Args:
        valid_until: Último dia de validade (inclusive).
        today: Dia de hoje em UTC.
    """
    if today <= valid_until:
        return None
    return LetterIssue(
        field="authorization.valid_until",
        code=AUTHORIZATION_EXPIRED,
        message=(
            f"A autorização venceu em {valid_until.isoformat()} e hoje é {today.isoformat()}. "
            "Peça ao dono do produto uma autorização em vigor e atualize a carta; "
            "o agente não muda a data."
        ),
    )


def letter_warnings(profile: ProductProfile, today: date) -> tuple[LetterIssue, ...]:
    """Avisos sobre o perfil gerado da carta (não bloqueiam, não mudam o que é gerado).

    Avisa: permissão com `/**` na raiz, método `DELETE` autorizado, nenhum caminho proibido e
    validade a mais de um ano e escrita do teste entre contas autorizada pela carta.
    """
    warnings: list[LetterIssue] = []
    for index, rule in enumerate(profile.scope.allow):
        field = f"scope.allow[{index}]"
        if _ROOT_WILDCARD in rule.paths:
            warnings.append(
                LetterIssue(
                    field=f"{field}.paths",
                    code=ALLOW_ROOT_WILDCARD,
                    message=(
                        f"A permissão para {rule.host} libera todos os caminhos "
                        f"({_ROOT_WILDCARD}). "
                        "Confirme com o dono do produto que é isso mesmo; se não for, "
                        "liste só os caminhos autorizados."
                    ),
                )
            )
        if "DELETE" in rule.methods:
            warnings.append(
                LetterIssue(
                    field=f"{field}.methods",
                    code=DELETE_AUTHORIZED,
                    message=(
                        f"O método DELETE está autorizado em {rule.host}: o teste pode apagar "
                        "dados do ambiente. Confirme com o dono do produto que isso é esperado."
                    ),
                )
            )
    if not profile.scope.deny_paths:
        warnings.append(
            LetterIssue(
                field="scope.deny_paths",
                code=DENY_PATHS_EMPTY,
                message=(
                    "Nenhum caminho proibido foi informado. Pergunte ao dono do produto se há "
                    "algo que não pode ser tocado (administração, pagamento, envio de mensagens)."
                ),
            )
        )
    valid_until = profile.scope.authorization.valid_until
    if valid_until - today > _ONE_YEAR:
        warnings.append(
            LetterIssue(
                field="authorization.valid_until",
                code=VALIDITY_OVER_ONE_YEAR,
                message=(
                    f"A autorização vale por mais de um ano (até {valid_until.isoformat()}). "
                    "Confirme com o dono do produto que a validade está certa."
                ),
            )
        )
    if profile.authz.allow_writes:
        warnings.append(
            LetterIssue(
                field="attack.allow_authz_writes",
                code=AUTHZ_WRITES_AUTHORIZED,
                message=(
                    "A carta autoriza o teste entre contas a ESCREVER no alvo (atribuição em "
                    "massa, alteração de recurso de outra conta e métodos de escrita): ele pode "
                    "alterar dados e criar recursos "
                    "do ambiente. Confirme com o dono do produto que a carta diz isso e que o "
                    "ambiente é de teste com dados sintéticos."
                ),
            )
        )
    return tuple(warnings)

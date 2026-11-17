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
NEGATIVE_WRITES_AUTHORIZED: Final = "NEGATIVE_WRITES_AUTHORIZED"
OUTCOMES_ATTACK_EXTENDED: Final = "OUTCOMES_ATTACK_EXTENDED"
UPLOAD_SCAN_AUTHORIZED: Final = "UPLOAD_SCAN_AUTHORIZED"
ATTACK_FLAG_AUTHORIZED: Final = "ATTACK_FLAG_AUTHORIZED"

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
    validade a mais de um ano, escrita autorizada pela carta (teste entre contas e teste de
    valores inválidos) e ataque a operações que deram não encontrado ou outra falha de dados
    (ADR 0050).
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
    if profile.negative.allow_writes:
        warnings.append(
            LetterIssue(
                field="attack.allow_invalid_input_writes",
                code=NEGATIVE_WRITES_AUTHORIZED,
                message=(
                    "A carta autoriza o teste de valores inválidos a GRAVAR no alvo dado com "
                    "valor que o contrato proíbe (POST, PUT e PATCH): o dado inválido aceito "
                    "persiste (restaurado em PUT e PATCH, deixado em POST). Confirme com o dono "
                    "do produto que a carta diz isso e que o ambiente é de teste com dados "
                    "sintéticos."
                ),
            )
        )
    if profile.scan.allow_upload_scan:
        warnings.append(
            LetterIssue(
                field="attack.allow_upload_scan",
                code=UPLOAD_SCAN_AUTHORIZED,
                message=(
                    "A carta autoriza o ZAP a varrer operações de envio de arquivo: os valores de "
                    "ataque do ZAP (nome e conteúdo de arquivo, campos de texto) serão GRAVADOS "
                    "no armazenamento do alvo, e esta ferramenta não os controla. Confirme com o "
                    "dono do produto que a carta diz isso, que o ambiente é de teste com dados "
                    "sintéticos e que o armazenamento aceita lixo."
                ),
            )
        )
    warnings.extend(_attack_flag_warnings(profile))
    if profile.scan.include_outcomes:
        warnings.append(
            LetterIssue(
                field="attack.include_outcomes",
                code=OUTCOMES_ATTACK_EXTENDED,
                message=(
                    "O teste ataca também operações que responderam "
                    + ", ".join(profile.scan.include_outcomes)
                    + "; nos POST, PUT e PATCH isso cria e altera mais dados sintéticos; "
                    "confirme com o dono do produto."
                ),
            )
        )
    warnings.extend(_technology_warning(profile))
    return tuple(warnings)


_ATTACK_FLAG_TEXT: Final = {
    "inject_headers": "injetar também em cabeçalhos e cookies",
    "oast": "usar o servidor de retorno do laboratório (retorno fora de banda)",
    "allow_rate_tests": "fazer testes de limite de consumo (poucos pedidos, com teto)",
    "experimental_rules": "usar as regras experimentais (alpha) do ZAP",
    "inventory": "inventariar versões irmãs e documentação exposta",
}


def _attack_flag_warnings(profile: ProductProfile) -> list[LetterIssue]:
    """Um aviso por capacidade da V1.12 que a carta ligou (ADR 0096)."""
    enabled = {
        "inject_headers": profile.scan.inject_headers,
        "oast": profile.scan.oast,
        "allow_rate_tests": profile.extra_checks.allow_rate_tests,
        "experimental_rules": profile.extra_checks.experimental_rules,
        "inventory": profile.extra_checks.inventory,
    }
    return [
        LetterIssue(
            field=f"attack.{name}",
            code=ATTACK_FLAG_AUTHORIZED,
            message=(
                f"A carta autoriza {text}: isso muda o tráfego ao alvo. Confirme com o dono do "
                "produto que a carta diz isso e que o ambiente é de teste com dados sintéticos."
            ),
        )
        for name, text in _ATTACK_FLAG_TEXT.items()
        if enabled[name]
    ]


def _technology_warning(profile: ProductProfile) -> tuple[LetterIssue, ...]:
    if profile.technologies is None:
        return ()
    return (
        LetterIssue(
            field="attack.technologies",
            code="TECHNOLOGIES_ADVISORY",
            message=(
                "A declaração não confirma a tecnologia nem reduz a cobertura: "
                "todas as regras continuam ativas."
            ),
        ),
    )

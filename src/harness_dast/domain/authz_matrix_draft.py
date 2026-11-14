"""Rascunho da tabela "quem pode o quê" (`hdast authz --draft-matrix`, ADR 0041). Módulo puro.

O rascunho é **hipótese**: nasce do OpenAPI (operações) e, com `--run`, do que o `probe` viu
(`allow`: os papéis cujas contas obtiveram `2xx` na operação). **Nunca preenche `deny`**: o que
o produto proíbe é decisão do dono, e uma proibição inventada geraria alarme falso com ar de
autoridade. O arquivo não vale nada até uma pessoa conferir cada linha, levá-la ao `target.yml`
e aprovar o escopo (`hdast profile approve`); o carregador do perfil nem o lê. O texto sai em
YAML com cadeias entre aspas duplas e só ASCII (o nome de operação vem do OpenAPI, não confiável).
"""

import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from harness_dast.domain.api_model import Operation
from harness_dast.domain.authz_matrix import MAX_MATRIX_RULES
from harness_dast.domain.authz_matrix_plan import matrix_roles
from harness_dast.domain.probe_exchange import ExchangeRecord

DRAFT_FILE: Final = "authz-matrix.draft.yml"
_REVIEW: Final = "pendente"


@dataclass(frozen=True)
class DraftItem:
    """Uma operação do rascunho.

    Attributes:
        operation: `operationId`.
        method: Método HTTP (maiúsculas).
        path: Modelo de caminho.
        allow: Papéis que o `probe` viu com `2xx` na operação (vazio sem `--run`).
    """

    operation: str
    method: str
    path: str
    allow: tuple[str, ...]


def draft_items(
    operations: Sequence[Operation],
    exchanges: Sequence[ExchangeRecord],
    roles: Mapping[str, str],
    role_order: Sequence[str],
    skip: Collection[str],
    infrastructure_paths: Collection[str],
) -> tuple[DraftItem, ...]:
    """Um item por operação, na ordem do OpenAPI, sem as públicas nem as de infraestrutura.

    Args:
        operations: Operações do OpenAPI.
        exchanges: Pedidos com sucesso do `probe` (vazio sem `--run`).
        roles: Papel de cada conta (apelido -> papel).
        role_order: `authz.role_order` (ordena os papéis de `allow`).
        skip: `authz.public_operations`: não entram (a tabela não pode citá-las).
        infrastructure_paths: Caminhos de login, saúde e preparação: não são negócio.
    """
    order = {role: index for index, role in enumerate(matrix_roles(role_order, roles))}
    items: list[DraftItem] = []
    for operation in operations:
        if operation.operation_id in skip or operation.path in infrastructure_paths:
            continue
        seen = {
            roles[e.account]
            for e in exchanges
            if e.operation_id == operation.operation_id and e.account in roles
        }
        allow = tuple(sorted(seen, key=lambda role: order[role]))
        items.append(
            DraftItem(operation.operation_id, operation.method.upper(), operation.path, allow)
        )
    return tuple(items[:MAX_MATRIX_RULES])


def _quoted(value: str) -> str:
    # String YAML de aspas duplas, só ASCII. Acima de U+FFFF o JSON escreveria um par substituto
    # que o YAML não junta de volta; ali vai o escape `\U` de oito dígitos, que o YAML entende.
    parts = [
        f"\\U{ord(char):08X}" if ord(char) > 0xFFFF else json.dumps(char)[1:-1] for char in value
    ]
    return '"' + "".join(parts) + '"'


def _item_lines(item: DraftItem) -> list[str]:
    allow = ", ".join(_quoted(role) for role in item.allow)
    return [
        f"    - operation: {_quoted(item.operation)}",
        f"      method: {_quoted(item.method)}",
        f"      path: {_quoted(item.path)}",
        f"      allow: [{allow}]",
        "      deny: []",
        f"      review: {_quoted(_REVIEW)}",
    ]


def render_draft(product: str, items: Sequence[DraftItem], *, with_run: bool) -> str:
    """Texto do arquivo de rascunho, com o cabeçalho que diz o que ele é e o que não é."""
    origin = (
        "allow vem do que o probe viu com 2xx; confira cada papel."
        if with_run
        else "allow está vazio (sem --run); preencha."
    )
    header = [
        f'# RASCUNHO da tabela "quem pode o quê" (ADR 0041) de {product}.',
        "# Isto é HIPÓTESE, gerada sem tocar o alvo. NÃO vale nada até uma pessoa decidir",
        "# cada linha, levá-la ao target.yml e aprovar o escopo (hdast profile approve).",
        "# O carregador do perfil não lê este arquivo.",
        "# A ferramenta nunca preenche deny: quem decide o que é proibido é o dono do produto.",
        f"# {origin}",
        "# Papel que não aparece numa linha não é testado (nunca é presumido proibido).",
        "# Ao copiar para authz.access_matrix do target.yml, apague method, path e review:",
        "# o perfil não aceita campo extra.",
        "authz:",
        "  access_matrix:",
    ]
    body = [line for item in items for line in _item_lines(item)]
    return "\n".join([*header, *body, ""])

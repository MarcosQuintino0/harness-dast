"""Impressão digital dos blocos de proteção do perfil (ADR 0037).

Calcula, sobre o perfil JÁ validado e normalizado (nunca sobre o texto do arquivo), um resumo
criptográfico por bloco de proteção e um resumo geral. Comentário, espaço e ordem de chave do
YAML não entram; o que entra é o que decide o que é tocado, com que conta e com que carga:

- `environment`: nome, `base_url` e verificação de TLS;
- `scope.allow`, `scope.deny_paths`, `scope.path_mode`, `scope.authorization`, `scope.windows`;
- `limits`;
- `auth`: tipo, caminho do login (ou cabeçalho da chave), contas (apelido, papel e NOMES de
  `secret_ref`) e `login_limit`;
- `scan`: o bloco inteiro (força, limiar, regras desligadas, tetos de tempo, renovação de token,
  gate de severidade, injeção em segmento de caminho e `PUT`/`PATCH` sobre qualquer recurso);
- `authz`: o bloco inteiro (operações públicas, ordem de papéis, campos voláteis, métodos
  repetidos, campos da atribuição em massa e verificações desligadas);
- `cleanup`: a configuração da limpeza (caminho do script, NOMES de `secret_ref`, tabelas, teto
  de linhas, esquema); nunca valor de segredo nem o conteúdo do script.

Critério (ADR 0037): entra tudo que amplia o que é tocado, com que conta, com que carga ou por
quanto tempo, E tudo que reduz o que é relatado. Fica de fora, de propósito, só o que o agente
precisa ajustar depois da aprovação para alcançar as operações e que não muda nem o alcance nem
o relato: `auth.csrf`, `auth.account_map`, `auth.default_account`, `auth.token_expired`, campos de
codificação do login, `probe` e `openapi`. O motivo de cada campo está no ADR 0037.

Mudar o que entra aqui muda a impressão digital de todo perfil: as aprovações existentes passam
a ser "alteradas" e a pessoa aprova de novo (falha fechada). Este módulo é puro e determinístico.
"""

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Final

from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.auth import PasswordLoginAuth
from harness_dast.domain.profile import ProductProfile

FINGERPRINT_VERSION: Final = 2
"""Versão do cálculo. Aprovação gravada com outra versão é recusada (`invalid`).

Versão 2: `scan` e `authz` inteiros e o bloco `cleanup` passaram a entrar (QA da V1.3).
Aprovação da versão 1 vale como não aprovada e uma pessoa aprova de novo.
"""

BLOCKS: Final[tuple[tuple[str, str], ...]] = (
    ("environment", "ambiente alvo"),
    ("scope.allow", "o que pode ser alcançado"),
    ("scope.deny_paths", "caminhos proibidos"),
    ("scope.path_mode", "modo de caminho"),
    ("scope.authorization", "autorização, com referência e validade"),
    ("scope.windows", "janelas de execução"),
    ("limits", "limites de carga"),
    ("auth", "contas e login"),
    ("scan", "política da varredura e do gate de severidade"),
    ("authz", "configuração do teste de autorização"),
    ("cleanup", "limpeza do ambiente, com script, banco e tetos"),
)
"""Blocos de proteção, em ordem de exibição: identificador e descrição em português."""

BLOCK_IDS: Final[tuple[str, ...]] = tuple(block_id for block_id, _ in BLOCKS)


def describe_block(block_id: str) -> str:
    """Descrição em português do bloco; o próprio identificador se ele for desconhecido."""
    return dict(BLOCKS).get(block_id, block_id)


def _canonical(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _list(items: Iterable[str | int]) -> list[JsonValue]:
    """Lista JSON (o `list` do mypy é invariante: `list[int]` não é `list[JsonValue]`)."""
    return list(items)


def _sorted_items(items: list[JsonValue]) -> list[JsonValue]:
    """Ordena itens de conjunto (a ordem não muda o que é permitido) pelo texto canônico."""
    return sorted(items, key=_canonical)


def _allow_rules(profile: ProductProfile) -> list[JsonValue]:
    rules: list[JsonValue] = []
    for rule in profile.scope.allow:
        dumped = rule.model_dump(mode="json")
        dumped["paths"] = _list(sorted(set(rule.paths)))
        dumped["methods"] = _list(sorted(set(rule.methods)))
        rules.append(dumped)
    return _sorted_items(rules)


def _windows(profile: ProductProfile) -> list[JsonValue]:
    return _sorted_items(
        [
            {
                "days": _list(sorted(window.days)),
                "start_minute": window.start_minute,
                "end_minute": window.end_minute,
                "timezone": window.timezone,
            }
            for window in profile.scope.windows
        ]
    )


def _auth(profile: ProductProfile) -> JsonValue:
    auth = profile.auth
    # As contas ficam na ordem do perfil: a primeira é a padrão quando não há `default_account`.
    accounts: list[JsonValue] = [account.model_dump(mode="json") for account in auth.accounts]
    if isinstance(auth, PasswordLoginAuth):
        limit = auth.login_limit
        return {
            "type": auth.type,
            "token_path": auth.token_path,
            "login_limit": None if limit is None else limit.max_per_minute,
            "accounts": accounts,
        }
    return {"type": auth.type, "header_name": auth.header_name, "accounts": accounts}


def _scan(profile: ProductProfile) -> JsonValue:
    dumped = profile.scan.model_dump(mode="json")
    # Conjuntos: a ordem em que o perfil os escreve não muda a política.
    dumped["mutating_methods"] = _list(sorted(set(profile.scan.mutating_methods)))
    dumped["disable_rules"] = _list(sorted(set(profile.scan.disable_rules)))
    return dumped


def _authz(profile: ProductProfile) -> JsonValue:
    authz = profile.authz
    dumped = authz.model_dump(mode="json")
    # `role_order` é ordem de privilégio: mantém a do perfil. Os demais são conjuntos.
    dumped["public_operations"] = _list(sorted(set(authz.public_operations)))
    dumped["volatile_fields"] = _list(sorted(set(authz.volatile_fields)))
    dumped["vertical_methods"] = _list(sorted(set(authz.vertical_methods)))
    dumped["disabled_checks"] = _list(sorted(set(authz.disabled_checks)))
    fields: list[JsonValue] = [
        field.model_dump(mode="json") for field in authz.mass_assignment_fields
    ]
    dumped["mass_assignment_fields"] = _sorted_items(fields)
    return dumped


def protected_blocks(profile: ProductProfile) -> dict[str, JsonValue]:
    """Forma canônica de cada bloco de proteção, na ordem de `BLOCK_IDS`.

    Conjuntos (regras de permissão, caminhos, métodos, janelas) saem ordenados; listas em que a
    ordem importa (as contas) mantêm a ordem do perfil.
    """
    authorization = profile.scope.authorization
    blocks: dict[str, JsonValue] = {
        "environment": profile.environment.model_dump(mode="json"),
        "scope.allow": _allow_rules(profile),
        "scope.deny_paths": _list(sorted(set(profile.scope.deny_paths))),
        "scope.path_mode": profile.scope.path_mode,
        "scope.authorization": {
            "reference": authorization.reference,
            "valid_until": authorization.valid_until.isoformat(),
        },
        "scope.windows": _windows(profile),
        "limits": profile.limits.model_dump(mode="json"),
        "auth": _auth(profile),
        "scan": _scan(profile),
        "authz": _authz(profile),
        "cleanup": None if profile.cleanup is None else profile.cleanup.model_dump(mode="json"),
    }
    return {block_id: blocks[block_id] for block_id in BLOCK_IDS}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def block_digests(profile: ProductProfile) -> dict[str, str]:
    """SHA-256 (hex) de cada bloco de proteção, por identificador."""
    blocks = protected_blocks(profile)
    return {block_id: _sha256(_canonical(value)) for block_id, value in blocks.items()}


def combine_digests(product: str, digests: Mapping[str, str]) -> str:
    """SHA-256 geral: junta a versão do cálculo, o produto e o resumo de cada bloco."""
    payload: JsonValue = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "product": product,
        "blocks": dict(digests),
    }
    return _sha256(_canonical(payload))

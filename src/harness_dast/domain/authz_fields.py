"""Classe de um nome de campo para a atribuição em massa: privilégio, saldo, preço, estado, dono.

A lista é fixa e testada (ADR 0040). A decisão olha só o NOME do campo, em palavras como em
`authz_sensitive` (`isAdmin` vira `is` e `admin`), nunca o valor. A direção do valor de teste
(`privilege` e `state` bom sobem, `blocked` desce, `discount` sobe e `price` desce) também sai
do nome. A lista é em português e inglês e é conservadora: palavra ambígua fica de fora. Este
módulo é puro.
"""

from typing import Final, Literal

from harness_dast.domain.authz_config import DEFAULT_VOLATILE_FIELDS, normalize_field_name
from harness_dast.domain.authz_sensitive import classify_field_name, field_words

CandidateKind = Literal["privilege", "balance", "price", "state", "ownership", "other"]
CandidateSource = Literal["declared", "readonly_in_input", "response_only", "name_in_input"]

KIND_ORDER: Final[tuple[CandidateKind, ...]] = (
    "privilege",
    "balance",
    "price",
    "state",
    "other",
    "ownership",
)
"""Prioridade das classes ao ordenar os candidatos derivados."""

PRIVILEGE_WORDS: Final[frozenset[str]] = frozenset(
    {
        "role",
        "roles",
        "papel",
        "papeis",
        "perfil",
        "admin",
        "administrator",
        "superuser",
        "staff",
        "permission",
        "permissions",
        "permissao",
        "permissoes",
        "scope",
        "scopes",
        "group",
        "groups",
        "grupo",
        "grupos",
        "level",
        "nivel",
        "tier",
        "plan",
        "plano",
        "premium",
        "vip",
        "verified",
        "verificado",
        "approved",
        "aprovado",
    }
)
BALANCE_WORDS: Final[frozenset[str]] = frozenset(
    {
        "saldo",
        "balance",
        "credit",
        "credito",
        "credits",
        "creditos",
        "points",
        "pontos",
        "limit",
        "limite",
    }
)
PRICE_DOWN_WORDS: Final[frozenset[str]] = frozenset(
    {"price", "preco", "valor", "amount", "cost", "custo"}
)
PRICE_UP_WORDS: Final[frozenset[str]] = frozenset({"discount", "desconto"})
GOOD_STATE_WORDS: Final[frozenset[str]] = frozenset(
    {"active", "ativo", "enabled", "habilitado", "paid", "pago"}
)
BAD_STATE_WORDS: Final[frozenset[str]] = frozenset(
    {"blocked", "bloqueado", "banned", "locked", "deleted", "disabled", "suspended"}
)
OWNERSHIP_WORDS: Final[frozenset[str]] = frozenset({"owner", "dono", "tenant", "organization"})
OWNERSHIP_NAMES: Final[frozenset[str]] = frozenset(
    {
        "ownerid",
        "userid",
        "tenantid",
        "accountid",
        "clinicaid",
        "createdby",
        "criadopor",
        "organizationid",
        "orgid",
    }
)
"""Nomes compostos (normalizados) de dono do recurso: nunca derivados."""

AUDIT_NAMES: Final[frozenset[str]] = frozenset(
    {
        "createdat",
        "updatedat",
        "deletedat",
        "modifiedat",
        "createdon",
        "updatedon",
        "criadoem",
        "atualizadoem",
        "version",
        "versao",
        "revision",
        "etag",
        "uuid",
        "id",
        *DEFAULT_VOLATILE_FIELDS,
    }
)
"""Nomes (normalizados) de identificação, auditoria e campos voláteis: nunca candidatos."""

ADMIN_ENUM_PREFERENCE: Final[tuple[str, ...]] = (
    "admin",
    "administrator",
    "root",
    "superuser",
    "owner",
    "staff",
)
"""Valores de enum preferidos para um campo de privilégio (sem diferenciar maiúsculas)."""

_MIN_ID_STEM = 3


def classify_candidate(name: str) -> CandidateKind | None:
    """Classe do campo pelo NOME, ou `None` se a lista fixa não o conhece.

    Dono do recurso (`ownership`) vence tudo: `tenantLevel` é dono, não privilégio. Segredo não
    tem classe (nunca é candidato): quem chama o descarta antes.
    """
    words = set(field_words(name))
    normalized = normalize_field_name(name)
    if normalized in OWNERSHIP_NAMES or words & OWNERSHIP_WORDS:
        return "ownership"
    if words & (BAD_STATE_WORDS | GOOD_STATE_WORDS):
        return "state"
    if words & PRIVILEGE_WORDS:
        return "privilege"
    if words & BALANCE_WORDS:
        return "balance"
    if words & (PRICE_DOWN_WORDS | PRICE_UP_WORDS):
        return "price"
    return None


def moves_up(name: str) -> bool:
    """Se o valor de teste de um campo numérico ou booleano sobe (`True`) ou desce (`False`).

    Só `price` e afins descem; `discount` sobe; o estado ruim (`blocked`) desce para `False`.
    """
    words = set(field_words(name))
    if words & BAD_STATE_WORDS:
        return False
    if words & PRICE_UP_WORDS:
        return True
    return not words & PRICE_DOWN_WORDS


def is_excluded_name(name: str, path_tail: str | None) -> bool:
    """Nomes que nunca viram candidato derivado: segredo, identificador, auditoria e volátil.

    Args:
        name: Nome do campo.
        path_tail: Último segmento literal do caminho da família (`medicos`), ou `None`;
            `medicoId` é o identificador do próprio recurso e fica de fora.
    """
    normalized = normalize_field_name(name)
    if classify_field_name(name) == "secret" or normalized in AUDIT_NAMES:
        return True
    if path_tail is not None and normalized.endswith("id"):
        stem = normalized.removesuffix("id")
        return len(stem) >= _MIN_ID_STEM and normalize_field_name(path_tail).startswith(stem)
    return False

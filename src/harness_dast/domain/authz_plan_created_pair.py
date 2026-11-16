"""Plano de criação para comparar a leitura entre contas do mesmo papel."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from harness_dast.domain.authz_compare import is_success_status
from harness_dast.domain.authz_plan import Planned, shared_role_note, skip_note, unique_exchanges
from harness_dast.domain.authz_plan_mass import created_reader, is_json_object
from harness_dast.domain.probe_exchange import ExchangeRecord


@dataclass(frozen=True)
class CreatedPairTask:
    """Criação por uma conta e leitura por outra do mesmo papel não compartilhado."""

    post: ExchangeRecord
    read: ExchangeRecord
    owner: tuple[str, str]
    actor: tuple[str, str]
    existing_targets: frozenset[str] = frozenset()
    collection: ExchangeRecord | None = None


def plan_created_pairs(
    exchanges: Sequence[ExchangeRecord],
    roles: Mapping[str, str],
    public: frozenset[str],
    shared_roles: Sequence[str],
    infrastructure: frozenset[str],
    *,
    allow_writes: bool,
) -> Planned[CreatedPairTask]:
    """Escolhe POSTs e GETs provados; nunca inventa um endpoint ou papel."""
    posts = unique_exchanges(
        [e for e in exchanges if e.method == "POST" and is_success_status(e.status)]
    )
    known = [e for e in exchanges if e.method == "GET" and is_success_status(e.status)]
    reads = [e for e in known if e.operation_id not in public]
    tasks: list[CreatedPairTask] = []
    notes = []
    seen: set[tuple[str, str]] = set()
    for post in posts:
        if (
            post.operation_id in public
            or post.path in infrastructure
            or not is_json_object(post.body)
        ):
            continue
        parent = post.target.split("?", 1)[0].rstrip("/")
        same_parent = [
            read for read in reads if read.target.split("?", 1)[0].rsplit("/", 1)[0] == parent
        ]
        reader = created_reader(post, same_parent)
        collection = next(
            (
                read
                for read in reads
                if read.path == post.path and read.target == post.target and "?" not in read.target
            ),
            None,
        )
        for role in dict.fromkeys(roles.values()):
            accounts = [alias for alias, value in roles.items() if value == role]
            if len(accounts) < 2 or (post.operation_id, role) in seen:
                continue
            seen.add((post.operation_id, role))
            if role in shared_roles:
                notes.append(shared_role_note("horizontal", post))
            elif not allow_writes:
                notes.append(
                    skip_note(
                        "horizontal",
                        post,
                        "writes_not_authorized",
                        "Escrita não autorizada pela carta: authz.allow_writes.",
                    )
                )
            elif reader is None:
                notes.append(
                    skip_note(
                        "horizontal",
                        post,
                        "create_not_readable",
                        "Não há GET provado do recurso criado.",
                    )
                )
            else:
                tasks.append(
                    CreatedPairTask(
                        post,
                        reader,
                        (accounts[0], role),
                        (accounts[1], role),
                        frozenset(read.target.split("?", 1)[0] for read in known),
                        collection,
                    )
                )
    return Planned(tuple(tasks), tuple(notes))

"""Leitura do recurso que um `POST` de teste acabou de criar (ADR 0040).

Única exceção à regra de que o `authz` só repete pedidos gravados em `exchanges.json`: monta UM
tipo de pedido novo, o `GET` do recurso criado, com o modelo de caminho que o `probe` provou e o
identificador que o servidor devolveu à própria requisição (`domain/authz_created`). O pedido
passa pelo `ReplaySender` e pelo `ScopeGuard` como os demais; recusado ou sem resposta útil, vale
a resposta do próprio `POST`.
"""

from dataclasses import dataclass

from harness_dast.application.authz_sender import CheckContext, Reply
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.authz_compare import is_success_status, parse_json
from harness_dast.domain.authz_created import created_identifier, created_read_exchange
from harness_dast.domain.authz_findings import MassObservation
from harness_dast.domain.authz_plan_mass import MassTask


@dataclass(frozen=True)
class CreatedRead:
    """O que se pôde ver do recurso criado.

    Attributes:
        body: Corpo JSON lido (da leitura do recurso ou da resposta do `POST`), ou `None`.
        via: De onde veio (`created_read` ou `post_response`); `None` sem corpo útil.
    """

    body: JsonValue | None
    via: MassObservation | None


def read_created(ctx: CheckContext, task: MassTask, post: Reply) -> CreatedRead:
    """Lê o recurso criado pelo `POST`; sem leitura útil, usa a resposta do próprio `POST`.

    Raises:
        StopRun: O alvo ficou sem resposta em várias requisições seguidas.
        WindowClosed: Janela fechada.
        DeadlineReached: Prazo esgotado.
        ExternalToolError: Falha do proxy.
    """
    if task.read is not None:
        identifier = created_identifier(
            location=post.location,
            body=post.body,
            reader=task.read,
            base_url=ctx.settings.base_url,
        )
        target = created_read_exchange(task.read, identifier) if identifier else None
        if target is not None:
            got = ctx.sender.send(target, target.account)
            parsed = parse_json(got.body) if is_success_status(got.status) else None
            if parsed is not None:
                return CreatedRead(parsed, "created_read")
    echoed = parse_json(post.body)
    return CreatedRead(echoed, "post_response" if echoed is not None else None)

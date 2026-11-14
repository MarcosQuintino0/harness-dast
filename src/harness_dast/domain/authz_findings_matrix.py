"""Construtor do achado da tabela "quem pode o quê" (ADR 0041). Módulo puro.

Severidade e classe saem do código: sempre **alta**, CWE-285, OWASP API5:2023 (BFLA), como na
verificação vertical. O papel proibido entra em `fields`, de modo que cada papel que falha é um
achado de fingerprint distinto na mesma operação. Nenhum valor do alvo entra no texto.
"""

from harness_dast.domain.authz_finding_build import build_finding
from harness_dast.domain.authz_matrix_cells import MatrixTask
from harness_dast.domain.authz_result import AuthzFinding
from harness_dast.domain.finding import normalize_path_template

_POST_NOTE = (
    " Como o método é POST, um recurso foi criado por quem não podia: ele permanece no alvo "
    "(use hdast cleanup ou o reset do ambiente)."
)


def matrix_finding(*, product: str, task: MatrixTask, status: int, source: str) -> AuthzFinding:
    """Achado de uma célula proibida em que o servidor aceitou (`2xx`).

    Args:
        product: Produto.
        task: A célula: papel proibido, pedido provado e conta que enviou.
        status: Código `2xx` observado.
        source: `replay` (o teste enviou o pedido) ou `probe` (a prova já estava gravada).
    """
    exchange = task.exchange
    method = exchange.method.upper()
    where = f"{method} {normalize_path_template(exchange.path)}"
    if source == "probe":
        evidence = (
            f"O probe já obteve {status} com a conta {task.actor} (papel {task.role}), e a "
            f"tabela authz.access_matrix proíbe o papel {task.role} nesta operação. Pode ser só "
            "roteamento do probe (conta padrão), mas o servidor respondeu de verdade."
        )
        owner = None
    else:
        evidence = (
            f"A tabela authz.access_matrix proíbe o papel {task.role} nesta operação e a conta "
            f"{task.actor} (papel {task.role}) recebeu {status} ao repetir o pedido que a conta "
            f"{task.owner[0]} provou ao probe."
        )
        owner = (task.owner[0], task.owner[1])
    if method == "POST":
        evidence += _POST_NOTE
    return build_finding(
        product=product,
        technique="authz_access_matrix",
        title=f"{where} aceita o papel {task.role}, que a tabela proíbe",
        severity="high",
        operation_id=exchange.operation_id,
        method=method,
        path_template=exchange.path,
        actor=(task.actor, task.role),
        owner=owner,
        statuses=(exchange.status, status),
        fields=(task.role,),
        evidence=evidence,
        description=(
            "Uma conta de um papel que o dono do produto declarou como proibido nesta "
            "operação conseguiu executá-la (BFLA)."
        ),
        solution=(
            "Exigir no servidor o papel necessário para a operação e responder 403 aos papéis "
            "que a tabela proíbe; se a tabela estiver errada, corrija-a e aprove de novo."
        ),
    )

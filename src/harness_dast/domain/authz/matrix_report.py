"""Saída da tabela "quem pode o quê" (ADR 0041): as células e a tabela do `authz.json`.

Cada célula é um papel numa operação. O que ela diz vem do código (`authz_matrix_plan`), nunca
do agente. Valor de resposta nunca entra: só código HTTP, apelido de conta e o motivo. É puro.
"""

from typing import Literal

from harness_dast.domain.api_schema import ApiModel

CellDeclared = Literal["allow", "deny", "unspecified"]
CellResult = Literal[
    "declared_allowed",
    "proved_allowed",
    "passed",
    "failed",
    "not_tested",
    "unspecified",
]
CellSource = Literal["probe", "replay"]


class MatrixCell(ApiModel):
    """Um papel numa operação da tabela.

    Attributes:
        role: Papel (coluna da tabela).
        declared: O que o perfil declara: `allow`, `deny` ou `unspecified`.
        result: `declared_allowed` (pode; a ferramenta não testa permissão), `proved_allowed`
            (pode, e o `probe` obteve `2xx` com conta do papel), `passed` (proibido e o
            servidor negou com 401 ou 403), `failed` (proibido e o servidor aceitou com `2xx`,
            ou o `probe` já o provou), `not_tested` (proibido e não deu para testar) e
            `unspecified` (o papel não está na regra: nunca testado, nunca presumido proibido).
        status: Código HTTP observado, quando houve resposta.
        account: Apelido da conta que enviou (ou que o `probe` usou).
        source: `replay` (pedido enviado pelo teste) ou `probe` (prova que já estava gravada).
        reason: Motivo estável do `not_tested` (`writes_not_allowed`, `delete_never_tested`...).
        message: Explicação em português do `not_tested`, com o que fazer.
    """

    role: str
    declared: CellDeclared
    result: CellResult
    status: int | None = None
    account: str | None = None
    source: CellSource | None = None
    reason: str | None = None
    message: str | None = None


class MatrixRow(ApiModel):
    """Uma operação da tabela.

    Attributes:
        operation_id: `operationId` da regra.
        method: Método HTTP, ou `None` se o OpenAPI não tem a operação.
        path: Modelo de caminho, ou `None`.
        cells: Uma célula por papel de `AccessMatrixReport.roles`, na mesma ordem.
    """

    operation_id: str
    method: str | None = None
    path: str | None = None
    cells: tuple[MatrixCell, ...] = ()


class AccessMatrixReport(ApiModel):
    """A tabela inteira, como vai para `authz.json` e para o relatório.

    Attributes:
        roles: Papéis das colunas: os de `authz.role_order` na ordem dela e depois os demais
            papéis de `auth.accounts`, na ordem do perfil.
        rows: Uma linha por regra da tabela, na ordem do perfil.
    """

    roles: tuple[str, ...] = ()
    rows: tuple[MatrixRow, ...] = ()

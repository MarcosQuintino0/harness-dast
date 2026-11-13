"""Resultado do `spec inspect`: modelos congelados lidos pelo agente."""

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.api_summary import ApiSummary


class NotSentOperation(BaseModel):
    """Operação que o `probe` nunca enviará com as opções padrão.

    Attributes:
        operation_id: Identificador da operação.
        method: Método HTTP.
        path: Modelo de caminho.
        reason: `skipped_scope`, `skipped_denied` ou `skipped_destructive`.
        message: Explicação.
    """

    model_config = ConfigDict(frozen=True)

    operation_id: str
    method: str
    path: str
    reason: str
    message: str


class OperationAccount(BaseModel):
    """Conta que enviará uma operação (por `auth.default_account` e `auth.account_map`).

    Attributes:
        operation_id: Identificador da operação.
        account: Apelido da conta (nunca usuário nem senha).
    """

    model_config = ConfigDict(frozen=True)

    operation_id: str
    account: str


class UnusedRule(BaseModel):
    """Regra de `data-rules.yml` que não casa com nenhum campo do OpenAPI.

    Attributes:
        number: Posição da regra no arquivo, a partir de 1.
        field: Valor de `match.field`.
        operation: Valor de `match.operation`, se houver.
    """

    model_config = ConfigDict(frozen=True)

    number: int
    field: str
    operation: str | None = None


class NeedsRule(BaseModel):
    """Operação cuja requisição não pôde ser montada sem uma regra de dados.

    Attributes:
        operation_id: Identificador da operação.
        message: O que não foi possível gerar.
        hint: Que regra escrever.
    """

    model_config = ConfigDict(frozen=True)

    operation_id: str
    message: str
    hint: str | None = None


class InspectIssue(BaseModel):
    """Problema encontrado em `data-rules.yml` ou `flows.yml`.

    Attributes:
        code: `DATA_RULES_INVALID`, `DATA_RULES_MISMATCH`, `FLOWS_INVALID`, `FLOWS_MISMATCH` ou
            `ACCOUNT_MAP_MISMATCH`.
        message: Descrição do problema (sem valores do arquivo).
        hint: O que corrigir.
    """

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    hint: str | None = None


class DocumentInfo(BaseModel):
    """Presença e tamanho de um arquivo de regras.

    Attributes:
        present: Se o arquivo existe.
        valid: Se existe e passou na validação estrutural e contra o OpenAPI.
        count: Quantidade de regras ou de encadeamentos.
    """

    model_config = ConfigDict(frozen=True)

    present: bool
    valid: bool
    count: int = 0


class SpecInspection(BaseModel):
    """Resultado do `spec inspect`.

    Attributes:
        product: Produto.
        summary: Resumo compacto da API (texto do OpenAPI, não confiável).
        servers_out_of_scope: Servidores do OpenAPI fora de `scope.allow` (o `probe` usa só
            `environment.base_url`; servidores do documento nunca definem o escopo).
        not_sent: Operações que o `probe` não enviará com as opções padrão, com o motivo.
        suspicious_operations: Operações cujo nome sugere reiniciar ou apagar dados; considere
            adicioná-las a `scope.deny_paths` (estreitar é permitido).
        data_rules: Situação de `data-rules.yml`.
        flows: Situação de `flows.yml`.
        unused_rules: Regras que não casam com campo algum.
        needs_rule: Operações que ainda precisam de regra (campo obrigatório não gerável).
        needs_rule_unchecked: Consumidores de `flows.yml`, cuja montagem depende de valores
            de outra operação e não foi simulada.
        issues: Problemas nos arquivos de regras e no roteamento de contas.
        operation_accounts: Conta que enviará cada operação que o `probe` envia, no plano.
    """

    model_config = ConfigDict(frozen=True)

    product: str
    summary: ApiSummary
    servers_out_of_scope: tuple[str, ...]
    not_sent: tuple[NotSentOperation, ...]
    suspicious_operations: tuple[str, ...]
    data_rules: DocumentInfo
    flows: DocumentInfo
    unused_rules: tuple[UnusedRule, ...]
    needs_rule: tuple[NeedsRule, ...]
    needs_rule_unchecked: tuple[str, ...]
    issues: tuple[InspectIssue, ...]
    operation_accounts: tuple[OperationAccount, ...] = ()

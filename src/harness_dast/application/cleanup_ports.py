"""Portas consumidas pela capacidade cleanup; assinaturas e docstrings preservadas."""

from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict, SecretStr

from harness_dast.domain.cleanup_binds import BindValue
from harness_dast.domain.cleanup_confirmation import ConfirmationRecord
from harness_dast.domain.cleanup_gate import CleanupStatement
from harness_dast.domain.cleanup_plan import CleanupAuditLine, CleanupPlan, CleanupRecord
from harness_dast.domain.probe_result import RunManifest
from harness_dast.domain.profile import ProductProfile


class CleanupConnection(BaseModel):
    """Como se conectar ao Oracle de testes. Nunca é registrado nem serializado.

    Attributes:
        dsn: DSN (`host:porta/serviço`).
        user: Usuário de banco da limpeza.
        password: Senha desse usuário (`SecretStr`: não aparece em repr nem em log).
        db_schema: Esquema dono das tabelas, quando o usuário não é o dono.
        connect_timeout_seconds: Tempo máximo para abrir a conexão.
        call_timeout_seconds: Tempo máximo de cada comando no banco.
    """

    model_config = ConfigDict(frozen=True)

    dsn: str
    user: str
    password: SecretStr
    db_schema: str | None = None
    connect_timeout_seconds: int
    call_timeout_seconds: int


class CleanupSession(Protocol):
    """Uma transação aberta no banco de testes. Nada vale até `commit`."""

    def execute(self, statement: CleanupStatement, binds: Mapping[str, BindValue]) -> int:
        """Executa um comando já aprovado pelo portão e devolve as linhas afetadas.

        Raises:
            CleanupError: Falha no banco. A mensagem traz só o código do erro, nunca os
                valores de ligação nem as credenciais.
        """
        ...

    def commit(self) -> None:
        """Confirma a transação.

        Raises:
            CleanupError: Falha ao confirmar (o estado fica desconhecido; confira o banco).
        """
        ...

    def rollback(self) -> None:
        """Desfaz a transação. Pode ser chamado mais de uma vez."""
        ...

    def close(self) -> None:
        """Encerra a conexão. Uma transação não confirmada é desfeita."""
        ...


class CleanupExecutor(Protocol):
    """Abre a conexão com o banco de testes e inicia a transação da limpeza."""

    def open(self, connection: CleanupConnection) -> CleanupSession:
        """Conecta e inicia uma única transação (sem confirmação automática).

        Raises:
            CleanupError: Conexão recusada, credencial inválida ou tempo esgotado. A mensagem
                traz só o código do erro.
        """
        ...


class CleanupScripts(Protocol):
    """Leitor do script de limpeza do produto (autoria humana; nunca é escrito pela CLI)."""

    def read(self, product: str, profile: ProductProfile) -> bytes:
        """Lê os bytes do script apontado por `profile.cleanup.script`.

        Garante: o arquivo fica dentro da pasta do produto e no máximo `MAX_SCRIPT_BYTES + 1`
        bytes são lidos (o portão confere o tamanho e recusa o excesso).

        Raises:
            ConfigError: Arquivo ausente, ilegível, grande demais ou fora da pasta do produto.
        """
        ...


class CleanupRuns(Protocol):
    """Arquivos de limpeza de uma execução (`runs/<run_id>/`)."""

    def read_manifest(self, run_id: str) -> RunManifest | None:
        """Lê `manifest.json`; `None` se a execução não existe.

        Raises:
            ConfigError: Manifesto ilegível ou inválido.
        """
        ...

    def write_record(self, run_id: str, record: CleanupRecord) -> None:
        """Grava `cleanup.json` de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def append_audit(self, run_id: str, line: CleanupAuditLine) -> None:
        """Acrescenta uma linha a `cleanup-audit.jsonl` e a persiste antes de retornar.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def save_confirmation(self, run_id: str, record: ConfirmationRecord) -> None:
        """Guarda o token emitido (só o hash), substituindo o anterior.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def load_confirmation(self, run_id: str) -> ConfirmationRecord | None:
        """Lê o token pendente; `None` se não há."""
        ...

    def consume_confirmation(self, run_id: str) -> bool:
        """Gasta o token pendente de forma atômica: só um chamador recebe `True`."""
        ...


class TokenSource(Protocol):
    """Sorteia o token de confirmação (aleatoriedade criptográfica em produção)."""

    def new_token(self) -> str:
        """Devolve um token novo, imprevisível e com pelo menos 128 bits de entropia."""
        ...


class OperatorPrompt(Protocol):
    """Confirmação interativa feita por uma pessoa diante do plano."""

    def confirm(self, plan: CleanupPlan) -> bool:
        """Mostra o plano e pergunta; `True` só se a pessoa confirmou digitando o produto."""
        ...

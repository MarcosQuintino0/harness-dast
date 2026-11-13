"""Autorização de uso único para executar a limpeza sem terminal (`--confirm <token>`).

Fluxo: `hdast cleanup --dry-run` executa os comandos, desfaz tudo e emite um token que vai SÓ
para o terminal de quem operou (stderr). O token se amarra ao produto, à execução, ao hash do
script e ao total de linhas que a pessoa viu; vence em poucos minutos; vale uma vez.

Só o SHA-256 do token é guardado em disco (`ConfirmationRecord`): ler o arquivo da execução não
revela o token. LIMITE HONESTO: isto é controle procedimental. Quem tem acesso ao shell da pessoa
(incluindo um agente) pode rodar o próprio `--dry-run` e ler o stderr. A proteção real é a
combinação de: regra de skill que proíbe o agente de rodar `cleanup`, privilégios mínimos do
usuário de banco e o portão do SQL. Este módulo é puro: relógio e token entram por parâmetro.
"""

import hashlib
import hmac
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.window import ensure_aware

CONFIRMATION_TTL = timedelta(minutes=10)
_HINT = "Rode 'hdast cleanup <produto> --run <run_id> --dry-run' e use o token mostrado no stderr."


class ConfirmationRecord(BaseModel):
    """Token emitido por um `--dry-run` (sem o token em claro).

    Attributes:
        token_sha256: SHA-256 (hex) do token.
        product: Produto a que o token se refere.
        run_id: Execução a que o token se refere.
        script_sha256: Hash do script que a pessoa viu.
        rows_ceiling: Total de linhas que a pessoa viu; o apagado real não pode passar disso.
        issued_at: Instante da emissão (ISO 8601).
        expires_at: Instante em que o token deixa de valer (ISO 8601).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    token_sha256: str
    product: str
    run_id: str
    script_sha256: str
    rows_ceiling: int
    issued_at: str
    expires_at: str


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_record(
    *,
    token: str,
    product: str,
    run_id: str,
    script_sha256: str,
    rows_ceiling: int,
    now: datetime,
) -> ConfirmationRecord:
    """Monta o registro de um token recém-emitido.

    Args:
        token: Token em claro, sorteado por quem chama (nunca é guardado).
        product: Produto.
        run_id: Execução.
        script_sha256: Hash do script visto no `--dry-run`.
        rows_ceiling: Total de linhas visto no `--dry-run`.
        now: Instante da emissão, com fuso.
    """
    ensure_aware(now)
    return ConfirmationRecord(
        token_sha256=_digest(token),
        product=product,
        run_id=run_id,
        script_sha256=script_sha256,
        rows_ceiling=rows_ceiling,
        issued_at=now.isoformat(),
        expires_at=(now + CONFIRMATION_TTL).isoformat(),
    )


def verify_token(
    record: ConfirmationRecord | None,
    token: str,
    *,
    product: str,
    run_id: str,
    script_sha256: str,
    now: datetime,
) -> ConfirmationRecord:
    """Confere o token contra o registro; não consome (quem chama consome depois).

    Raises:
        ConfigError: Sem token emitido, token errado, vencido, ou emitido para outro produto,
            outra execução ou outro script (o script mudou depois do `--dry-run`).
    """
    ensure_aware(now)
    if record is None:
        raise ConfigError("Não há token de confirmação válido para esta execução.", hint=_HINT)
    if not hmac.compare_digest(record.token_sha256, _digest(token)):
        raise ConfigError("O token de confirmação não confere.", hint=_HINT)
    if (record.product, record.run_id) != (product, run_id):
        raise ConfigError("O token foi emitido para outro produto ou outra execução.", hint=_HINT)
    if record.script_sha256 != script_sha256:
        raise ConfigError(
            "O script de limpeza mudou depois do --dry-run que emitiu o token.", hint=_HINT
        )
    if now >= datetime.fromisoformat(record.expires_at):
        raise ConfigError("O token de confirmação venceu.", hint=_HINT)
    return record

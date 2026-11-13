"""Contrato das variáveis de ligação do script de limpeza.

O script de limpeza (escrito por uma pessoa) só pode usar estas variáveis, sempre como
variável de ligação (`:nome`), nunca concatenadas ao texto:

- `:run_start` (data e hora): início da execução (`started_at` do manifesto), em UTC e sem
  fuso (`TIMESTAMP`);
- `:run_id` (texto): identificador completo da execução (`RunId`);
- `:run_tag` (texto): a etiqueta curta (4 a 8 hex) embutida nos valores únicos gerados;
- `:account_1` .. `:account_N` (texto): usuário de login de cada conta de teste, na ordem de
  `auth.accounts` do perfil.

`N` é a quantidade de contas do perfil. Qualquer outro nome (inclusive `:account_0`, `:account_N+1`
e variáveis posicionais como `:1`) é recusado antes de abrir a conexão. Os valores nunca são
mostrados em saída, log, auditoria nem relatório: só os nomes.

Este módulo é puro: o instante vem do manifesto e os usuários chegam já resolvidos.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.unique_values import run_tag_from_run_id
from harness_dast.domain.window import ensure_aware

type BindValue = str | datetime

STATIC_BINDS = ("run_start", "run_id", "run_tag")


def account_bind_name(position: int) -> str:
    """Nome da variável da conta na posição `position` (a partir de 1)."""
    return f"account_{position}"


def allowed_bind_names(account_count: int) -> frozenset[str]:
    """Nomes (minúsculos) aceitos num perfil com `account_count` contas."""
    accounts = (account_bind_name(number) for number in range(1, account_count + 1))
    return frozenset((*STATIC_BINDS, *accounts))


def parse_run_start(value: str) -> datetime:
    """Lê o `started_at` do manifesto (ISO 8601 com fuso) e devolve o instante em UTC, com fuso.

    Raises:
        ConfigError: Se o texto não for uma data e hora com fuso.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ConfigError(
            "O manifesto da execução tem um started_at inválido.",
            hint="Não edite manifest.json; use um run_id gerado pelo probe.",
        ) from None
    ensure_aware(parsed)
    return parsed.astimezone(UTC)


def build_binds(
    *, run_id: str, started_at: datetime, usernames: Sequence[str]
) -> Mapping[str, BindValue]:
    """Monta todos os valores do contrato.

    Args:
        run_id: Identificador da execução.
        started_at: Início da execução, com fuso; vira UTC sem fuso (`:run_start`).
        usernames: Usuários de login das contas, na ordem do perfil.

    Returns:
        Mapa nome (minúsculo) para valor. Quem executa passa a cada comando só as variáveis
        que o comando usa.

    Raises:
        ConfigError: Se `started_at` não tiver fuso ou `run_id` não tiver etiqueta válida.
    """
    ensure_aware(started_at)
    binds: dict[str, BindValue] = {
        "run_start": started_at.astimezone(UTC).replace(tzinfo=None),
        "run_id": run_id,
        "run_tag": run_tag_from_run_id(run_id),
    }
    for position, username in enumerate(usernames, start=1):
        binds[account_bind_name(position)] = username
    return binds


def select_binds(binds: Mapping[str, BindValue], names: Sequence[str]) -> dict[str, BindValue]:
    """Recorta os valores das variáveis que um comando usa (o driver recusa as que sobram)."""
    return {name: binds[name] for name in names}

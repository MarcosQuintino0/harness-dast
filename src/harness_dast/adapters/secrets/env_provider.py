"""Provedor de segredos por variável de ambiente (implementa `SecretProvider`)."""

from collections.abc import Mapping

from harness_dast.domain.secret_ref import SecretRef


class EnvSecretProvider:
    """Lê o valor de `secret_ref: env:NOME` do ambiente recebido.

    O mapa de ambiente entra pelo construtor (a CLI passa `os.environ`), então o adaptador
    não lê estado global e é testável. Nunca registra nem inclui o valor em exceção.
    """

    def __init__(self, environ: Mapping[str, str]) -> None:
        """Cria o provedor.

        Args:
            environ: Variáveis de ambiente disponíveis.
        """
        self._environ = environ

    def resolve(self, ref: SecretRef) -> str | None:
        """Devolve o valor da variável, ou `None` se ausente ou só com espaços."""
        value = self._environ.get(ref.env_name)
        if value is None or not value.strip():
            return None
        return value

"""Validação do identificador de execução que a pessoa informa em `--run` e `--compare`."""

from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.run import RunId


def require_run_id(value: str) -> str:
    """Devolve o identificador se tiver o formato de `RunId`.

    Raises:
        ConfigError: Formato inválido. A mensagem não repete o texto recebido, que pode ser um
            caminho (o identificador vira nome de pasta).
    """
    try:
        return RunId(value=value).value
    except ValidationError:
        raise ConfigError(
            "Identificador de execução inválido.",
            hint="Use o run_id devolvido pelo probe, no formato AAAA-MM-DDTHH-MM-SSZ-produto-xxxx.",
        ) from None

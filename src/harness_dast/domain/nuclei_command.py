"""Argumentos fixos e seguros do Nuclei (ADR 0122).

O que garante: a lista de argumentos sai só de entradas tipadas. Sempre leva as opções que
desligam OAST, atualização, protocolos fora de HTTP e cor, e a saída enxuta em JSONL; nunca
leva as opções que ligam fuzz, DAST, código, navegador, nuvem, autenticação por arquivo ou
atualização. O segredo só aparece como CAMINHO do arquivo em `-sf`, nunca como valor.
O que não faz: não executa o Nuclei nem grava arquivos.
"""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt

__all__ = ["NUCLEI_FORBIDDEN_FLAGS", "NucleiCommandInput", "build_nuclei_args"]

NUCLEI_FORBIDDEN_FLAGS = frozenset(
    {"-fr", "-dast", "-code", "-headless", "-cloud-upload", "-auth", "-update", "-ut"}
)
"""Opções que nunca podem aparecer nos argumentos do Nuclei."""


def _validate_value(value: str) -> str:
    # Um valor iniciado por '-' viraria outra opção; controle quebraria a linha de comando.
    if not value or value.startswith("-") or not value.isprintable():
        raise ValueError("valor de argumento vazio, iniciado por '-' ou com caractere de controle")
    return value


_Value = Annotated[str, AfterValidator(_validate_value)]


class NucleiCommandInput(BaseModel):
    """Entradas tipadas dos argumentos.

    Attributes:
        target_url: URL base do alvo.
        proxy_url: URL da cerca `scope-proxy-nuclei`.
        requests_per_second: Ritmo (`-rl`), inteiro positivo.
        concurrency: Concorrência (`-c`), inteira positiva.
        templates_list_path: Caminho do arquivo com os modelos escolhidos (`-t`).
        secret_file_path: Caminho do arquivo de segredos (`-sf`) ou `None` sem login.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_url: _Value
    proxy_url: _Value
    requests_per_second: StrictInt = Field(ge=1)
    concurrency: StrictInt = Field(ge=1)
    templates_list_path: _Value
    secret_file_path: _Value | None = None


def build_nuclei_args(command: NucleiCommandInput) -> tuple[str, ...]:
    """Monta os argumentos do Nuclei, sem o nome do binário.

    Args:
        command: Entradas já validadas.

    Returns:
        Os argumentos, com as opções de segurança sempre presentes e as proibidas ausentes.
    """
    args = [
        "-ni",
        "-duc",
        "-pt",
        "http",
        "-jsonl",
        "-omit-raw",
        "-nc",
        "-u",
        command.target_url,
        "-t",
        command.templates_list_path,
        "-proxy",
        command.proxy_url,
        "-rl",
        str(command.requests_per_second),
        "-c",
        str(command.concurrency),
    ]
    if command.secret_file_path is not None:
        args.extend(("-sf", command.secret_file_path))
    return tuple(args)

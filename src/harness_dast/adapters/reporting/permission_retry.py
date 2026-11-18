"""Nova tentativa curta para arquivo momentaneamente preso por outro processo.

No Windows, gravar, trocar ou ler um arquivo que outro processo tem aberto (`hdast wait`,
`hdast stop`, a pessoa, antivírus) levanta `PermissionError`. A condição passa em instantes;
sem a nova tentativa, uma leitura de cortesia derrubava a varredura inteira.
"""

from collections.abc import Callable
from typing import Final

REPLACE_ATTEMPTS: Final = 10
_PAUSE_STEP_SECONDS: Final = 0.05
_PAUSE_CAP_SECONDS: Final = 0.2


def retry_on_permission_error[T](action: Callable[[], T], sleep: Callable[[float], None]) -> T:
    """Executa `action`, repetindo poucas vezes só quando ela levanta `PermissionError`.

    Garante: no máximo `REPLACE_ATTEMPTS` execuções e pausa total limitada (cerca de 1,6 s).
    Levanta: o último `PermissionError`, se o arquivo continuar preso; qualquer outra exceção
    sai na hora, sem nova tentativa.
    """
    attempt = 0
    while True:
        try:
            return action()
        except PermissionError:
            attempt += 1
            if attempt >= REPLACE_ATTEMPTS:
                raise
            sleep(min(_PAUSE_STEP_SECONDS * attempt, _PAUSE_CAP_SECONDS))

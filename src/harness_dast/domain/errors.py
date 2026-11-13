"""Hierarquia de erros do harness e mapeamento para códigos de saída.

Todo erro esperado herda de `HarnessError` e traz um `code` estável (legível por
máquina), uma `message` que diz o que houve e uma `hint` opcional que diz o que fazer.
A CLI traduz esses erros em envelope JSON e código de saída; nada aqui faz I/O.
"""

from enum import IntEnum
from typing import ClassVar


class ExitCode(IntEnum):
    """Códigos de saída do processo `hdast`. Fazem parte do contrato público.

    5 é reservado a falha de ferramenta externa (ZAP, Docker); 6 é o alvo respondendo de
    forma que impede o prosseguimento; 7 é falha na limpeza do ambiente; 130 é interrupção
    pelo usuário (Ctrl+C), convenção de shell para SIGINT.
    """

    OK = 0
    FINDINGS = 1
    USAGE = 2
    SCOPE = 3
    PREFLIGHT = 4
    EXTERNAL_TOOL = 5
    TARGET = 6
    CLEANUP = 7
    INTERRUPTED = 130
    INTERNAL = 10


class HarnessError(Exception):
    """Erro base esperado do harness.

    Attributes:
        code: Identificador estável do erro, em MAIUSCULAS.
        exit_code: Código de saída do processo associado a este tipo de erro.
        message: Descrição do que aconteceu.
        hint: Orientação do que fazer, ou `None` quando não há.
    """

    code: ClassVar[str] = "INTERNAL"
    exit_code: ClassVar[ExitCode] = ExitCode.INTERNAL

    def __init__(self, message: str, hint: str | None = None) -> None:
        """Cria o erro.

        Args:
            message: O que aconteceu.
            hint: O que fazer a respeito (opcional).
        """
        super().__init__(message)
        self.message = message
        self.hint = hint


class ConfigError(HarnessError):
    """Configuração, perfil ou argumento inválido."""

    code = "CONFIG_ERROR"
    exit_code = ExitCode.USAGE


class ScopeViolation(HarnessError):
    """Ação fora do escopo, dos limites ou da janela autorizados."""

    code = "SCOPE_VIOLATION"
    exit_code = ExitCode.SCOPE


class PreflightError(HarnessError):
    """Verificação anterior à execução falhou."""

    code = "PREFLIGHT_FAILED"
    exit_code = ExitCode.PREFLIGHT


class ExternalToolError(HarnessError):
    """Ferramenta externa (por exemplo o ZAP) indisponível ou com resposta inválida."""

    code = "EXTERNAL_TOOL_ERROR"
    exit_code = ExitCode.EXTERNAL_TOOL


class TargetError(HarnessError):
    """O alvo respondeu de forma que impede o prosseguimento."""

    code = "TARGET_ERROR"
    exit_code = ExitCode.TARGET


class TargetTimeout(TargetError):
    """O alvo não respondeu dentro do tempo limite de uma requisição."""

    code = "TARGET_TIMEOUT"


class TargetUnreachable(TargetError):
    """Não foi possível falar com o alvo (conexão recusada, reiniciada ou interrompida)."""

    code = "TARGET_UNREACHABLE"


class CleanupError(HarnessError):
    """A limpeza do ambiente de teste falhou."""

    code = "CLEANUP_FAILED"
    exit_code = ExitCode.CLEANUP


class UserInterrupt(HarnessError):
    """A pessoa interrompeu a execução (Ctrl+C); não é falha do harness nem do alvo."""

    code = "INTERRUPTED"
    exit_code = ExitCode.INTERRUPTED

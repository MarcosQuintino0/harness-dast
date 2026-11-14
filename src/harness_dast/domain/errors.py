"""Hierarquia de erros do harness e mapeamento para códigos de saída.

Todo erro esperado herda de `HarnessError` e traz um `code` estável (legível por
máquina), uma `message` que diz o que houve e uma `hint` opcional que diz o que fazer.
A CLI traduz esses erros em envelope JSON e código de saída; nada aqui faz I/O.
"""

from enum import IntEnum
from typing import ClassVar

from harness_dast.domain.scope_reason import ScopeReason


class ExitCode(IntEnum):
    """Códigos de saída do processo `hdast`. Fazem parte do contrato público.

    5 é reservado a falha de ferramenta externa (ZAP, Docker); 6 é o alvo respondendo de
    forma que impede o prosseguimento; 7 é falha na limpeza do ambiente; 8 é a pilha ocupada por
    outra execução (ADR 0035); 130 é interrupção
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
    BUSY = 8
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


class LetterRejected(ConfigError):
    """A carta de autorização estruturada (`carta.yml`) não passou na conferência (ADR 0036).

    Falha fechada: nada foi gerado. A resposta que falta vem da pessoa, nunca do agente.
    """

    code = "LETTER_REJECTED"


class ScopeViolation(HarnessError):
    """Ação fora do escopo, dos limites ou da janela autorizados.

    Attributes:
        reason: Código estável do motivo quando a recusa vem da normalização ou do
            `ScopeGuard`; `None` nas demais (janela, autorização).
    """

    code = "SCOPE_VIOLATION"
    exit_code = ExitCode.SCOPE

    def __init__(
        self, message: str, hint: str | None = None, *, reason: ScopeReason | None = None
    ) -> None:
        """Cria a violação.

        Args:
            message: O que aconteceu.
            hint: O que fazer a respeito (opcional).
            reason: Código estável do motivo (opcional).
        """
        super().__init__(message, hint)
        self.reason = reason


class ScopeNotApproved(HarnessError):
    """Os blocos de proteção do perfil não têm a aprovação de uma pessoa (ADR 0037).

    Falha fechada: sem aprovação, ou com o perfil alterado depois dela, nenhum comando que
    toca o alvo roda. Usa a saída 3 (a mesma da cerca) e código próprio no envelope. Não herda de
    `ScopeViolation` de propósito: nenhum `except ScopeViolation` existente (janela, cerca) pode
    engolir a falta de aprovação.

    Attributes:
        state: `not_approved` (nunca aprovado), `changed` (perfil mudou desde a aprovação) ou
            `invalid` (arquivo de aprovação ilegível, de versão desconhecida ou de outro produto).
        changed_blocks: Identificadores dos blocos que mudaram (só com `state == "changed"`).
    """

    code = "SCOPE_NOT_APPROVED"
    exit_code = ExitCode.SCOPE

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        *,
        state: str = "not_approved",
        changed_blocks: tuple[str, ...] = (),
    ) -> None:
        """Cria o erro.

        Args:
            message: O que aconteceu.
            hint: O que fazer a respeito (opcional).
            state: Estado da aprovação (veja a classe).
            changed_blocks: Blocos alterados desde a aprovação.
        """
        super().__init__(message, hint)
        self.state = state
        self.changed_blocks = changed_blocks


class PreflightError(HarnessError):
    """Verificação anterior à execução falhou."""

    code = "PREFLIGHT_FAILED"
    exit_code = ExitCode.PREFLIGHT


class SecretBackendError(HarnessError):
    """O cofre de credenciais do sistema não está utilizável (ADR 0030).

    Nunca cai em silêncio para outro lugar (variável de ambiente, arquivo).
    """

    code = "SECRET_BACKEND_ERROR"
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


class StackBusy(HarnessError):
    """A pilha (ZAP e proxy) já está ocupada por outra execução (ADR 0035).

    Falha fechada: duas execuções na mesma pilha se corromperiam (sessão do ZAP, regra de token
    e histórico são globais). Não é falha do alvo nem da ferramenta: é só "tente depois".
    """

    code = "STACK_BUSY"
    exit_code = ExitCode.BUSY


class UserInterrupt(HarnessError):
    """A pessoa interrompeu a execução (Ctrl+C); não é falha do harness nem do alvo."""

    code = "INTERRUPTED"
    exit_code = ExitCode.INTERRUPTED

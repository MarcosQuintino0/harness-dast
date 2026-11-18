"""Portas consumidas pela capacidade stack; assinaturas e docstrings preservadas."""

from datetime import datetime
from pathlib import Path
from typing import Protocol

from harness_dast.application.stack_models import ComposeProject, LabAccountPaths, ServiceStatus
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run import RunId
from harness_dast.domain.stack_binding import StackDigests


class ProxyPolicyStore(Protocol):
    """Grava a política do proxy de escopo e aciona a trava de emergência."""

    def publish(
        self, profile: ProductProfile, run_id: RunId, not_after: datetime, directory: Path
    ) -> Path:
        """Gera `policy.json` a partir do perfil, valida e grava em `directory`.

        Garante: escopo e limites iguais aos do perfil (nunca mais largos) e arquivo que o
        validador do proxy aceita.

        Raises:
            ConfigError: Política inválida ou falha de escrita.
        """
        ...

    def trigger_kill(self, directory: Path) -> bool:
        """Cria o arquivo `KILL`; devolve `False` se ele já existia.

        Raises:
            ConfigError: Pasta inexistente ou falha ao criar o arquivo.
        """
        ...

    def kill_active(self, directory: Path) -> bool:
        """Diz se o arquivo `KILL` existe."""
        ...


class StackBindingSource(Protocol):
    """Lê o vínculo que o `stack up` gravou e os arquivos de agora (ADR 0081). Só lê."""

    def recorded(self, policy_dir: Path) -> StackDigests | None:
        """Hashes que a política da pilha em `policy_dir` prende; `None` sem vínculo.

        Raises:
            ConfigError: Política ausente, grande demais ou inválida (o proxy falharia fechado).
        """
        ...

    def current(self, product: str) -> StackDigests:
        """Hashes dos arquivos de agora (perfil e aprovação); `None` no que não pôde ser lido."""
        ...


class ComposeRunner(Protocol):
    """Docker Compose. Toda chamada tem prazo e devolve falha como `ExternalToolError`."""

    def build(
        self, project: ComposeProject, env: dict[str, str], services: tuple[str, ...]
    ) -> None:
        """Constrói os serviços indicados; falhas levantam `ExternalToolError`."""
        ...

    def up(
        self,
        project: ComposeProject,
        env: dict[str, str],
        *,
        build: bool | None,
        timeout_seconds: int,
    ) -> None:
        """Sobe o projeto recriando os contêineres e espera ficarem saudáveis.

        `build=None` deixa o Compose construir serviços de laboratório sob demanda.

        Raises:
            ExternalToolError: Docker ausente, daemon parado, falha do compose ou prazo.
        """
        ...

    def down(self, project: ComposeProject, env: dict[str, str], *, timeout_seconds: int) -> None:
        """Derruba o projeto e remove contêineres e redes dele.

        Raises:
            ExternalToolError: Docker ausente, daemon parado, falha do compose ou prazo.
        """
        ...

    def status(self, project: ComposeProject, env: dict[str, str]) -> tuple[ServiceStatus, ...]:
        """Lista os serviços do projeto (vazio se não há contêiner).

        Raises:
            ExternalToolError: Docker ausente, daemon parado ou saída ilegível.
        """
        ...


class LabAccountProvisioner(Protocol):
    """Cadastra contas sintéticas do laboratório após a subida do alvo."""

    def provision(self, credentials: dict[str, str], paths: LabAccountPaths) -> None:
        """Cadastra contas e veículos; falhas não devem conter valores de credenciais."""
        ...


class StackLockFile(Protocol):
    """Arquivo de trava exclusiva da pilha, na pasta de estado (ADR 0035).

    Só mexe em arquivo: quem decide se a trava está viva ou órfã é o domínio.
    """

    def location(self) -> Path:
        """Caminho do arquivo de trava."""
        ...

    def create_exclusive(self, content: str) -> bool:
        """Cria o arquivo com `content` de uma vez só; `False` se ele já existe.

        O conteúdo aparece junto com o arquivo: ninguém nunca lê uma trava pela metade.

        Raises:
            ConfigError: Falha de escrita que não seja "já existe".
        """
        ...

    def read(self) -> str | None:
        """Texto do arquivo; `None` se não existe.

        Raises:
            ConfigError: O arquivo existe, mas não pôde ser lido.
        """
        ...

    def remove_if_unchanged(self, expected: str) -> bool:
        """Apaga o arquivo só se o conteúdo ainda for `expected`; `False` se mudou ou sumiu.

        Garante que quem retoma uma trava órfã nunca apaga a trava nova de outra execução.

        Raises:
            ConfigError: Falha ao apagar.
        """
        ...


class ProcessProbe(Protocol):
    """O processo atual e a pergunta "este processo ainda está vivo?"."""

    def current_pid(self) -> int:
        """Número do processo em execução."""
        ...

    def is_alive(self, pid: int) -> bool:
        """Se existe um processo vivo com esse número.

        Na dúvida (sem permissão para consultar), responde `True`: a trava nunca é retomada
        por engano.
        """
        ...


class RandomSource(Protocol):
    """Aleatoriedade criptográfica para segredos descartáveis."""

    def token_hex(self, nbytes: int) -> str:
        """Devolve `2 * nbytes` dígitos hexadecimais."""
        ...


class ZapScanStopper(Protocol):
    """Parada das varreduras do ZAP (usada pela trava de emergência)."""

    def stop_all_scans(self) -> int:
        """Para todas as varreduras ativas e devolve quantas estavam em andamento.

        Raises:
            ExternalToolError: ZAP inacessível ou resposta inesperada.
        """
        ...

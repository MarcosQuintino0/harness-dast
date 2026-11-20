"""Portas do `nuclei`: motor em contêiner, arquivo de segredos, leitura do JSONL e arquivos.

Declaradas aqui por quem as consome (o caso de uso `nuclei.py`, ADR 0122). Os adaptadores ficam
em `adapters/nuclei/`. Nenhuma porta carrega regra de negócio: escolher modelos, escopo e
gravidade é do domínio.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.nuclei_command import NUCLEI_CATALOG_ROOT
from harness_dast.domain.nuclei_findings import NucleiResultRecord
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.nuclei_scope import NucleiScope

__all__ = [
    "CATALOG_ROOT",
    "SECRETS_MOUNT",
    "TEMPLATES_MOUNT",
    "NucleiArtifacts",
    "NucleiEngine",
    "NucleiFence",
    "NucleiImages",
    "NucleiOutputReader",
    "NucleiParsedOutput",
    "NucleiRunResult",
    "NucleiRunSpec",
    "NucleiSecret",
    "NucleiSecretsWriter",
]

CATALOG_ROOT: Final = NUCLEI_CATALOG_ROOT
"""Raiz do catálogo dentro da imagem (`docker/nuclei/Dockerfile`)."""
TEMPLATES_MOUNT: Final = "/hdast/templates.txt"
"""Onde a lista de modelos aparece no contêiner (montagem somente leitura); vai em `-t`."""
SECRETS_MOUNT: Final = "/hdast/secrets.yaml"
"""Onde o arquivo de segredos aparece no contêiner (somente leitura); vai em `-sf`."""


@dataclass(frozen=True)
class NucleiSecret:
    """O que vai no arquivo `-sf`: um cabeçalho de autenticação para uma origem.

    Attributes:
        domains: Hosts (com e sem porta) aos quais o cabeçalho se aplica: só a origem aprovada.
        header: Nome do cabeçalho (`Authorization`...).
        value: Valor completo do cabeçalho (esquema e token). Fica fora do `repr`.
    """

    domains: tuple[str, ...]
    header: str
    value: str = field(repr=False)


@dataclass(frozen=True)
class NucleiRunSpec:
    """Uma execução única do Nuclei, já montada.

    Attributes:
        args: Argumentos do Nuclei (sem o binário), de `build_nuclei_args`.
        templates: Caminhos dos modelos escolhidos, relativos ao catálogo, em ordem.
        secrets_path: Arquivo de segredos no host, ou `None` sem login. Só o caminho.
        timeout_seconds: Prazo do contêiner; estourado, o contêiner morre e o erro sobe.
        container_name: Nome do contêiner, para derrubá-lo pelo nome.
    """

    args: tuple[str, ...]
    templates: tuple[str, ...]
    secrets_path: Path | None
    timeout_seconds: int
    container_name: str


@dataclass(frozen=True)
class NucleiRunResult:
    """Resultado de uma execução do contêiner.

    Attributes:
        exit_code: Código de saída do Nuclei, como veio.
        raw_jsonl: Saída bruta, num diretório temporário privado; quem a recebe deve passá-la a
            `NucleiEngine.discard` depois de ler.
        killed: Se o contêiner foi derrubado porque `stop_requested` pediu a parada.
    """

    exit_code: int
    raw_jsonl: Path
    killed: bool


@dataclass(frozen=True)
class NucleiParsedOutput:
    """O JSONL já projetado.

    Attributes:
        records: Metadados permitidos de cada linha válida.
        malformed: Quantas linhas não puderam ser projetadas.
    """

    records: tuple[NucleiResultRecord, ...]
    malformed: int


class NucleiEngine(Protocol):
    """Roda o Nuclei num contêiner de uso único atrás da segunda cerca."""

    def run(self, spec: NucleiRunSpec, stop_requested: Callable[[], bool]) -> NucleiRunResult:
        """Roda o contêiner e devolve o código de saída e o JSONL bruto.

        Garante: entrada padrão fechada; lista de modelos e arquivo de segredos montados somente
        leitura; o token nunca em argumento, ambiente nem log; ao estourar o prazo o contêiner
        é morto e removido antes de o erro subir; `stop_requested` é consultado durante a
        execução e, se disser `True`, o contêiner é derrubado.

        Raises:
            ConfigError: Nome de contêiner ou montagem inválidos.
            ExternalToolError: Docker ausente, falha ao iniciar, contêiner que não morreu ou
                prazo estourado.
        """
        ...

    def discard(self, raw_jsonl: Path) -> None:
        """Apaga a saída bruta e o diretório temporário dela; não falha se já sumiu."""
        ...


class NucleiSecretsWriter(Protocol):
    """Grava e apaga o arquivo `-sf` com o token de uma conta."""

    def write(self, secret: NucleiSecret) -> Path:
        """Grava o arquivo e devolve só o caminho.

        Raises:
            ConfigError: Falha ao gravar com segurança (nada fica no disco).
        """
        ...

    def remove(self, path: Path) -> None:
        """Apaga o arquivo que `write` criou; ignora um que já sumiu.

        Raises:
            ConfigError: O arquivo existe e não pôde ser apagado (diz onde, sem o conteúdo).
        """
        ...


class NucleiOutputReader(Protocol):
    """Lê o JSONL bruto e devolve só a projeção por lista branca."""

    def read(self, raw_jsonl: Path) -> NucleiParsedOutput:
        """Lê linha a linha; linha malformada vira contagem e nunca é registrada.

        Raises:
            ExternalToolError: O arquivo não pôde ser lido.
        """
        ...


class NucleiArtifacts(Protocol):
    """Arquivos da execução que o `nuclei` lê (`audit.jsonl`) e grava (`nuclei.json`)."""

    def read_audit(self, run_id: str) -> tuple[AuditEntry, ...]:
        """Lê `audit.jsonl` (para continuar a numeração do login).

        Raises:
            ConfigError: Arquivo ausente, ilegível ou inválido.
        """
        ...

    def write_nuclei(self, run_id: str, result: NucleiResult) -> None:
        """Grava `nuclei.json` de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...


class NucleiFence(Protocol):
    """Política publicada na `scope-proxy-nuclei` (a segunda cerca)."""

    def published_scope(self) -> NucleiScope | None:
        """Política que a cerca do Nuclei tem agora.

        Devolve `None` sem política publicada ou quando ela nega tudo.

        Raises:
            ConfigError: Política ilegível ou inválida (a cerca falharia fechada).
        """
        ...


class NucleiImages(Protocol):
    """Disponibilidade da imagem do Nuclei nesta instalação (`StackImages` a satisfaz)."""

    def require_nuclei(self) -> None:
        """Levanta `ConfigError` com orientação se a instalação não traz o Nuclei."""
        ...

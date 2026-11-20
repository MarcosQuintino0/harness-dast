"""Portas compartilhadas por mais de uma capacidade da aplicação.

Cada Protocol preserva contrato e docstrings. O arquivo excede 300 linhas porque reúne
apenas declarações comuns e suas garantias; portas exclusivas ficam junto da capacidade.
Não há implementação, regra de negócio nem reexportação de compatibilidade aqui.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from harness_dast.application.stack_models import StackDirectories, StackState
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.command_journal import JournalEntry, JournalLoad
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.http_messages import ApprovedRequest, HttpResponse
from harness_dast.domain.knowledge_mutation import MutationMetadata
from harness_dast.domain.mutation_snapshot import MutationSnapshot
from harness_dast.domain.probe_exchange import ExchangeLog
from harness_dast.domain.probe_result import ArtifactHashes, ProbeResult, RunManifest
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.request_builder import ValueSource
from harness_dast.domain.scope_approval import ScopeApproval
from harness_dast.domain.secret_ref import SecretRef
from harness_dast.domain.strategy import StrategyReferences


class MutationJournal(Protocol):
    """Reserva intenções antes do envio e registra apenas resultado conhecido."""

    def begin(
        self,
        key: str,
        previous_state: Literal["absent", "present", "unknown"],
        snapshot: MutationSnapshot | None = None,
        metadata: MutationMetadata | None = None,
    ) -> None:
        """Reserva chave estável; pendência impede repetição."""
        ...

    def finish(self, key: str, outcome: Literal["succeeded", "failed", "observed"]) -> None:
        """Conclui uma intenção com resultado conhecido."""
        ...


class StrategyStore(Protocol):
    """Armazena estratégias sem conceder autorização."""

    def read(self, product: str) -> dict[str, object] | None:
        """Lê estratégia ou devolve None quando ausente."""
        ...

    def check_references(self, product: str, references: StrategyReferences) -> None:
        """Confere contenção das referências."""
        ...

    def migrate(self, product: str, output: str) -> str:
        """Cria cópia neutra sem sobrescrever."""
        ...


class StrategyDependencyStore(Protocol):
    """Armazena estratégia e lê dependências de uma escolha de forma limitada."""

    def read(self, product: str) -> dict[str, object] | None:
        """Lê estratégia ou devolve None quando ausente."""
        ...

    def check_references(self, product: str, references: StrategyReferences) -> None:
        """Confere contenção das referências."""
        ...

    def migrate(self, product: str, output: str) -> str:
        """Cria cópia neutra sem sobrescrever."""
        ...

    def read_dependencies(
        self, product: str, profile: ProductProfile
    ) -> tuple[bytes, bytes | None, bytes | None]:
        """Lê contrato e documentos opcionais com limite e confinamento."""
        ...


class ReferencedFile(BaseModel):
    """Arquivo para o qual o perfil aponta.

    Attributes:
        field: Campo do perfil que o referencia (ex.: `openapi`, `cleanup.script`).
        path: Caminho relativo à pasta do produto, como escrito no perfil.
    """

    model_config = ConfigDict(frozen=True)

    field: str
    path: str


class Clock(Protocol):
    """Relógio. Existe para que janela e validade da autorização sejam testáveis."""

    def now(self) -> datetime:
        """Devolve o instante atual, sempre com fuso horário."""
        ...


class ProfileRepository(Protocol):
    """Fonte dos perfis de produto."""

    def load(self, product: str) -> ProductProfile:
        """Carrega e valida o perfil do produto.

        Garante: o perfil é estruturalmente válido, seu campo `product` é o nome pedido e
        todo arquivo que ele referencia fica DENTRO da pasta do produto.

        Raises:
            ConfigError: Nome de produto inválido, pasta ou perfil ausente ou ilegível,
                YAML inválido ou inseguro, perfil inválido, referência para fora da pasta.
                A mensagem nunca repete o conteúdo do arquivo.
        """
        ...

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        """Lista os arquivos referenciados pelo perfil que ainda não existem.

        Só verifica existência: não lê o conteúdo.

        Raises:
            ConfigError: Se o produto for inválido ou algum caminho sair da pasta do produto.
        """
        ...


class Sleeper(Protocol):
    """Espera. Existe para que ritmo, `Retry-After` e prazo sejam testáveis sem esperar."""

    def sleep(self, seconds: float) -> None:
        """Bloqueia por `seconds` segundos (nunca negativo)."""
        ...


class KillSwitch(Protocol):
    """Trava de emergência (`hdast stop`): uma vez acionada, nenhuma etapa envia mais nada."""

    def engaged(self) -> bool:
        """Diz se a trava foi acionada."""
        ...


class EntropySource(Protocol):
    """Aleatoriedade da execução (sufixo do identificador e semente dos geradores)."""

    def hex_suffix(self) -> str:
        """Devolve 4 dígitos hexadecimais minúsculos para o `RunId`."""
        ...

    def seed(self) -> int:
        """Devolve uma semente inteira não negativa para os geradores de dados."""
        ...


class ValueSourceFactory(Protocol):
    """Cria a fonte de valores dos geradores a partir da semente e do instante de referência."""

    def __call__(self, seed: int, now: datetime) -> ValueSource:
        """Devolve uma fonte determinística para esta semente e este instante."""
        ...


class SpecLoader(Protocol):
    """Leitor do OpenAPI de um produto."""

    def load(self, product: str, profile: ProductProfile) -> ApiSpec:
        """Carrega o OpenAPI apontado por `profile.openapi`.

        Garante: o arquivo fica dentro da pasta do produto e o resultado é o modelo
        normalizado do domínio.

        Raises:
            ConfigError: Arquivo ausente, ilegível, grande demais, fora da pasta ou inválido.
        """
        ...


class ProductDocuments(Protocol):
    """Arquivos de regras do produto (`data-rules.yml`, `flows.yml`) e seus hashes."""

    def load_data_rules(self, product: str) -> DataRules | None:
        """Lê e valida `data-rules.yml`; `None` quando o arquivo não existe.

        Raises:
            ConfigError: YAML inválido ou inseguro, ou regras inválidas.
        """
        ...

    def load_flows(self, product: str) -> FlowSpec | None:
        """Lê e valida `flows.yml`; `None` quando o arquivo não existe.

        Raises:
            ConfigError: YAML inválido ou inseguro, ou encadeamento inválido.
        """
        ...

    def hashes(self, product: str, profile: ProductProfile) -> ArtifactHashes:
        """Calcula o SHA-256 de `target.yml`, `data-rules.yml`, `flows.yml` e do OpenAPI.

        Arquivo ausente vira `None`.

        Raises:
            ConfigError: Se o produto ou algum caminho do perfil sair da pasta do produto.
        """
        ...


class SecretProvider(Protocol):
    """Resolve referências de segredo. Só o código da CLI o chama; o agente nunca vê o valor."""

    def resolve(self, ref: SecretRef) -> str | None:
        """Devolve o valor do segredo, ou `None` se não existe ou está vazio.

        Garante: nunca registra nem inclui o valor em exceção.
        """
        ...


class ApprovalStore(Protocol):
    """Guarda a aprovação humana do escopo, por produto (ADR 0037), fora da pasta do produto."""

    def read(self, product: str) -> ScopeApproval | None:
        """Lê a aprovação do produto; `None` se nunca foi aprovado.

        Raises:
            ScopeNotApproved: Arquivo ilegível, grande demais, de versão desconhecida, de outro
                produto ou com resumos que não conferem (`state="invalid"`): falha fechada.
            ConfigError: Nome de produto inválido.
        """
        ...

    def write(self, approval: ScopeApproval) -> None:
        """Grava (substitui) a aprovação do produto de forma atômica.

        Raises:
            ConfigError: Falha ao gravar na pasta de estado.
        """
        ...


class SecretVault(Protocol):
    """Registro de valores secretos conhecidos, para que sejam mascarados onde aparecerem."""

    def register(self, value: str) -> None:
        """Registra um valor secreto (token, senha, chave)."""
        ...

    def mask(self, text: str) -> str:
        """Troca por `***` toda ocorrência de segredo registrado em `text`."""
        ...


class TargetClient(Protocol):
    """Cliente HTTP do alvo: só envia o que o `ScopeGuard` já aprovou."""

    def send(self, approved: ApprovedRequest) -> HttpResponse:
        """Envia a requisição aprovada, sem seguir redirecionamentos.

        Garante: usa o proxy do ZAP quando `approved.request.route` é `zap`; mantém os
        cookies separados por conta; limita o tempo e o tamanho da resposta.

        Raises:
            TargetTimeout: O alvo não respondeu a tempo.
            TargetUnreachable: Não foi possível falar com o alvo.
            ExternalToolError: O proxy do ZAP não respondeu.
        """
        ...

    def cookie_value(self, account: str, name: str) -> str | None:
        """Valor do cookie `name` guardado para a conta, ou `None`."""
        ...


class ZapControl(Protocol):
    """API de controle do ZAP usada pelo `preflight` e pelo `probe`."""

    def version(self) -> str:
        """Devolve a versão do ZAP.

        Raises:
            ExternalToolError: ZAP inacessível, chave inválida ou resposta inesperada.
        """
        ...

    def start_session(self, name: str) -> None:
        """Abre uma sessão nova e limpa no ZAP (histórico, alertas e contextos zerados).

        Raises:
            ExternalToolError: Falha da API do ZAP.
        """
        ...

    def create_context(self, name: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> int:
        """Cria um contexto restrito às expressões dadas e devolve o identificador dele.

        Raises:
            ExternalToolError: Falha da API do ZAP.
        """
        ...

    def remove_stale_rules(self, prefix: str) -> int:
        """Remove as regras do Replacer cujo nome começa com `prefix`; devolve quantas.

        Regras de outros nomes nunca são tocadas.

        Raises:
            ExternalToolError: Falha da API do ZAP.
        """
        ...


class RunStore(Protocol):
    """Armazém dos arquivos de uma execução (`runs/<run_id>/`)."""

    def write_manifest(self, run_id: str, manifest: RunManifest) -> None:
        """Grava (ou regrava) `manifest.json` de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def append_audit(self, run_id: str, entry: AuditEntry) -> None:
        """Acrescenta uma linha a `audit.jsonl` e a persiste antes de retornar.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def write_probe(self, run_id: str, result: ProbeResult) -> None:
        """Grava `probe.json` de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def write_exchanges(self, run_id: str, log: ExchangeLog) -> None:
        """Grava `exchanges.json` (pedidos com sucesso, sem segredo) de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...


class StackStateStore(Protocol):
    """Estado da pilha gerenciada, guardado fora do repositório e de `runs/`."""

    def load(self) -> StackState | None:
        """Lê o estado; `None` quando não há pilha gerenciada.

        Raises:
            ConfigError: Arquivo ilegível ou inválido.
        """
        ...

    def save(self, state: StackState) -> None:
        """Grava o estado de forma atômica, legível só pela pessoa usuária.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def clear(self) -> None:
        """Apaga o estado (não falha se não existe)."""
        ...

    def directories_for(self, run_id: str) -> StackDirectories:
        """Cria e devolve as pastas de política e auditoria da pilha `run_id`.

        Raises:
            ConfigError: Falha ao criar as pastas.
        """
        ...

    def location(self) -> Path:
        """Caminho do arquivo de estado."""
        ...


class CommandJournalStore(Protocol):
    """Diário de comandos por produto, guardado fora do repositório e de `runs/` (ADR 0033)."""

    def append(self, product: str | None, entry: JournalEntry) -> None:
        """Acrescenta uma linha ao diário do produto (`None`: comandos sem produto).

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def load(self, product: str | None) -> JournalLoad:
        """Lê o diário do produto de forma tolerante: linha corrompida é pulada e contada.

        Um diário que ainda não existe devolve zero linhas.

        Raises:
            ConfigError: O arquivo existe, mas não pôde ser lido.
        """
        ...

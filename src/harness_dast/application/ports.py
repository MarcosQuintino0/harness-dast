"""Portas da camada `application`: o que os casos de uso exigem do mundo externo.

Cada porta é um `typing.Protocol` declarado aqui por quem a consome. Os adaptadores
(`adapters/`) as implementam; os testes usam falsos em memória (`tests/fakes/`).
Nenhuma porta decide regra de negócio: elas só buscam e gravam.
"""

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, SecretStr

from harness_dast.application.stack_models import (
    ComposeProject,
    ServiceStatus,
    StackDirectories,
    StackState,
)
from harness_dast.domain.agent_metrics import AgentMetrics
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.cleanup_binds import BindValue
from harness_dast.domain.cleanup_confirmation import ConfirmationRecord
from harness_dast.domain.cleanup_gate import CleanupStatement
from harness_dast.domain.cleanup_plan import CleanupAuditLine, CleanupPlan, CleanupRecord
from harness_dast.domain.command_journal import JournalEntry, JournalLoad
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.http_messages import ApprovedRequest, HttpResponse
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_exchange import ExchangeLog
from harness_dast.domain.probe_result import ArtifactHashes, ProbeResult, RunManifest
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.request_builder import ValueSource
from harness_dast.domain.run import RunId
from harness_dast.domain.run_metrics import RunMetrics
from harness_dast.domain.run_summary import RunSummary
from harness_dast.domain.scan_result import ScanResult
from harness_dast.domain.scope_approval import ScopeApproval
from harness_dast.domain.secret_ref import SecretRef
from harness_dast.domain.strategy import StrategyReferences
from harness_dast.domain.wait import WaitResult


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


class WaitReader(Protocol):
    """Fornece uma observação validada da execução."""

    def read(self, run_id: str) -> WaitResult:
        """Lê uma observação ou informa erro de configuração."""
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


class ScaffoldedProduct(BaseModel):
    """Pasta de produto recém-criada.

    Attributes:
        directory: Caminho absoluto da pasta criada, com barras normais.
        files: Caminhos dos arquivos criados, relativos à pasta, em ordem alfabética.
    """

    model_config = ConfigDict(frozen=True)

    directory: str
    files: tuple[str, ...]


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


class ProductScaffolder(Protocol):
    """Criador da pasta de um produto novo a partir do modelo."""

    def scaffold(
        self, product: str, *, with_cleanup: bool = False, target_text: str | None = None
    ) -> ScaffoldedProduct:
        """Cria a pasta do produto com os arquivos do modelo.

        Por padrão a subpasta `cleanup/` do modelo NÃO é copiada: a limpeza de dados é opcional
        e o script é de autoria humana. `with_cleanup=True` a copia (README e exemplo).
        `target_text` (ADR 0036) substitui o `target.yml` do modelo pelo texto gerado da carta;
        o texto é gravado como veio, em UTF-8 com quebras LF.

        Garante: nunca sobrescreve uma pasta existente e nunca cria nada fora da pasta de
        produtos; em caso de falha no meio da cópia, não deixa pasta parcial.

        Raises:
            ConfigError: Nome inválido, pasta de produtos ausente, produto já existente,
                modelo indisponível ou falha de escrita.
        """
        ...


class LetterReader(Protocol):
    """Leitor da carta de autorização estruturada (`carta.yml`)."""

    def read(self, path: Path) -> Mapping[str, object]:
        """Lê a carta como mapa, recusando YAML perigoso.

        Raises:
            ConfigError: Arquivo ausente, grande demais, fora de UTF-8 ou YAML inválido ou
                com construção proibida. A mensagem nunca traz o conteúdo do arquivo.
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


class CredentialStore(Protocol):
    """Cofre de credenciais do sistema operacional (`secret_ref: keyring:NOME`, ADR 0030).

    Os três métodos levantam `SecretBackendError` se o cofre não está utilizável; nenhum
    registra nem inclui o valor em exceção.
    """

    def read(self, name: str) -> str | None:
        """Devolve o valor guardado sob `name`, ou `None` se não existe ou está vazio."""
        ...

    def write(self, name: str, value: str) -> None:
        """Guarda `value` sob `name`, substituindo o que houver."""
        ...

    def remove(self, name: str) -> bool:
        """Apaga `name`. Devolve `False` se não existia."""
        ...


class SecretPrompt(Protocol):
    """Prompt de terminal para a PESSOA gerir o cofre; o valor nunca é mostrado."""

    def read_value(self, name: str) -> str:
        """Lê o valor de `name` por prompt oculto, pedindo duas vezes (confirmação)."""
        ...

    def confirm_removal(self, name: str) -> bool:
        """Pede que a pessoa digite `name` para confirmar; `True` só se digitar igual."""
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


class ApprovalPrompt(Protocol):
    """Confirmação de uma PESSOA, em terminal, diante do resumo dos blocos de proteção."""

    def confirm(self, product: str, summary: tuple[str, ...], changes: tuple[str, ...]) -> bool:
        """Mostra o resumo (e o que mudou desde a aprovação anterior) e pergunta.

        Returns:
            `True` só se a pessoa digitou exatamente o nome do produto.
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


class ComposeRunner(Protocol):
    """Docker Compose. Toda chamada tem prazo e devolve falha como `ExternalToolError`."""

    def up(
        self, project: ComposeProject, env: dict[str, str], *, build: bool, timeout_seconds: int
    ) -> None:
        """Sobe o projeto recriando os contêineres e espera ficarem saudáveis.

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


class CleanupConnection(BaseModel):
    """Como se conectar ao Oracle de testes. Nunca é registrado nem serializado.

    Attributes:
        dsn: DSN (`host:porta/serviço`).
        user: Usuário de banco da limpeza.
        password: Senha desse usuário (`SecretStr`: não aparece em repr nem em log).
        db_schema: Esquema dono das tabelas, quando o usuário não é o dono.
        connect_timeout_seconds: Tempo máximo para abrir a conexão.
        call_timeout_seconds: Tempo máximo de cada comando no banco.
    """

    model_config = ConfigDict(frozen=True)

    dsn: str
    user: str
    password: SecretStr
    db_schema: str | None = None
    connect_timeout_seconds: int
    call_timeout_seconds: int


class CleanupSession(Protocol):
    """Uma transação aberta no banco de testes. Nada vale até `commit`."""

    def execute(self, statement: CleanupStatement, binds: Mapping[str, BindValue]) -> int:
        """Executa um comando já aprovado pelo portão e devolve as linhas afetadas.

        Raises:
            CleanupError: Falha no banco. A mensagem traz só o código do erro, nunca os
                valores de ligação nem as credenciais.
        """
        ...

    def commit(self) -> None:
        """Confirma a transação.

        Raises:
            CleanupError: Falha ao confirmar (o estado fica desconhecido; confira o banco).
        """
        ...

    def rollback(self) -> None:
        """Desfaz a transação. Pode ser chamado mais de uma vez."""
        ...

    def close(self) -> None:
        """Encerra a conexão. Uma transação não confirmada é desfeita."""
        ...


class CleanupExecutor(Protocol):
    """Abre a conexão com o banco de testes e inicia a transação da limpeza."""

    def open(self, connection: CleanupConnection) -> CleanupSession:
        """Conecta e inicia uma única transação (sem confirmação automática).

        Raises:
            CleanupError: Conexão recusada, credencial inválida ou tempo esgotado. A mensagem
                traz só o código do erro.
        """
        ...


class CleanupScripts(Protocol):
    """Leitor do script de limpeza do produto (autoria humana; nunca é escrito pela CLI)."""

    def read(self, product: str, profile: ProductProfile) -> bytes:
        """Lê os bytes do script apontado por `profile.cleanup.script`.

        Garante: o arquivo fica dentro da pasta do produto e no máximo `MAX_SCRIPT_BYTES + 1`
        bytes são lidos (o portão confere o tamanho e recusa o excesso).

        Raises:
            ConfigError: Arquivo ausente, ilegível, grande demais ou fora da pasta do produto.
        """
        ...


class CleanupRuns(Protocol):
    """Arquivos de limpeza de uma execução (`runs/<run_id>/`)."""

    def read_manifest(self, run_id: str) -> RunManifest | None:
        """Lê `manifest.json`; `None` se a execução não existe.

        Raises:
            ConfigError: Manifesto ilegível ou inválido.
        """
        ...

    def write_record(self, run_id: str, record: CleanupRecord) -> None:
        """Grava `cleanup.json` de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def append_audit(self, run_id: str, line: CleanupAuditLine) -> None:
        """Acrescenta uma linha a `cleanup-audit.jsonl` e a persiste antes de retornar.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def save_confirmation(self, run_id: str, record: ConfirmationRecord) -> None:
        """Guarda o token emitido (só o hash), substituindo o anterior.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def load_confirmation(self, run_id: str) -> ConfirmationRecord | None:
        """Lê o token pendente; `None` se não há."""
        ...

    def consume_confirmation(self, run_id: str) -> bool:
        """Gasta o token pendente de forma atômica: só um chamador recebe `True`."""
        ...


class TokenSource(Protocol):
    """Sorteia o token de confirmação (aleatoriedade criptográfica em produção)."""

    def new_token(self) -> str:
        """Devolve um token novo, imprevisível e com pelo menos 128 bits de entropia."""
        ...


class OperatorPrompt(Protocol):
    """Confirmação interativa feita por uma pessoa diante do plano."""

    def confirm(self, plan: CleanupPlan) -> bool:
        """Mostra o plano e pergunta; `True` só se a pessoa confirmou digitando o produto."""
        ...


class HostInspector(Protocol):
    """Olhos do `doctor` sobre a máquina: Docker, imagens, portas, pastas e ferramentas.

    Só lê. Nenhum método toca o alvo, sobe contêiner ou altera arquivo.
    """

    def docker_version(self) -> str:
        """Versão do servidor Docker que respondeu.

        Raises:
            ExternalToolError: Docker ausente, parado ou sem resposta no prazo.
        """
        ...

    def compose_images(self, services: tuple[str, ...]) -> tuple[str, ...]:
        """Imagens que o `compose.yaml` do repositório usa para os serviços indicados.

        Raises:
            ConfigError: O `compose.yaml` não foi encontrado ou é ilegível.
        """
        ...

    def image_present(self, reference: str) -> bool:
        """Diz se a imagem já está no Docker local.

        Raises:
            ExternalToolError: Docker ausente, parado ou sem resposta no prazo.
        """
        ...

    def port_is_free(self, port: int) -> bool:
        """Diz se a porta TCP de 127.0.0.1 está livre para publicar."""
        ...

    def uv_version(self) -> str | None:
        """Versão do `uv` no PATH, ou `None` se não está instalado."""
        ...

    def directory_exists(self, path: Path) -> bool:
        """Diz se `path` existe e é uma pasta."""
        ...


class PanelFiles(Protocol):
    """Arquivos da execução que o painel lê e as páginas que ele grava (ADR 0032).

    Todo arquivo de leitura é opcional: ausente ou ilegível devolve `None` (ilegível levanta
    `ConfigError`, e o caso de uso trata os dois do mesmo jeito: "não medido"). Também acha a
    execução mais recente de um produto e grava as páginas HTML em `runs/<run_id>/panel/`.
    Nenhuma página grava fora dessa pasta.
    """

    def read_manifest(self, run_id: str) -> RunManifest | None:
        """Lê `manifest.json`; `None` se não existe."""
        ...

    def read_probe(self, run_id: str) -> ProbeResult | None:
        """Lê `probe.json`; `None` se não existe."""
        ...

    def read_scan(self, run_id: str) -> ScanResult | None:
        """Lê `scan.json`; `None` se não existe."""
        ...

    def read_findings(self, run_id: str) -> FindingsReport | None:
        """Lê `findings.json`; `None` se não existe."""
        ...

    def read_authz(self, run_id: str) -> AuthzResult | None:
        """Lê `authz.json`; `None` se o estágio não rodou."""
        ...

    def read_negative(self, run_id: str) -> NegativeResult | None:
        """Lê `negative.json`; `None` se o estágio não rodou."""
        ...

    def read_summary(self, run_id: str) -> RunSummary | None:
        """Lê `run.json`; `None` quando a execução não passou pelo `hdast run`.

        Raises:
            ConfigError: Arquivo ilegível ou inválido.
        """
        ...

    def read_metrics(self, run_id: str) -> RunMetrics | None:
        """Lê `metrics.json`; `None` quando não existe (execução anterior à medição).

        Raises:
            ConfigError: Arquivo ilegível ou inválido.
        """
        ...

    def read_agent_metrics(self, run_id: str) -> AgentMetrics | None:
        """Lê `agent-metrics.json` (tokens do agente, gravado pela avaliação cega).

        Devolve `None` quando não existe ou não é usável (JSON inválido, versão de formato
        desconhecida): o painel mostra "não medido" e nunca derruba a geração.
        """
        ...

    def latest_run_id(self, product: str) -> str | None:
        """Execução mais recente do produto (pelo carimbo do `run_id`), ou `None`."""
        ...

    def write_pages(self, run_id: str, pages: Mapping[str, str]) -> tuple[str, ...]:
        """Grava as páginas (nome do arquivo -> HTML) e devolve os caminhos relativos à execução.

        Garante: cada arquivo é gravado de forma atômica e o nome nunca sai da pasta do painel.

        Raises:
            ConfigError: Nome de página inválido ou falha de escrita.
        """
        ...

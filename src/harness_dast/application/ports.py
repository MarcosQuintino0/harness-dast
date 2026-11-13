"""Portas da camada `application`: o que os casos de uso exigem do mundo externo.

Cada porta é um `typing.Protocol` declarado aqui por quem a consome. Os adaptadores
(`adapters/`) as implementam; os testes usam falsos em memória (`tests/fakes/`).
Nenhuma porta decide regra de negócio: elas só buscam e gravam.
"""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.http_messages import ApprovedRequest, HttpResponse
from harness_dast.domain.probe_result import ArtifactHashes, ProbeResult, RunManifest
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.request_builder import ValueSource
from harness_dast.domain.secret_ref import SecretRef


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

    def scaffold(self, product: str) -> ScaffoldedProduct:
        """Cria a pasta do produto com os arquivos do modelo.

        Garante: nunca sobrescreve uma pasta existente e nunca cria nada fora da pasta de
        produtos; em caso de falha no meio da cópia, não deixa pasta parcial.

        Raises:
            ConfigError: Nome inválido, pasta de produtos ausente, produto já existente,
                modelo indisponível ou falha de escrita.
        """
        ...


class Sleeper(Protocol):
    """Espera. Existe para que ritmo, `Retry-After` e prazo sejam testáveis sem esperar."""

    def sleep(self, seconds: float) -> None:
        """Bloqueia por `seconds` segundos (nunca negativo)."""
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

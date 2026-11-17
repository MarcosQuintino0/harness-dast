"""Modelos da pilha de contêineres gerenciada pelo `hdast stack`.

`StackState` é o que a CLI lembra entre comandos (chave do ZAP, endereços, pastas). Contém
segredos de laboratório (chave do ZAP e senhas descartáveis do alvo): quem o persiste deve
protegê-lo (ver `adapters/storage/stack_state.py`). Estes modelos são puros.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harness_dast.domain.scan_result import ScanProgress

STATE_SCHEMA_VERSION = 1


class StackProjectSuffix(BaseModel):
    """Sufixo opcional e restrito para nomes de projetos Compose."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str = Field(default="", pattern=r"^(?:-[a-z0-9]{1,20})?$")


class LabAccountPaths(BaseModel):
    """Caminhos literais locais para cadastrar contas e veículos de laboratório."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    signup: str = Field(pattern=r"^/[a-zA-Z0-9_~.-]+(?:/[a-zA-Z0-9_~.-]+)*$", max_length=500)
    login: str = Field(pattern=r"^/[a-zA-Z0-9_~.-]+(?:/[a-zA-Z0-9_~.-]+)*$", max_length=500)
    resend: str = Field(pattern=r"^/[a-zA-Z0-9_~.-]+(?:/[a-zA-Z0-9_~.-]+)*$", max_length=500)
    vehicle: str = Field(pattern=r"^/[a-zA-Z0-9_~.-]+(?:/[a-zA-Z0-9_~.-]+)*$", max_length=500)

    @model_validator(mode="after")
    def validate_paths(self) -> "LabAccountPaths":
        """Recusa segmentos relativos e operações que compartilhem o mesmo caminho."""
        paths = (self.signup, self.login, self.resend, self.vehicle)
        if len(set(paths)) != len(paths) or any(
            segment in {".", ".."} for path in paths for segment in path.split("/")
        ):
            raise ValueError("caminhos repetidos ou relativos")
        return self


class ComposeProject(BaseModel):
    """Um projeto do Docker Compose a subir ou derrubar.

    Attributes:
        name: Nome do projeto (`-p`).
        workdir: Pasta em que o compose é executado (caminhos de `files` são relativos a ela).
        files: Arquivos compose (`-f`), em ordem.
        profiles: Perfis do compose a ativar.
        services: Serviços a subir; vazio sobe todos os do(s) perfil(is) ativo(s).
        remove_volumes: Se os volumes do projeto são descartáveis e devem ser removidos no down.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")
    workdir: str
    files: tuple[str, ...] = Field(min_length=1)
    profiles: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    remove_volumes: bool = False


class ServiceStatus(BaseModel):
    """Estado de um serviço de um projeto compose.

    Attributes:
        project: Nome do projeto.
        service: Nome do serviço.
        state: Estado do contêiner (`running`, `exited`...).
        health: Saúde (`healthy`, `unhealthy`, `starting`) ou vazio sem healthcheck.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    project: str
    service: str
    state: str
    health: str = ""


class StackDirectories(BaseModel):
    """Pastas de uma execução da pilha.

    Attributes:
        policy_dir: Pasta montada somente leitura no proxy (`policy.json` e `KILL`).
        audit_dir: Pasta da trilha de auditoria do proxy.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_dir: Path
    audit_dir: Path


class StackState(BaseModel):
    """O que a pilha gerenciada deixou de estado para os comandos seguintes.

    Attributes:
        schema_version: Versão do formato do arquivo.
        product: Produto cuja política está carregada.
        run_id: Identificador da pilha (vai em toda linha de auditoria do proxy).
        started_at: Início (ISO 8601).
        not_after: Prazo da política (ISO 8601).
        lab_target: Alvo de laboratório anexado (`vampi`, `clinica-piloto`) ou `None`.
        zap_api_key: Chave da API do ZAP desta pilha.
        zap_url: URL da API e do proxy do ZAP no host.
        auth_proxy_url: URL do proxy de escopo no host (login e CSRF).
        policy_dir: Pasta da política (contém o `KILL` quando acionado).
        audit_dir: Pasta da auditoria do proxy.
        projects: Projetos compose subidos, na ordem de subida.
        target_env: Variáveis (credenciais descartáveis) geradas para o alvo, lidas como
            `secret_ref: env:` pelos comandos seguintes. Só nomes que o alvo exige.
        target_urls: Endereços do alvo no host (`api`, `management`), quando publicados.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = STATE_SCHEMA_VERSION
    product: str
    run_id: str
    started_at: str
    not_after: str
    lab_target: str | None = None
    zap_api_key: str = Field(min_length=8)
    zap_url: str
    auth_proxy_url: str
    policy_dir: Path
    audit_dir: Path
    projects: tuple[ComposeProject, ...]
    target_env: dict[str, str] = Field(default_factory=dict)
    target_urls: dict[str, str] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        """Aceita só a versão que este código entende."""
        if value != STATE_SCHEMA_VERSION:
            raise ValueError("versão do arquivo de estado não suportada")
        return value


class StackLockInfo(BaseModel):
    """Quem ocupa a pilha, como `stack status` conta (ADR 0035).

    Attributes:
        state: `held` (dono vivo), `orphan` (dono morto; a próxima execução a retoma) ou
            `unreadable` (arquivo ilegível; a pessoa precisa conferir e apagar).
        command: Comando dono, ou `None` com o arquivo ilegível.
        product: Produto da execução dona.
        lock_id: Identificador da tomada.
        pid: Processo dono.
        started_at: Início (ISO 8601).
        message: Frase pronta para a pessoa, com o que fazer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: Literal["held", "orphan", "unreadable"]
    command: str | None = None
    product: str | None = None
    lock_id: str | None = None
    pid: int | None = None
    started_at: str | None = None
    message: str


class StackReport(BaseModel):
    """O que `stack up` e `stack status` contam ao agente. Nunca contém segredo.

    Attributes:
        managed: Se há uma pilha gerenciada pela CLI.
        running: Se todos os serviços conhecidos estão em execução.
        product: Produto cuja política está carregada.
        run_id: Identificador da pilha.
        lab_target: Alvo de laboratório anexado, ou `None`.
        not_after: Prazo da política (ISO 8601).
        zap_url: URL da API e do proxy do ZAP no host.
        auth_proxy_url: URL do proxy de escopo no host (login e CSRF).
        policy_file: Caminho do `policy.json` da pilha.
        audit_file: Caminho da trilha de auditoria do proxy.
        kill_switch: Se a trava de emergência está acionada.
        services: Estado dos serviços.
        target_urls: Endereços do alvo no host, quando publicados.
        state_file: Caminho do arquivo de estado da CLI.
        warnings: Avisos (por exemplo, pilha anterior que não pôde ser derrubada).
        lock: Quem ocupa a pilha agora (trava exclusiva, ADR 0035); `None` com a pilha livre.
        binding: Frescor da pilha frente ao perfil e à aprovação atuais (ADR 0081): `fresh`,
            `stale`, `unbound` ou `unreadable`; `None` sem pilha ou sem a conferência.
        stale_parts: O que divergiu (`profile`, `approval`, `binding`); vazio se não está velha.
        stale_message: O que houve e o que fazer, quando a pilha está desatualizada.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    managed: bool
    running: bool = False
    product: str | None = None
    run_id: str | None = None
    lab_target: str | None = None
    not_after: str | None = None
    zap_url: str | None = None
    auth_proxy_url: str | None = None
    policy_file: str | None = None
    audit_file: str | None = None
    kill_switch: bool = False
    services: tuple[ServiceStatus, ...] = ()
    target_urls: dict[str, str] = Field(default_factory=dict)
    state_file: str
    warnings: tuple[str, ...] = ()
    lock: StackLockInfo | None = None
    binding: Literal["fresh", "stale", "unbound", "unreadable"] | None = None
    stale_parts: tuple[str, ...] = ()
    stale_message: str | None = None


class StopReport(BaseModel):
    """O que a trava de emergência (`hdast stop`) fez.

    Attributes:
        kill_file: Caminho do arquivo `KILL`.
        kill_created: Se o arquivo foi criado agora (`False`: já existia).
        stack_managed: Se a pasta veio do estado da pilha gerenciada.
        zap_reachable: Se a API do ZAP respondeu.
        zap_scans_stopped: Varreduras do ZAP que estavam em andamento e foram paradas.
        zap_message: Por que o ZAP não pôde ser alcançado, quando for o caso.
        scans_running: Varreduras do `hdast scan`/`run` que estavam andando (lidas de
            `scan-progress.json`, atualizado há pouco) quando a trava foi acionada.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kill_file: str
    kill_created: bool
    stack_managed: bool
    zap_reachable: bool
    zap_scans_stopped: int = 0
    zap_message: str | None = None
    scans_running: tuple[ScanProgress, ...] = ()

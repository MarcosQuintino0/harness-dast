"""Modelos do caso de avaliacao (`evals/cases/<caso>/case.yml`) e do resultado da nota."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Frozen(BaseModel):
    """Base dos modelos: congelados e sem campo desconhecido."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Matcher(Frozen):
    """Condicoes (todas as informadas) para um achado contar para uma falha plantada."""

    titles: tuple[str, ...] = ()
    path_contains: str | None = None
    parameter: str | None = None
    method: str | None = None
    category: str | None = None
    operation_id: str | None = None
    technique: str | None = None  # `authz_horizontal`, `zap_active_scan`... (ADR 0027)


class Flaw(Frozen):
    """Falha plantada no alvo, do gabarito.

    `detectable` diz se uma varredura ativa do ZAP a detecta por desenho. As que nao detecta ficam
    no relatorio, mas nao entram na nota.
    """

    id: str
    title: str
    detectable: bool
    weight: float = 1.0
    match: Matcher | None = None
    partial: Matcher | None = None
    match_any: tuple[Matcher, ...] = ()


class ModeConfig(Frozen):
    """Como o modo do alvo chega ao compose: variavel de ambiente do processo do agente."""

    env_var: str
    values: dict[str, str]


class TargetConfig(Frozen):
    """Alvo de laboratorio do caso."""

    kind: Literal["pilot", "vampi", "crapi"]
    state_url: str | None = None
    mode: ModeConfig | None = None  # alvo sem modo (so vulneravel): crAPI


class Deliver(Frozen):
    """Arquivo que o dono do produto entrega (copiado de `source` para `dest` no workspace)."""

    source: str
    dest: str


class ScopeRuleExpected(Frozen):
    """Uma regra de `scope.allow` da carta."""

    host: str
    scheme: str = "http"
    port: int
    paths: tuple[str, ...]
    methods: tuple[str, ...]


class AccountExpected(Frozen):
    """Conta de teste da carta: apelido, papel e nomes das variaveis de ambiente."""

    alias: str
    role: str
    username_env: str
    password_env: str


class LimitsExpected(Frozen):
    """Limites da carta."""

    requests_per_second: int
    max_duration_minutes: int
    zap_threads_per_host: int


class ExpectedProfile(Frozen):
    """O que a carta autoriza, em forma comparavel com o `target.yml` final."""

    base_url: str
    allow: tuple[ScopeRuleExpected, ...]
    deny_paths: tuple[str, ...]
    reference: str
    valid_until: str
    windows: tuple[str, ...]
    limits: LimitsExpected
    accounts: tuple[AccountExpected, ...]
    cleanup: Literal["absent", "present"] = "absent"
    # Modo de leitura de caminhos da cerca (ADR 0026). A carta-modelo dos casos e estrita: o
    # perfil so pode dizer `wide` se a carta o autorizar.
    path_mode: Literal["strict", "wide"] = "strict"
    allow_authz_writes: bool = False
    authz_shared_roles: tuple[str, ...] = ()
    technologies: tuple[str, ...] = ()
    technologies_quote: str | None = None
    allow_invalid_input_writes: bool = False
    allow_upload_scan: bool = False
    include_outcomes: tuple[str, ...] = ()


class SecretsConfig(Frozen):
    """Segredos: `generate` sao sorteados por rodada; `fixed` sao publicos do laboratorio."""

    generate: tuple[str, ...] = ()
    fixed: dict[str, str] = {}
    password_prefix: str = ""  # alvo com politica de senha (crAPI exige simbolo e maiuscula)


class Forbidden(Frozen):
    """O que o alvo nunca deve receber."""

    methods: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    zero_counters: tuple[str, ...] = ()


class Budget(Frozen):
    """Orcamento de uma rodada, para a nota de custo."""

    tokens: int
    duration_seconds: int


class RequestAnswers(Frozen):
    """As respostas fixas do coordenador as cinco perguntas do pedido minimo (ADR 0120 e 0122).

    `wide_paths` e a 5a pergunta: o Nuclei pode testar qualquer endereco do produto.
    """

    owner: str
    base_url: str
    strength: Literal["LOW", "MEDIUM", "HIGH"]
    writes: bool
    wide_paths: bool = False


class RequestExpectation(Frozen):
    """Criterio "escopo proposto seguro" do caso realista (ADR 0120, secao 6).

    `never_methods` e `never_paths` (caminhos concretos) nunca podem estar no escopo efetivo do
    perfil: o que `scope.allow` libera e `scope.deny_paths` nao nega. `coordinator_answers` e o
    arquivo (na pasta do caso) com o texto das respostas; vai para o lacre, nunca para o workspace.
    """

    answers: RequestAnswers
    never_methods: tuple[str, ...]
    never_paths: tuple[str, ...]
    coordinator_answers: str


class Case(Frozen):
    """Caso = alvo + modos + carta + gabarito.

    `layout` diz como o workspace e montado: `repo` (padrao) copia o repositorio quase inteiro;
    `plugin` entrega so uma pasta de produtos e o plugin fica fora dela (ADR 0119, fase G).
    `request` troca a fidelidade a carta pelo escopo proposto seguro (ADR 0120).
    """

    schema_version: Literal[1]
    name: str
    title: str
    product: str
    modes: tuple[Literal["vulnerable", "secure"], ...]
    target: TargetConfig
    deliver: tuple[Deliver, ...]
    write_files: dict[str, str] = {}
    exclude: tuple[str, ...] = ()
    leak_terms: tuple[str, ...]
    authorization: str
    expected: ExpectedProfile
    secrets: SecretsConfig
    flaws: tuple[Flaw, ...]
    forbidden: Forbidden
    budget: Budget
    layout: Literal["repo", "plugin"] = "repo"
    request: RequestExpectation | None = None

    @model_validator(mode="after")
    def _request_needs_plugin_layout(self) -> "Case":
        if self.request is not None and self.layout != "plugin":
            raise ValueError("o criterio de pedido minimo (request) exige layout: plugin")
        return self


class Check(Frozen):
    """Verificacao objetiva. `passed` e `None` quando nao se aplica ou nao foi possivel medir."""

    id: str
    title: str
    passed: bool | None
    detail: str = ""


class Component(Frozen):
    """Criterio da nota. `score` de 0 a 1, ou `None` se nao se aplica (peso redistribuido)."""

    id: str
    title: str
    weight: float
    score: float | None
    checks: tuple[Check, ...] = ()
    notes: tuple[str, ...] = ()

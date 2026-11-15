"""Bloco opcional `scan` do `target.yml`: política da varredura ativa dentro de um conjunto fechado.

Nenhum campo daqui amplia o escopo de rede (o `ScopeGuard` continua decidindo) nem reativa uma
regra desligada por padrão. Mas vários mexem na carga (`strength`, `max_*_minutes`,
`mutating_methods`) ou no que é relatado (`threshold`, `disable_rules`, `fail_on`): por isso o
bloco inteiro entra na impressão digital da aprovação humana (ADR 0037) e mudá-lo exige nova
aprovação. Limites de carga globais continuam em `limits`. Este módulo é puro.
"""

from typing import Annotated, Final, Literal, get_args

from pydantic import Field, StrictBool, StrictInt, field_validator

from harness_dast.domain.secret_ref import ProfileModel

Level = Literal["LOW", "MEDIUM", "HIGH"]
FailOn = Literal["none", "low", "medium", "high"]
MutatingMethod = Literal["PUT", "PATCH"]
ExtraOutcome = Literal[
    "logical_failure", "validation_error", "conflict", "not_found", "client_error"
]
EXTRA_OUTCOMES: Final = frozenset(get_args(ExtraOutcome))
"""Classes do `probe` além de `success` que a varredura pode atacar (ADR 0050).

Lista fechada: `auth_error`, `csrf_error`, `rate_limited`, `server_error`, `redirect`,
`timeout` e as `skipped_*` nunca entram.
"""

_STRICTNESS: dict[str, int] = {"none": 0, "high": 1, "medium": 2, "low": 3}


def effective_fail_on(from_profile: FailOn, requested: FailOn | None) -> FailOn:
    """Limiar que vale: o pedido na linha de comando só endurece o do perfil, nunca afrouxa.

    O perfil vem da autorização formal; uma flag (que um agente também passa) não pode silenciar
    o código de saída 1 que o perfil exige. `--fail-on none` com um perfil `high` continua `high`.

    Args:
        from_profile: `scan.fail_on` do perfil.
        requested: `--fail-on` da linha de comando, ou `None`.

    Returns:
        O mais rígido dos dois (`low` é mais rígido que `medium`, que é mais que `high`).
    """
    if requested is None:
        return from_profile
    return requested if _STRICTNESS[requested] > _STRICTNESS[from_profile] else from_profile


class ScanConfig(ProfileModel):
    """Política da varredura ativa (ZAP) e do gate de severidade.

    Attributes:
        strength: Força de ataque (`LOW` envia menos carga por parâmetro; padrão do spike).
        threshold: Limiar de alerta do ZAP: só alertas com pelo menos esta confiança entram.
        url_path_injection: Injeta também em segmentos de caminho. Ligado por padrão porque o
            spike mostrou que sem isso a injeção de SQL em parâmetro de caminho passa batida.
        mutating_methods: Métodos `PUT`/`PATCH` que podem ser varridos sobre QUALQUER recurso
            (opt-in). Sem isto, só se varre `PUT`/`PATCH` de recurso criado nesta execução.
        disable_rules: Ids de regras ativas do ZAP a desligar ALÉM das desligadas por padrão
            (nunca reativa as padrão).
        max_scan_minutes: Teto de cada varredura individual (uma por requisição aprendida).
        max_rule_minutes: Teto de cada regra dentro de uma varredura.
        token_refresh_seconds: Idade máxima do token entregue ao ZAP antes de renovar.
        include_outcomes: Classes do `probe` além de `success` cujas operações também são
            atacadas (ADR 0050); lista fechada de `ExtraOutcome`, padrão vazio. Não amplia o
            escopo, só quanto se ataca dentro dele; por isso a aprovação humana a mostra.
        allow_upload_scan: A carta autoriza o ZAP a varrer operações de envio de arquivo
            (`multipart/form-data`, ADR 0052)? Padrão `false`: o ZAP grava conteúdo de ataque no
            armazenamento do alvo (nome e conteúdo de arquivo, campos de texto), então só a carta
            o liga. Sem ele, a operação de upload é alcançada pelo `probe`, mas não varrida
            (`upload_scan_not_authorized`). Ligá-lo muda a impressão digital da aprovação.
        fail_on: Severidade mínima (proposta pelo ZAP) que faz `report` sair com código 1;
            `none` desliga o gate.
    """

    strength: Level = "LOW"
    threshold: Level = "MEDIUM"
    url_path_injection: StrictBool = True
    mutating_methods: tuple[MutatingMethod, ...] = Field(default=(), max_length=2)
    disable_rules: tuple[Annotated[StrictInt, Field(ge=0, le=999_999)], ...] = Field(
        default=(), max_length=100
    )
    max_scan_minutes: StrictInt = Field(default=10, ge=1, le=60)
    max_rule_minutes: StrictInt = Field(default=2, ge=1, le=10)
    token_refresh_seconds: StrictInt = Field(default=120, ge=10, le=3600)
    fail_on: FailOn = "none"
    include_outcomes: tuple[ExtraOutcome, ...] = Field(default=(), max_length=5)
    allow_upload_scan: StrictBool = False

    @field_validator("include_outcomes")
    @classmethod
    def _no_repeated_outcome(cls, value: tuple[ExtraOutcome, ...]) -> tuple[ExtraOutcome, ...]:
        if len(set(value)) != len(value):
            raise ValueError("classe repetida em scan.include_outcomes")
        return value

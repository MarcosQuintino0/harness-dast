"""Bloco opcional `scan` do `target.yml`: política da varredura ativa dentro de um conjunto fechado.

Tudo aqui só ESTREITA ou ajusta com valores de listas fechadas: não existe campo que reative
uma regra desligada por padrão, amplie métodos varridos além do escopo, ou remova um limite.
Limites de carga continuam em `limits` (com tetos absolutos). Este módulo é puro.
"""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt

from harness_dast.domain.secret_ref import ProfileModel

Level = Literal["LOW", "MEDIUM", "HIGH"]
FailOn = Literal["none", "low", "medium", "high"]
MutatingMethod = Literal["PUT", "PATCH"]


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
